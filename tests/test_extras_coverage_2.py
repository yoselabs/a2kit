"""Second-pass coverage: connections store, lint runtime, otel."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from a2kit.packages.connections.exceptions import ConnectionNotFound
from a2kit.packages.connections.store import ConnectionStore
from tests.packages.connections.conftest import WidgetConfig


# --------------------------- ConnectionStore property/branch coverage --------------------------- #


def test_connection_store_properties_expose_model(tmp_path: Path) -> None:
    store = ConnectionStore(WidgetConfig, tmp_path)
    assert store.connection_class is WidgetConfig
    assert store.key_class is WidgetConfig.Key  # type: ignore[attr-defined]


def test_connection_store_load_missing_raises_connection_not_found(tmp_path: Path) -> None:
    store = ConnectionStore(WidgetConfig, tmp_path)
    with pytest.raises(ConnectionNotFound):
        asyncio.run(store.load(name="missing"))


def test_connection_store_delete_missing_raises_connection_not_found(tmp_path: Path) -> None:
    store = ConnectionStore(WidgetConfig, tmp_path)
    with pytest.raises(ConnectionNotFound):
        asyncio.run(store.delete(name="missing"))


def test_connection_store_list_when_dir_does_not_exist(tmp_path: Path) -> None:
    """`config_dir` doesn't exist → returns []."""
    store = ConnectionStore(WidgetConfig, tmp_path / "never-created")
    assert asyncio.run(store.list_connections()) == []


def test_connection_store_save_and_round_trip(tmp_path: Path) -> None:
    """Cover save() success path + load() success path + list_keys()."""
    store = ConnectionStore(WidgetConfig, tmp_path)
    info = WidgetConfig(key=("prod",), token="literal-secret")
    path = asyncio.run(store.save(info))
    assert path.exists()
    loaded = asyncio.run(store.load(name="prod"))
    assert loaded.token == "literal-secret"
    keys = asyncio.run(store.list_keys())
    assert keys == [("prod",)]


# --------------------------- lint.runtime A2KR* checks --------------------------- #


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeToolManager:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    def list_tools(self) -> list[_FakeTool]:
        return [_FakeTool(n) for n in self._names]


class _FakeServer:
    def __init__(self, names: list[str]) -> None:
        self._tool_manager = _FakeToolManager(names)


def test_lint_runtime_check_snapshot_presence_reports_missing(tmp_path: Path) -> None:
    from a2kit.packages.lint.runtime import check_snapshot_presence

    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "ping.json").write_text("{}")
    server = _FakeServer(["ping", "missing_tool"])
    findings = list(check_snapshot_presence(server, {"snapshot_dir": str(snap)}))
    assert any("missing_tool" in f.target for f in findings)
    assert all(f.target != "ping" for f in findings)


def test_lint_runtime_check_snapshot_presence_no_dir_returns_empty() -> None:
    from a2kit.packages.lint.runtime import check_snapshot_presence

    server = _FakeServer(["x"])
    assert list(check_snapshot_presence(server, {})) == []


def test_lint_runtime_check_per_tool_budget_flags_oversized(tmp_path: Path) -> None:
    from a2kit.packages.lint.runtime import check_per_tool_budget

    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "fat.json").write_text("x" * 1000)
    server = _FakeServer(["fat", "thin"])
    findings = list(
        check_per_tool_budget(
            server,
            {"snapshot_dir": str(snap), "budgets": {"fat": 100, "thin": 100}},
        )
    )
    assert any("fat" in f.target for f in findings)


def test_lint_runtime_check_per_tool_budget_skips_when_no_budgets() -> None:
    from a2kit.packages.lint.runtime import check_per_tool_budget

    server = _FakeServer(["x"])
    assert list(check_per_tool_budget(server, {"snapshot_dir": "/tmp"})) == []


def test_lint_runtime_check_per_tool_budget_skips_unknown_tool(tmp_path: Path) -> None:
    from a2kit.packages.lint.runtime import check_per_tool_budget

    snap = tmp_path / "snap"
    snap.mkdir()
    server = _FakeServer(["x"])
    # No file for x — silently skip.
    findings = list(check_per_tool_budget(server, {"snapshot_dir": str(snap), "budgets": {"x": 100}}))
    assert findings == []


def test_lint_runtime_check_total_budget_flags_overrun(tmp_path: Path) -> None:
    from a2kit.packages.lint.runtime import check_total_budget

    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "a.json").write_text("x" * 600)
    (snap / "b.json").write_text("x" * 600)
    server = _FakeServer([])
    findings = list(check_total_budget(server, {"snapshot_dir": str(snap), "total_budget": 1000}))
    assert len(findings) == 1
    assert "exceeds" in findings[0].message


def test_lint_runtime_check_total_budget_skips_when_dir_missing(tmp_path: Path) -> None:
    from a2kit.packages.lint.runtime import check_total_budget

    server = _FakeServer([])
    assert list(check_total_budget(server, {"snapshot_dir": str(tmp_path / "nope"), "total_budget": 1000})) == []


def test_lint_runtime_check_total_budget_skips_when_no_total() -> None:
    from a2kit.packages.lint.runtime import check_total_budget

    server = _FakeServer([])
    assert list(check_total_budget(server, {"snapshot_dir": "/tmp"})) == []


def test_lint_runtime_check_similar_tool_names_flags_close_pair() -> None:
    from a2kit.packages.lint.runtime import check_similar_tool_names

    server = _FakeServer(["fetch_user", "fetch_users", "delete_account"])
    findings = list(check_similar_tool_names(server, {}))
    assert any("fetch_user" in f.target and "fetch_users" in f.target for f in findings)


def test_lint_runtime_check_message_format_concise() -> None:
    from a2kit.packages.lint.runtime import CheckMessage

    msg = CheckMessage(rule="A2KR999", target="foo", message="bad")
    assert msg.format_concise() == "foo: A2KR999 bad"


def test_lint_runtimelist_tool_names_returns_empty_for_naive_server() -> None:
    """Server without `_tool_manager` → empty list."""
    from a2kit.packages.lint.runtime import list_tool_names

    class _Naive:
        pass

    assert list_tool_names(_Naive()) == []


# --------------------------- otel module (lazy install) --------------------------- #


# --------------------------- connections.filters --------------------------- #


def test_scope_filter_returns_base_store_for_none_scope(tmp_path: Path) -> None:
    from a2kit.packages.connections.filters import scope_filter

    base = ConnectionStore(WidgetConfig, tmp_path)
    assert scope_filter(base, None) is base


def test_filtered_store_load_blocks_keys_without_scope(tmp_path: Path) -> None:
    from a2kit.packages.connections.filters import FilteredStore

    base = ConnectionStore(WidgetConfig, tmp_path)
    fs = FilteredStore(base, "prod")
    with pytest.raises(ConnectionNotFound):
        asyncio.run(fs.load(("dev",)))


def test_filtered_store_list_filters_by_scope(tmp_path: Path) -> None:
    from a2kit.packages.connections.filters import FilteredStore

    base = ConnectionStore(WidgetConfig, tmp_path)
    asyncio.run(base.save(WidgetConfig(key=("prod",), token="t1")))
    asyncio.run(base.save(WidgetConfig(key=("dev",), token="t2")))
    fs = FilteredStore(base, "prod")
    listed = asyncio.run(fs.list_connections())
    assert [tuple(i.key) for i in listed] == [("prod",)]
    assert fs.config_dir == tmp_path


def test_ephemeral_aware_store_short_circuits_to_ephemeral(tmp_path: Path) -> None:
    from a2kit.packages.connections.filters import EphemeralAwareStore

    base = ConnectionStore(WidgetConfig, tmp_path)
    ephemeral = {("eph",): WidgetConfig(key=("eph",), token="ephemeral-token")}
    s = EphemeralAwareStore(base, ephemeral)  # ty: ignore[invalid-argument-type]  # why: ty's narrowed parameter type rejects this call; runtime accepts duck-typed/stub argument
    info = asyncio.run(s.load(("eph",)))
    assert info.token == "ephemeral-token"


def test_ephemeral_aware_store_falls_through_to_base_load(tmp_path: Path) -> None:
    from a2kit.packages.connections.filters import EphemeralAwareStore

    base = ConnectionStore(WidgetConfig, tmp_path)
    asyncio.run(base.save(WidgetConfig(key=("real",), token="rt")))
    s = EphemeralAwareStore(base, {})
    info = asyncio.run(s.load(("real",)))
    assert info.token == "rt"


def test_ephemeral_aware_store_no_base_raises_not_found() -> None:
    from a2kit.packages.connections.filters import EphemeralAwareStore

    s = EphemeralAwareStore(None, {})
    with pytest.raises(ConnectionNotFound):
        asyncio.run(s.load(("anywhere",)))


def test_ephemeral_aware_store_list_merges_unique() -> None:
    from a2kit.packages.connections.filters import EphemeralAwareStore

    class _Base:
        async def list_connections(self) -> list[Any]:
            return [WidgetConfig(key=("real",), token="t")]

    s = EphemeralAwareStore(_Base(), {("eph",): WidgetConfig(key=("eph",), token="e")})
    out = asyncio.run(s.list_connections())
    keys = sorted(tuple(i.key) for i in out)
    assert keys == [("eph",), ("real",)]


def test_ephemeral_aware_store_list_no_base() -> None:
    from a2kit.packages.connections.filters import EphemeralAwareStore

    s = EphemeralAwareStore(None, {("eph",): WidgetConfig(key=("eph",), token="e")})
    out = asyncio.run(s.list_connections())
    assert [tuple(i.key) for i in out] == [("eph",)]


# --------------------------- otel module (lazy install) --------------------------- #


# --------------------------- cli/schemas helpers --------------------------- #


def test_compute_schema_handles_param_with_no_annotation() -> None:
    """`_annotation_to_field` Any-fallback branch when param has no annotation."""
    from a2kit.schema import compute_schema

    async def fn(x):  # type: ignore[no-untyped-def]
        return {"x": x}

    out = compute_schema(fn)
    assert out["name"] == "fn"
    assert "inputSchema" in out


def test_compute_schema_no_return_annotation_skips_output_schema() -> None:
    from a2kit.schema import compute_schema

    async def fn():  # type: ignore[no-untyped-def]
        return 1

    out = compute_schema(fn)
    assert "outputSchema" not in out


def test_annotations_dict_handles_dataclass_and_none() -> None:
    """`_annotations_dict` covers dataclass branch + None branch."""
    from dataclasses import dataclass

    from a2kit.schema import _annotations_dict

    @dataclass
    class _A:
        x: int = 1

    assert _annotations_dict(_A()) == {"x": 1}
    assert _annotations_dict(None) == {}
    # Plain object — falls through final return {}.
    assert _annotations_dict(object()) == {}


# --------------------------- cli/builder edge cases --------------------------- #


def test_builder_strip_optional_returns_inner_type() -> None:
    from typing import Optional, Union

    from a2kit.packages.cli.builder import _strip_optional

    assert _strip_optional(int | None) is int
    assert _strip_optional(Optional[str]) is str  # noqa: UP007
    assert _strip_optional(Union[float, None]) is float  # noqa: UP007
    # Multi-non-None union → returned unchanged.
    multi = int | str | None
    assert _strip_optional(multi) == multi
    # Non-union returned unchanged.
    assert _strip_optional(int) is int


def test_builder_needs_json_decode_primitives_and_complex() -> None:
    """``_needs_json_decode`` returns False for primitives, True for complex types."""
    import inspect

    from a2kit.packages.cli.builder import _needs_json_decode

    assert _needs_json_decode(inspect.Parameter.empty) is False
    assert _needs_json_decode(int) is False
    assert _needs_json_decode(bool) is False
    assert _needs_json_decode(str) is False
    assert _needs_json_decode(float) is False
    # Complex types get JSON-decode treatment.
    assert _needs_json_decode(list[int]) is True
    assert _needs_json_decode(dict[str, int]) is True


# --------------------------- otel module (lazy install) --------------------------- #


def test_otel_module_lazy_attrs_resolve() -> None:
    """`__getattr__` resolves declared lazy attrs."""
    import a2kit.packages.otel as pkg

    assert callable(pkg.install)
    assert pkg.OTelMiddleware is not None
    assert "install" in dir(pkg)


def test_otel_module_does_not_eagerly_import_opentelemetry() -> None:
    """Importing the package must NOT pull in opentelemetry — that's the cold-start guarantee."""
    import subprocess
    import sys

    out = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import sys; import a2kit.packages.otel; print('opentelemetry' in sys.modules)",
        ],
        text=True,
    )
    assert out.strip() == "False"
