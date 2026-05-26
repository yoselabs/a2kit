"""Capability: per-request Container is a published seed; retrievable by type."""

from __future__ import annotations

from a2kit.packages.context import request_scope
from a2kit.packages.di.container import Container


def test_published_container_retrievable_by_type() -> None:
    container = Container()
    token = request_scope.publish(container)
    try:
        assert request_scope.get(Container) is container
    finally:
        request_scope.reset(token)
