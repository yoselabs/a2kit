"""ConnectionStore — TOML-backed save/load/list/delete for named connections.

Generalises both:
- a2db's three-part key (project, env, db) → `{project}-{env}-{db}.toml`
- a2atlassian's flat-name key ("prod") → `prod.toml`

The key is a tuple of one or more string parts. Storage filename is the parts joined
by `-` plus `.toml`.

`ConnectionInfo` is a frozen Pydantic model — consumers subclass to add domain fields
(DSN, URL, email, read_only, project/env/db, ...). The store is generic over the
subclass via a type parameter.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, field_validator

from a2kit.exceptions import ConnectionNotFound, InvalidConnectionKey

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

    Note: a2atlassian hardcodes `~/.config` and tracks XDG_CONFIG_HOME support as a
    backlog item — fixed here at the primitive layer.
    """
    override = os.environ.get(ENV_CONFIG_HOME)
    if override:
        return Path(override)
    return Path.home() / DEFAULT_CONFIG_SUBDIR


class ConnectionInfo(BaseModel):
    """Base frozen connection record.

    Subclass and add domain fields. The `key` tuple is what the store uses to derive
    the on-disk filename. Order and arity matter — `("prod",)` and
    `("acme", "prod", "main")` are both valid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: tuple[str, ...] = Field(min_length=1)

    KEY_PARTS: ClassVar[int | None] = None
    """Optional subclass-level arity check. None = any (1+) arity allowed."""

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        v = _validate_key(v)
        if cls.KEY_PARTS is not None and len(v) != cls.KEY_PARTS:
            msg = f"{cls.__name__} requires a {cls.KEY_PARTS}-part key, got {len(v)}: {v}"
            raise ValueError(msg)
        return v

    @property
    def filename(self) -> str:
        """The on-disk filename derived from the key."""
        return "-".join(self.key) + ".toml"


C = TypeVar("C", bound=ConnectionInfo)


class ConnectionStore(Generic[C]):
    """Manages connection TOML files for a single `ConnectionInfo` subclass.

    The store is parameterised by the model class so `load()` and `list_connections()`
    return strongly-typed instances.
    """

    def __init__(self, config_dir: Path, model: type[C]) -> None:
        self.config_dir = config_dir
        self.model = model

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
        data["key"] = list(data["key"])  # TOML has no tuple type
        # Coerce any tuple fields on subclasses to lists for tomli_w.
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
            tmp_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
            tmp_path.replace(path)
        except Exception:
            tmp.close()
            Path(tmp.name).unlink(missing_ok=True)
            raise
        return path

    def delete(self, key: tuple[str, ...]) -> None:
        """Delete a connection. Raises `ConnectionNotFound` if missing."""
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        path.unlink()

    # -- queries -------------------------------------------------------------

    def load(self, key: tuple[str, ...]) -> C:
        """Load by key. Raises `ConnectionNotFound` if missing."""
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        data = tomllib.loads(path.read_text())
        # tuple fields lose their type through TOML; restore the key tuple.
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
