"""ConnectionStore — TOML-backed save/load/delete/list per ConnectionConfig subclass."""

from __future__ import annotations

import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Generic, NamedTuple, TypeVar

import tomli_w

from a2kit.packages.connections.config import (
    ConnectionConfig,
    _coerce_key,
    default_config_dir,
)
from a2kit.packages.connections.exceptions import (
    ConnectionNotFound,
    InvalidConnectionKey,
    KeyArityMismatch,
    KeyFieldMissing,
)

C = TypeVar("C", bound=ConnectionConfig)


def _validate_key(key: tuple[str, ...]) -> tuple[str, ...]:
    from a2kit.packages.connections.config import _validate_key as _vk

    return _vk(key)


class ConnectionStore(Generic[C]):
    """Save/load/delete/list TOML connection records for a single ConnectionConfig subclass."""

    def __init__(self, model: type[C], config_dir: Path | None = None) -> None:
        self.model = model
        self.config_dir = config_dir if config_dir is not None else default_config_dir()

    @property
    def connection_class(self) -> type[C]:
        return self.model

    @property
    def key_class(self) -> type[NamedTuple]:
        return self.model.Key

    def _filename(self, key: tuple[str, ...]) -> str:
        _validate_key(key)
        return "-".join(key) + ".toml"

    def _path(self, key: tuple[str, ...]) -> Path:
        return self.config_dir / self._filename(key)

    async def save(self, info: C) -> Path:
        """Save atomically. Persists `info.serialize_to_disk()` (raw placeholders, never resolved)."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        # Round 8 Gotcha 1: serialize_to_disk(), NOT model_dump(); resolved secrets must
        # never reach disk on round-trip.
        data = info.serialize_to_disk()
        if "key" not in data:
            data["key"] = list(info.key)
        elif isinstance(data["key"], tuple):
            data["key"] = list(data["key"])
        for k, v in list(data.items()):
            if isinstance(v, tuple):
                data[k] = list(v)
        key_parts: tuple[str, ...] = tuple(str(k) for k in data["key"])
        path = self._path(key_parts)
        payload = tomli_w.dumps(data).encode("utf-8")

        prefix = "." + "-".join(key_parts) + "."
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
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        path.unlink()

    async def load(self, *args: Any, **kwargs: Any) -> C:
        """Load by key. ${VAR}/op:// resolved eagerly via pydantic-settings source.

        Fails fast with EnvVarNotFound / OpResolutionError when a referenced env var
        is missing or `op` cannot resolve.
        """
        key = _coerce_key(self.model, args, kwargs)
        path = self._path(key)
        if not path.exists():
            raise ConnectionNotFound(key)
        data = tomllib.loads(path.read_text())
        data["key"] = tuple(data["key"])
        try:
            return self.model(**data)
        except Exception as exc:  # propagate typed inner errors
            for inner in (KeyArityMismatch, KeyFieldMissing, InvalidConnectionKey):
                if isinstance(exc, inner):
                    raise
            raise

    async def list_connections(self) -> list[C]:
        if not self.config_dir.exists():
            return []
        results: list[C] = []
        for path in sorted(self.config_dir.glob("*.toml")):
            data = tomllib.loads(path.read_text())
            data["key"] = tuple(data["key"])
            results.append(self.model(**data))
        return results

    async def list_keys(self) -> list[tuple[str, ...]]:
        return [self.model.Key(*info.key) for info in await self.list_connections()]  # type: ignore[misc]


__all__ = ["ConnectionStore"]
