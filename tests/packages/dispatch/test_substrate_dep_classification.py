"""BDD: 4th signature class for FastAPI `Depends`/`Security` (add-substrate-dep-class)."""

from __future__ import annotations

from typing import Annotated

import pytest
from fastapi import Depends, Security
from pydantic import BaseModel

import a2kit.packages.http  # noqa: F401  -- registers ApiSurface
import a2kit.packages.mcp  # noqa: F401  -- registers McpSurface
from a2kit.packages.di import Container
from a2kit.packages.dispatch import SURFACE_REGISTRY
from a2kit.packages.dispatch.substrate import (
    SubstrateSignatureError,
    install_substrate_signature,
    split_signature,
)


def _api():
    return SURFACE_REGISTRY.get("api")


def _mcp():
    return SURFACE_REGISTRY.get("mcp")


class _Memory(BaseModel):
    id: str


class _Database:
    pass


def _get_db() -> _Database:
    return _Database()


def _guard() -> str:
    return "principal"


class TestSubstrateDepClassification:
    def test_fastapi_depends_lands_in_substrate_dep_bucket(self) -> None:
        async def fetch(*, db: Annotated[_Database, Depends(_get_db)], id: str) -> _Memory:  # noqa: ARG001
            return _Memory(id=id)

        split = split_signature(fetch, _api(), Container())
        assert "db" in split.substrate_dep
        assert "id" in split.wire
        assert "db" not in split.wire
        assert "db" not in split.container

    def test_fastapi_security_lands_in_substrate_dep_bucket(self) -> None:
        async def admin(*, who: Annotated[str, Security(_guard)], id: str) -> _Memory:  # noqa: ARG001
            return _Memory(id=id)

        split = split_signature(admin, _api(), Container())
        assert "who" in split.substrate_dep
        assert "id" in split.wire

    def test_non_marker_annotated_still_wire(self) -> None:
        async def fetch(*, label: Annotated[str, "wire help text"]) -> _Memory:
            return _Memory(id=label)

        split = split_signature(fetch, _api(), Container())
        assert "label" in split.wire
        assert not split.substrate_dep

    def test_substrate_dep_on_fastmcp_install_raises(self) -> None:
        async def fetch(*, db: Annotated[_Database, Depends(_get_db)], id: str) -> _Memory:  # noqa: ARG001
            return _Memory(id=id)

        with pytest.raises(SubstrateSignatureError) as excinfo:
            install_substrate_signature(fetch, _mcp(), Container())
        msg = str(excinfo.value)
        assert "Depends" in msg or "Security" in msg
        assert "expose=" in msg

    def test_substrate_dep_passes_through_to_fastapi_signature(self) -> None:
        async def fetch(*, db: Annotated[_Database, Depends(_get_db)], id: str) -> _Memory:  # noqa: ARG001
            return _Memory(id=id)

        wrapped = install_substrate_signature(fetch, _api(), Container())
        sig_params = wrapped.__signature__.parameters  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]  # why: install_substrate_signature attaches __signature__ via setattr
        assert "db" in sig_params
        assert "id" in sig_params
        # Annotated metadata preserved so FastAPI can walk Depends marker.
        db_ann = sig_params["db"].annotation
        assert hasattr(db_ann, "__metadata__")
