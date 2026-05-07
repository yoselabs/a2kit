"""ConnectionStore — TOML-backed save/load/list/delete for named connections.

v0.3: keys are **named tuples** declared via `KEY_FIELDS: ClassVar[tuple[str, ...]]`.
Defaults to `("name",)` so the common single-key case is zero-config. Multi-part
keys are declared positionally on the subclass:

    class WidgetConn(a2kit.ConnectionInfo):
        KEY_FIELDS = ("project", "env", "db")
        ...

Filename derivation unchanged: `"-".join(values) + ".toml"`.

Loading shapes (all equivalent):

    store.load(name="prod")              # kwargs (preferred)
    store.load("prod")                   # bare-string sugar (single-field default)
    store.load(("project", "env", "db"))   # tuple (migration path)
    store.load("p", "e", "d")              # positional
    store.load(project=..., env=..., db=...)
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator

from a2kit.exceptions import (
    ConnectionNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

ENV_CONFIG_HOME = "A2KIT_CONFIG_HOME"
DEFAULT_CONFIG_SUBDIR = Path(".config") / "a2kit" / "connections"


def _validate_key_part(part: str) -> str:
    if not _NAME_RE.match(part):
        raise InvalidConnectionKey(part)
    return part


def _validate_key(key: tuple[str, ...]) -> tuple[str, ...]:
    if not key:
        raise InvalidConnectionKey("")
    for part in key:
        _validate_key_part(part)
    return key


def default_config_dir() -> Path:
    """Resolve the default config directory.

    Honours `A2KIT_CONFIG_HOME` (overrides everything). Otherwise falls back to
    `~/.config/a2kit/connections/`.
    """
    override = os.environ.get(ENV_CONFIG_HOME)
    if override:
        return Path(override)
    return Path.home() / DEFAULT_CONFIG_SUBDIR


class ConnectionInfo(BaseModel):
    """Base frozen connection record. Subclass and add domain fields.

    `KEY_FIELDS` declares the named-tuple shape of the key. The on-disk filename
    is `"-".join(values) + ".toml"`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: tuple[str, ...] = Field(min_length=1)

    KEY_FIELDS: ClassVar[tuple[str, ...]] = ("name",)
    """Subclass-level field names. Defaults to a single flat `name` key."""

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        v = _validate_key(v)
        expected = len(cls.KEY_FIELDS)
        if len(v) != expected:
            raise KeyArityMismatch(expected=cls.KEY_FIELDS, got=v)
        return v

    @property
    def filename(self) -> str:
        """The on-disk filename derived from the key."""
        return "-".join(self.key) + ".toml"


C = TypeVar("C", bound=ConnectionInfo)


def _coerce_key(  # noqa: C901
    model: type[C],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[str, ...]:
    """Resolve `load(...)` / `delete(...)` arguments into a validated key tuple."""
    fields = model.KEY_FIELDS
    expected = len(fields)

    # All-kwargs path.
    if not args and kwargs:
        missing = [f for f in fields if f not in kwargs]
        extras = [k for k in kwargs if k not in fields]
        if missing:
            raise KeyFieldMissing(missing[0], have=[f for f in fields if f in kwargs])
        if extras:
            msg = f"Unknown key field(s) {extras!r}; expected one of {list(fields)}"
            raise InvalidConnectionKey(extras[0]) if False else ValueError(msg)
        return tuple(str(kwargs[f]) for f in fields)

    if not args and not kwargs:
        msg = f"load() requires {expected} key field(s): {list(fields)}"
        raise KeyFieldMissing(fields[0] if fields else "name", have=[])

    # Tuple-shape path: load(("a", "b", "c")).
    if len(args) == 1 and isinstance(args[0], tuple) and not kwargs:
        got = args[0]
        if len(got) != expected:
            raise KeyArityMismatch(expected=fields, got=got)
        return tuple(str(p) for p in got)

    # List-shape path (mirror tuple).
    if len(args) == 1 and isinstance(args[0], list) and not kwargs:
        got = tuple(args[0])
        if len(got) != expected:
            raise KeyArityMismatch(expected=fields, got=got)
        return tuple(str(p) for p in got)

    # Single-string-sugar (only for the default single-field shape).
    if len(args) == 1 and isinstance(args[0], str) and not kwargs:
        if expected != 1:
            raise KeyArityMismatch(expected=fields, got=(args[0],))
        return (args[0],)

    # Positional path: load("p", "e", "d").
    if args and not kwargs:
        if len(args) != expected:
            raise KeyArityMismatch(expected=fields, got=tuple(str(a) for a in args))
        return tuple(str(a) for a in args)

    msg = "Cannot mix positional and keyword key arguments"
    raise TypeError(msg)


class ConnectionStore(Generic[C]):
    """Manages connection TOML files for a single `ConnectionInfo` subclass.

    `store.connection_class` exposes the model type for code that wants to derive
    it from the store rather than passing it twice.
    """

    def __init__(self, config_dir: Path, model: type[C]) -> None:
        self.config_dir = config_dir
        self.model = model

    @property
    def connection_class(self) -> type[C]:
        """The `ConnectionInfo` subclass this store is bound to."""
        return self.model

    # -- key/path ------------------------------------------------------------

    def _filename(self, key: tuple[str, ...]) -> str:
        _validate_key(key)
        return "-".join(key) + ".toml"

    def _path(self, key: tuple[str, ...]) -> Path:
        return self.config_dir / self._filename(key)

    # -- mutations -----------------------------------------------------------

    def save(self, info: C) -> Path:
        """Save a connection atomically (tempfile + chmod 0600 + rename)."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(info.key)
        data = info.model_dump(mode="python")
        data["key"] = list(data["key"])
        for k, v in list(data.items()):
            if isinstance(v, tuple):
                data[k] = list(v)
        payload = tomli_w.dumps(data).encode("utf-8")

        prefix = "." + "-".join(info.key) + "."
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            mode="wb", delete=False, dir=self.config_dir, prefix=prefix, suffix=".tmp"
        )
        try:
            tmp.write(payload)
            tmp.close()
            tmp_path = Path(tmp.name)
            tmp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            tmp_path.replace(path)
        except Exception:
            tmp.close()
            Path(tmp.name).unlink(missing_ok=True)
            raise
        return path

    def delete(self, *args: Any, **kwargs: Any) -> None:
        """Delete a connection. Accepts the same call shapes as `load`."""
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        path.unlink()

    # -- queries -------------------------------------------------------------

    def load(self, *args: Any, **kwargs: Any) -> C:
        """Load by key. See module docstring for accepted call shapes."""
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        data = tomllib.loads(path.read_text())
        data["key"] = tuple(data["key"])
        return self.model.model_validate(data)

    def list_connections(self) -> list[C]:
        """List all valid connections in the config dir, sorted by filename."""
        if not self.config_dir.exists():
            return []
        results: list[C] = []
        for path in sorted(self.config_dir.glob("*.toml")):
            data = tomllib.loads(path.read_text())
            data["key"] = tuple(data["key"])
            results.append(self.model.model_validate(data))
        return results
