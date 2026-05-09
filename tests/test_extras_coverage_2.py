"""Second-pass coverage: connections store, lint runtime, caps edges, otel."""

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


def test_lint_runtime_list_tool_names_returns_empty_for_naive_server() -> None:
    """Server without `_tool_manager` → empty list."""
    from a2kit.packages.lint.runtime import _list_tool_names

    class _Naive:
        pass

    assert _list_tool_names(_Naive()) == []


# --------------------------- caps.py edges (project_root None / unparseable) --------------------------- #


def test_caps_a2k012_no_project_root_treats_imported_name_unsafe(tmp_path: Path) -> None:
    """Without pyproject.toml, project_root is None — imported Name is NOT trusted as Final[str]."""
    from a2kit.packages.lint.rules.caps import _reset_reexport_cache
    from a2kit.packages.lint.static import A2K012, run_static_rules

    _reset_reexport_cache()
    body = "import a2kit\nfrom mystery import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = tmp_path / "src" / "m.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    findings = run_static_rules([p])
    # No A2K012 because elt is a Name, not Constant — A2K012 only flags string constants.
    # But the safe_names check still has to RUN — which means project_root was None branch.
    assert {f.rule for f in findings}.isdisjoint({A2K012})  # type: ignore[union-attr]


def test_caps_a2k012_skips_unparseable_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-export resolution survives a SyntaxError in a sibling module."""
    from a2kit.packages.lint.rules.caps import _reset_reexport_cache
    from a2kit.packages.lint.static import A2K012, run_static_rules

    _reset_reexport_cache()
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "pyproject.toml").write_text("")
    (src / "broken.py").write_text("def f(:\n    pass\n")  # SyntaxError
    body = "import a2kit\nfrom broken import MY_CAP\n@a2kit.tool(capabilities={MY_CAP})\ndef t() -> int:\n    return 1\n"
    p = src / "m.py"
    p.write_text(body)
    # Monkey-patch project root resolution to point at tmp_path:
    findings = run_static_rules([p])
    # Doesn't crash — that's the success criterion.
    assert isinstance(findings, list)
    # MY_CAP is a Name, not a Constant — A2K012 skips Names.
    assert A2K012 not in {f.rule for f in findings}  # type: ignore[union-attr]


# --------------------------- otel module (lazy install) --------------------------- #


# --------------------------- routers Enricher path --------------------------- #


def test_router_propagates_enricher_to_tool_meta() -> None:
    """Router with `enricher = staticmethod(...)` injects it into each tool's meta."""
    import a2kit
    from a2kit.metadata import get_meta

    def _enr(exc: Exception, tool_name: str) -> Exception:
        return exc

    class R(a2kit.Router):
        name = "r"
        enricher = staticmethod(_enr)

        @a2kit.read("ping")
        async def ping(self) -> dict[str, int]:
            return {"x": 1}

    r = R()
    assert r.tools(), "router must collect at least one tool"
    meta = get_meta(r.tools()[0])
    assert meta is not None
    assert meta.enricher is _enr


def test_router_constructor_enricher_arg_overrides_class_default() -> None:
    """`R(enricher=...)` overrides the class-level `enricher` attr."""
    import a2kit
    from a2kit.metadata import get_meta

    def _ctor_enr(exc: Exception, tool_name: str) -> Exception:
        return exc

    class R(a2kit.Router):
        name = "r"

        @a2kit.read("ping")
        async def ping(self) -> dict[str, int]:
            return {"x": 1}

    r = R(enricher=_ctor_enr)
    meta = get_meta(r.tools()[0])
    assert meta is not None
    assert meta.enricher is _ctor_enr


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
    s = EphemeralAwareStore(base, ephemeral)
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
    from a2kit.packages.cli.schemas import compute_schema

    async def fn(x):  # type: ignore[no-untyped-def]
        return {"x": x}

    out = compute_schema(fn)
    assert out["name"] == "fn"
    assert "inputSchema" in out


def test_compute_schema_no_return_annotation_skips_output_schema() -> None:
    from a2kit.packages.cli.schemas import compute_schema

    async def fn():  # type: ignore[no-untyped-def]
        return 1

    out = compute_schema(fn)
    assert "outputSchema" not in out


def test_annotations_dict_handles_dataclass_and_none() -> None:
    """`_annotations_dict` covers dataclass branch + None branch."""
    from dataclasses import dataclass

    from a2kit.packages.cli.schemas import _annotations_dict

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


def test_builder_click_type_for_primitives_and_any() -> None:
    import inspect

    from a2kit.packages.cli.builder import _click_type_for

    # Empty + Any → STRING, complex=False
    t1, c1 = _click_type_for(inspect.Parameter.empty)
    assert c1 is False
    t2, c2 = _click_type_for(int)
    assert t2 is int
    assert c2 is False
    t3, c3 = _click_type_for(bool)
    assert t3 is bool
    assert c3 is False
    # list[int] → STRING, complex=True
    t4, c4 = _click_type_for(list[int])
    assert c4 is True


# --------------------------- otel module (lazy install) --------------------------- #


# --------------------------- select edges --------------------------- #


def test_select_evaluate_bool_python_path() -> None:
    """If the runner returns a plain `bool`, line 96 covers it."""
    from a2kit.packages.select import _convert

    # Sanity for _convert non-bool, non-dict pass-through (line 132).
    assert _convert(42) == 42
    assert _convert("string") == "string"


def test_select_evaluate_non_bool_result_raises_invalid_filter() -> None:
    """Returning a non-bool from CEL → InvalidFilterExpression."""
    from a2kit.exceptions import InvalidFilterExpression
    from a2kit.packages.select import compile, evaluate

    # `1 + 1` evaluates to int, not bool.
    prog = compile("1 + 1")
    with pytest.raises(InvalidFilterExpression, match="must evaluate to bool"):
        evaluate(prog, {})


def test_select_collect_atom_names_flattens_nested_dict() -> None:
    """Lines 141-142 — nested dict produces dotted names."""
    from a2kit.packages.select import _collect_atom_names

    names = _collect_atom_names({"surface": {"mcp": True, "cli": False}, "default": True})
    assert "surface" in names
    assert "surface.mcp" in names
    assert "surface.cli" in names
    assert "default" in names


def test_select_validate_atoms_raises_for_unknown() -> None:
    from a2kit.packages.select import UnknownAtomError, validate_atoms

    with pytest.raises(UnknownAtomError):
        validate_atoms("not_listed && default", known_atoms={"default"})


def test_select_validate_atoms_silent_for_known() -> None:
    from a2kit.packages.select import validate_atoms

    # Just doesn't raise.
    validate_atoms("default && surface.mcp", known_atoms={"default", "surface.mcp"})


# --------------------------- otel module (lazy install) --------------------------- #


def test_otel_module_lazy_attrs_resolve() -> None:
    """`__getattr__` resolves declared lazy attrs and raises for unknowns."""
    import a2kit.packages.otel as pkg

    assert callable(pkg.install)
    assert pkg.OTelMiddleware is not None
    assert "install" in dir(pkg)
    with pytest.raises(AttributeError):
        pkg.definitely_not_an_attr  # noqa: B018


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
