"""Tests for a2kit.pytest_plugin — `--update-schema-snapshots` and `schema_snapshot` fixture.

Uses pytest's `pytester` to run nested pytest invocations.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


_CONFTEST = 'pytest_plugins = ["a2kit.pytest_plugin"]\n'


def test_fixture_writes_on_first_run(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_inner="""
from mcp.server.fastmcp import FastMCP

def test_snap(schema_snapshot, tmp_path):
    s = FastMCP("inner")

    @s.tool()
    def hello(name: str) -> dict:
        return {"hi": name}

    snap_dir = tmp_path / "snap"
    schema_snapshot(s, snap_dir)
    assert (snap_dir / "hello.json").exists()
"""
    )
    res = pytester.runpytest("test_inner.py")
    res.assert_outcomes(passed=1)


def test_update_flag_overwrites(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_update="""
from mcp.server.fastmcp import FastMCP

def test_snap(schema_snapshot, tmp_path):
    s = FastMCP("u")

    @s.tool()
    def hi(x: int) -> dict:
        return {"x": x}

    snap_dir = tmp_path / "snap"
    snap_dir.mkdir()
    (snap_dir / "stale.json").write_text('{"old": true}')
    schema_snapshot(s, snap_dir)
"""
    )
    res = pytester.runpytest("--update-schema-snapshots", "test_update.py")
    res.assert_outcomes(passed=1)


def test_update_cassettes_fixture(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_uc="""
def test_default_false(update_cassettes):
    assert update_cassettes is False
"""
    )
    res = pytester.runpytest("test_uc.py")
    res.assert_outcomes(passed=1)


def test_update_cassettes_fixture_true(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_uct="""
def test_truthy(update_cassettes):
    assert update_cassettes is True
"""
    )
    res = pytester.runpytest("--update-cassettes", "test_uct.py")
    res.assert_outcomes(passed=1)


def test_fixture_asserts_when_snapshot_exists(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(_CONFTEST)
    pytester.makepyfile(
        test_assertpath="""
import pytest
from mcp.server.fastmcp import FastMCP
from a2kit import SchemaSnapshotMismatch

def _server():
    s = FastMCP("a")
    @s.tool()
    def hi(x: int) -> dict:
        return {"x": x}
    return s

def test_first_run_writes(schema_snapshot, tmp_path):
    schema_snapshot(_server(), tmp_path / "s")

def test_second_run_asserts_drift(schema_snapshot, tmp_path):
    snap = tmp_path / "s"
    snap.mkdir()
    (snap / "hi.json").write_text('{"different": true}')
    with pytest.raises(SchemaSnapshotMismatch):
        schema_snapshot(_server(), snap)
"""
    )
    res = pytester.runpytest("test_assertpath.py")
    res.assert_outcomes(passed=2)
