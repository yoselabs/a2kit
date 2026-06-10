"""Mirror tests for a2kit/_lazy_module — PEP 562 helper for package front doors."""

from __future__ import annotations

import sys
import types

import pytest

from a2kit._lazy_module import lazy_attr, lazy_dir


def _fake_module(name: str, **attrs: object) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def test_lazy_attr_resolves_from_target_module():
    _fake_module("a2kit._lz_t1", THING=42)
    getter = lazy_attr("a2kit._lz_pkg", {"thing": ("a2kit._lz_t1", "THING")})
    assert getter("thing") == 42


def test_lazy_attr_resolves_module_alias():
    _fake_module("a2kit._lz_alias", marker="ok")
    getter = lazy_attr("a2kit._lz_pkg", {}, modules={"alias": "a2kit._lz_alias"})
    assert getter("alias").marker == "ok"


def test_lazy_attr_raises_default_for_unknown():
    getter = lazy_attr("a2kit._lz_pkg", {})
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        getter("missing")


def test_lazy_dir_unions_globals_and_lazy_keys():
    g = {"static_a": 1, "__name__": "pkg"}
    d = lazy_dir(g, {"lazy_b": ("m", "x")}, {"alias_c": "m"})
    out = d()
    assert "static_a" in out
    assert "lazy_b" in out
    assert "alias_c" in out
