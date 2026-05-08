"""ConnectionStore — TOML-backed save/load/list/delete for named connections.

v0.5: keys are **NamedTuple instances** declared via `key=` on the subclass:

    class WidgetKey(NamedTuple):
        project: str
        env: Literal["dev", "staging", "prod"]
        db: str

    class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
        base_url: str
        api_key: str

If `key=` is omitted, `cls.Key` defaults to a single-field `_DefaultKey(name: str)`
so the common case stays zero-config.

Filename derivation unchanged: `"-".join(values) + ".toml"`.

Loading shapes (all equivalent):

    store.load(WidgetKey(project="a", env="dev", db="c"))   # typed instance
    store.load(project="a", env="dev", db="c")              # kwargs
    store.load(("a", "dev", "c"))                           # tuple
    store.load("a", "dev", "c")                             # positional
    store.load("prod")                                      # bare-string sugar (single-field default)
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NamedTuple, Protocol, TypeVar, runtime_checkable

import tomli_w

if TYPE_CHECKING:
    from collections.abc import Sequence
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from a2kit.exceptions import (
    ConnectionNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
    MigrationRequired,
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@runtime_checkable
class ConnectionInfoLike(Protocol):
    """Anything with a `.key: tuple[str, ...]` attribute.

    The minimum shape consumers (e.g. `connection_enricher`) need from a listed
    connection. Both `ConnectionInfo` subclasses and bespoke records satisfy
    this structurally. Lives here next to `ConnectionStore`; re-exported from
    `a2kit.enrichers` for backward compatibility through one cycle.
    """

    key: tuple[str, ...]


@runtime_checkable
class ConnectionStoreLike(Protocol):
    """Minimum store contract — `list_connections()` only.

    Both `ConnectionStore` and the internal `_EphemeralAwareStore` proxy
    satisfy this. Used by `connection_enricher` and the schema-hint helper to
    avoid pulling in the full `ConnectionStore[ConnectionInfo]` generic.

    v0.11: `list_connections()` is `async def`. Sync callers wrap with
    `anyio.run(store.list_connections())`.
    """

    async def list_connections(self) -> Sequence[ConnectionInfoLike]: ...


ENV_CONFIG_HOME = "A2KIT_CONFIG_HOME"
DEFAULT_CONFIG_SUBDIR = Path(".config") / "a2kit" / "connections"


class _DefaultKey(NamedTuple):
    """Built-in single-field key used when no `key=` is declared on a subclass."""

    name: str


def _is_namedtuple_class(obj: object) -> bool:
    """True if `obj` is a NamedTuple subclass (has `_fields` and inherits from tuple)."""
    return isinstance(obj, type) and issubclass(obj, tuple) and hasattr(obj, "_fields")


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

    Declare a NamedTuple via `key=`; on-disk filename is `"-".join(values) + ".toml"`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: tuple[str, ...] = Field(min_length=1)

    Key: ClassVar[type[NamedTuple]] = _DefaultKey
    """The NamedTuple key class for this subclass. Bound by `__init_subclass__`."""

    def __init_subclass__(cls, *, key: type[NamedTuple] | None = None, **kwargs: Any) -> None:
        """v0.5: capture `key=` and bind as `cls.Key`. Reject leftover `KEY_FIELDS`.

        - `key=WidgetKey` must be a NamedTuple subclass (validated structurally).
        - If absent, inherits from a parent that already set `Key` (typically `_DefaultKey`).
        - Legacy `KEY_FIELDS` on the subclass body raises `MigrationRequired`.
        """
        super().__init_subclass__(**kwargs)
        if "KEY_FIELDS" in cls.__dict__:
            raise MigrationRequired(cls.__name__, tuple(cls.__dict__["KEY_FIELDS"]))
        if key is not None:
            if not _is_namedtuple_class(key):
                msg = f"{cls.__name__}: `key=` must be a NamedTuple subclass, got {key!r}"
                raise TypeError(msg)
            if not key._fields:  # type: ignore[attr-defined]
                msg = f"{cls.__name__}: `key={key.__name__}` must have at least one field"
                raise ValueError(msg)
            cls.Key = key

    @classmethod
    def _key_field_names(cls) -> tuple[str, ...]:
        return tuple(cls.Key._fields)  # type: ignore[attr-defined]

    @field_validator("key", mode="before")
    @classmethod
    def _coerce_key_input(cls, v: Any) -> tuple[str, ...]:
        """Accept NamedTuple instance / tuple / list / dict / kwargs-like dict for `key`."""
        fields = cls._key_field_names()
        if isinstance(v, dict):
            missing = [f for f in fields if f not in v]
            if missing:
                raise KeyFieldMissing(missing[0], have=[str(k) for k in v], key_class=cls.Key.__name__)
            return tuple(str(v[f]) for f in fields)
        if isinstance(v, list):
            return tuple(str(p) for p in v)
        if isinstance(v, tuple):
            # NamedTuple instance is also a tuple; same path is fine.
            return tuple(str(p) for p in v)
        return v  # let pydantic surface a TypeError downstream

    @field_validator("key")
    @classmethod
    def _validate_key(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        v = _validate_key(v)
        fields = cls._key_field_names()
        expected = len(fields)
        if len(v) != expected:
            raise KeyArityMismatch(expected=fields, got=v, key_class=cls.Key.__name__)
        return v

    @property
    def filename(self) -> str:
        """The on-disk filename derived from the key."""
        return "-".join(self.key) + ".toml"


C = TypeVar("C", bound=ConnectionInfo)
K = TypeVar("K", bound=tuple[Any, ...])


def _coerce_key(  # noqa: C901, PLR0912
    model: type[C],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[str, ...]:
    """Resolve `load(...)` / `delete(...)` arguments into a validated key tuple."""
    key_cls = model.Key
    fields = tuple(key_cls._fields)  # type: ignore[attr-defined]
    expected = len(fields)
    cls_name = key_cls.__name__

    # All-kwargs path.
    if not args and kwargs:
        missing = [f for f in fields if f not in kwargs]
        extras = [k for k in kwargs if k not in fields]
        if missing:
            raise KeyFieldMissing(missing[0], have=[f for f in fields if f in kwargs], key_class=cls_name)
        if extras:
            msg = f"Unknown key field(s) {extras!r} on {cls_name}; expected one of {list(fields)}"
            raise ValueError(msg)
        return tuple(str(kwargs[f]) for f in fields)

    if not args and not kwargs:
        raise KeyFieldMissing(fields[0] if fields else "name", have=[], key_class=cls_name)

    # Single arg: NamedTuple instance / tuple / list / single-string sugar.
    if len(args) == 1 and not kwargs:
        sole = args[0]
        if isinstance(sole, key_cls):
            return tuple(str(p) for p in sole)
        if isinstance(sole, tuple):
            if len(sole) != expected:
                raise KeyArityMismatch(expected=fields, got=sole, key_class=cls_name)
            return tuple(str(p) for p in sole)
        if isinstance(sole, list):
            got = tuple(sole)
            if len(got) != expected:
                raise KeyArityMismatch(expected=fields, got=got, key_class=cls_name)
            return tuple(str(p) for p in got)
        if isinstance(sole, str):
            if expected != 1:
                raise KeyArityMismatch(expected=fields, got=(sole,), key_class=cls_name)
            return (sole,)

    # Positional path: load("p", "e", "d").
    if args and not kwargs:
        if len(args) != expected:
            raise KeyArityMismatch(expected=fields, got=tuple(str(a) for a in args), key_class=cls_name)
        return tuple(str(a) for a in args)

    msg = "Cannot mix positional and keyword key arguments"
    raise TypeError(msg)


class ConnectionStore(Generic[C]):
    """Manages connection TOML files for a single `ConnectionInfo` subclass.

    Generic on the `ConnectionInfo` subclass; the key NamedTuple is derived from
    `model.Key` (same class is exposed as `store.key_class`).
    """

    def __init__(self, config_dir: Path, model: type[C]) -> None:
        self.config_dir = config_dir
        self.model = model

    @property
    def connection_class(self) -> type[C]:
        """The `ConnectionInfo` subclass this store is bound to."""
        return self.model

    @property
    def key_class(self) -> type[NamedTuple]:
        """The NamedTuple key class for this store (`model.Key`)."""
        return self.model.Key

    # -- key/path ------------------------------------------------------------

    def _filename(self, key: tuple[str, ...]) -> str:
        _validate_key(key)
        return "-".join(key) + ".toml"

    def _path(self, key: tuple[str, ...]) -> Path:
        return self.config_dir / self._filename(key)

    # -- async-first API (v0.11) ---------------------------------------------
    #
    # `save` / `load` / `list_connections` / `list_keys` are `async def`. The
    # bodies are sync (TOML files are tiny — ~1KB; the sync work runs inline,
    # no `to_thread` overhead). What async-first buys is API consistency with
    # FastMCP's tool model: tools are async, so reaching for the connection
    # store reads `await store.load(key)`. Sync callers (CLI commands, tests,
    # decoration-time enrichment) wrap one call site with `anyio.run(...)`.
    #
    # `delete` is also async for symmetry, even though its body is also sync.

    async def save(self, info: C) -> Path:
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

    async def delete(self, *args: Any, **kwargs: Any) -> None:
        """Delete a connection. Accepts the same call shapes as `load`."""
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        path.unlink()

    async def load(self, *args: Any, **kwargs: Any) -> C:
        """Load by key. See module docstring for accepted call shapes."""
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        data = tomllib.loads(path.read_text())
        data["key"] = tuple(data["key"])
        try:
            return self.model.model_validate(data)
        except ValidationError as exc:  # surface KeyArityMismatch / KeyFieldMissing
            for err in exc.errors():
                ctx = err.get("ctx", {})
                inner = ctx.get("error") if isinstance(ctx, dict) else None
                if isinstance(inner, (KeyArityMismatch, KeyFieldMissing, InvalidConnectionKey)):
                    raise inner from exc
            raise

    async def list_connections(self) -> list[C]:
        """List all valid connections in the config dir, sorted by filename."""
        if not self.config_dir.exists():
            return []
        results: list[C] = []
        for path in sorted(self.config_dir.glob("*.toml")):
            data = tomllib.loads(path.read_text())
            data["key"] = tuple(data["key"])
            results.append(self.model.model_validate(data))
        return results

    async def list_keys(self) -> list[tuple[str, ...]]:
        """List all stored keys as `model.Key` NamedTuple instances.

        Returns the typed key (e.g. `WidgetKey(project=..., env=..., db=...)`)
        rather than a raw tuple — callers iterating by index still work because
        `NamedTuple` supports indexing.
        """
        return [self.model.Key(*info.key) for info in await self.list_connections()]  # type: ignore[misc]
