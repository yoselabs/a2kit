"""ConnectionConfig — pydantic-settings BaseSettings with eager ${VAR} / op:// resolution.

Round 8 Gotcha 1: `_raw: PrivateAttr` shadow preserves the original placeholder strings;
`serialize_to_disk()` returns that raw form. `ConnectionStore.save` MUST call
`serialize_to_disk()` so round-trips never persist resolved secret values.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from pydantic import Field, PrivateAttr, ValidationError, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from a2kit.packages.connections._validation import (
    validate_key as _validate_key,
)
from a2kit.packages.connections.exceptions import (
    KeyArityMismatch,
    KeyFieldMissing,
)
from a2kit.packages.connections.tokens import resolve_value

ENV_CONFIG_HOME = "A2KIT_CONFIG_HOME"
DEFAULT_CONFIG_SUBDIR = Path(".config") / "a2kit" / "connections"


class _DefaultKey(NamedTuple):
    name: str


def _is_namedtuple_class(obj: object) -> bool:
    return isinstance(obj, type) and issubclass(obj, tuple) and hasattr(obj, "_fields")


def default_config_dir() -> Path:
    """Honour `A2KIT_CONFIG_HOME`; otherwise `~/.config/a2kit/connections/`."""
    override = os.environ.get(ENV_CONFIG_HOME)
    if override:
        return Path(override)
    return Path.home() / DEFAULT_CONFIG_SUBDIR


class _EagerSubstitutionSource(PydanticBaseSettingsSource):
    """Top-level string substitution via the resolve_value(${VAR} | op:// | literal) chain.

    Round 9 B10: only top-level string fields are walked; list/dict-internal placeholders
    are not recursed (acceptable limitation, lint rule A2K-CONN-LIST-PLACEHOLDER).
    """

    def __init__(self, settings_cls: type[BaseSettings], init_kwargs: dict[str, Any]) -> None:
        super().__init__(settings_cls)
        self._init_kwargs = init_kwargs

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:  # noqa: ARG002
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, value in self._init_kwargs.items():
            if isinstance(value, str):
                out[name] = resolve_value(value)
            else:
                out[name] = value
        return out


class ConnectionConfig(BaseSettings):
    """Base connection record. Subclass and add domain fields; declare `key=NamedTuple`."""

    model_config = SettingsConfigDict(extra="forbid")

    key: tuple[str, ...] = Field(min_length=1)

    Key: ClassVar[type[NamedTuple]] = _DefaultKey

    _raw: dict[str, Any] = PrivateAttr(default_factory=dict)

    def __init__(self, **data: Any) -> None:
        # Capture raw init kwargs BEFORE pydantic-settings resolves ${VAR}/op:// — this is
        # what serialize_to_disk() returns, so save/load never persists resolved secrets.
        raw = dict(data)
        super().__init__(**data)
        # Normalize key in raw to list (TOML-friendly) and capture only fields that were
        # actually passed; resolved fields go through model_validate path during load.
        if "key" in raw and isinstance(raw["key"], tuple):
            raw["key"] = list(raw["key"])
        object.__setattr__(self, "_raw", raw)

    @classmethod
    def settings_customise_sources(  # type: ignore[override]
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Wrap init_kwargs through eager substitution; users still get env/dotenv/secret
        # sources for completeness so cloud-secret backends compose without forking.
        init_kwargs = getattr(init_settings, "init_kwargs", None) or {}
        substitution = _EagerSubstitutionSource(settings_cls, init_kwargs)
        return (substitution, env_settings, dotenv_settings, file_secret_settings)

    def __init_subclass__(cls, *, key: type[NamedTuple] | None = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
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
        fields = cls._key_field_names()
        if isinstance(v, dict):
            missing = [f for f in fields if f not in v]
            if missing:
                raise KeyFieldMissing(missing[0], have=[str(k) for k in v], key_class=cls.Key.__name__)
            return tuple(str(v[f]) for f in fields)
        if isinstance(v, list):
            return tuple(str(p) for p in v)
        if isinstance(v, tuple):
            return tuple(str(p) for p in v)
        return v

    @field_validator("key")
    @classmethod
    def _validate_key_arity(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        v = _validate_key(v)
        fields = cls._key_field_names()
        if len(v) != len(fields):
            raise KeyArityMismatch(expected=fields, got=v, key_class=cls.Key.__name__)
        return v

    @property
    def filename(self) -> str:
        return "-".join(self.key) + ".toml"

    def serialize_to_disk(self) -> dict[str, Any]:
        """Return the raw kwargs as captured at construction. Preserves placeholders."""
        out = dict(self._raw)
        if "key" in out and isinstance(out["key"], tuple):
            out["key"] = list(out["key"])
        return out


def _coerce_key(  # noqa: C901, PLR0912
    model: type[ConnectionConfig],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[str, ...]:
    """Resolve `load(...)` / `delete(...)` arguments into a validated key tuple."""
    key_cls = model.Key
    fields = tuple(key_cls._fields)  # type: ignore[attr-defined]
    expected = len(fields)
    cls_name = key_cls.__name__

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

    if args and not kwargs:
        if len(args) != expected:
            raise KeyArityMismatch(expected=fields, got=tuple(str(a) for a in args), key_class=cls_name)
        return tuple(str(a) for a in args)

    msg = "Cannot mix positional and keyword key arguments"
    raise TypeError(msg)


__all__ = [
    "ENV_CONFIG_HOME",
    "ConnectionConfig",
    "ValidationError",
    "_coerce_key",
    "default_config_dir",
]
