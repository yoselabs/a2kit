"""v0.7 tests — StrEnum Cap, dropped info kwarg, auto-inject docs, FQN ContextVar,
A2K012 re-export resolution, A2K013, public ToolKwargs."""

from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Unpack

import pytest

import a2kit
from a2kit import Cap, ToolKwargs
from a2kit._context import _RouterContext
from a2kit.lint._ast_helpers import (
    reset_reexport_cache,
    resolve_through_reexports,
)
from a2kit.scaffold import Router
from a2kit.tools import _reset_auto_inject_cache


# ---------------------------------------------------------------------------- #
# A. Cap StrEnum semantics
# ---------------------------------------------------------------------------- #


def test_cap_is_strenum() -> None:
    """Cap is a StrEnum — values are strings, equal to their .value."""
    assert Cap.WRITE == "write"
    assert Cap.READ == "read"
    assert isinstance(Cap.WRITE, str)


def test_cap_iteration_yields_all_members() -> None:
    members = list(Cap)
    assert {m.value for m in members} == {"read", "write", "destructive", "expensive", "pii", "external"}


def test_cap_parses_raw_string() -> None:
    """`Cap('write')` returns the matching member."""
    assert Cap("write") is Cap.WRITE
    assert Cap("destructive") is Cap.DESTRUCTIVE


def test_cap_unknown_raises() -> None:
    with pytest.raises(ValueError, match="not a valid Cap"):
        Cap("nope")


def test_cap_in_set_with_string() -> None:
    """Mixing Cap members and bare strings in a set works (StrEnum hashes as str)."""
    s = {Cap.WRITE, "destructive"}
    assert "write" in s
    assert Cap.DESTRUCTIVE in s


def test_capabilities_registry_pre_registers_builtins() -> None:
    for cap in Cap:
        rec = a2kit.capabilities.get(cap.value)
        assert rec is not None
        assert rec.is_built_in is True


# ---------------------------------------------------------------------------- #
# B. Drop `info` kwarg pattern
# ---------------------------------------------------------------------------- #


def test_tool_decorator_no_info_kwarg_param() -> None:
    """`@a2kit.tool(...)` no longer accepts `info_kwarg=` (signature is sealed)."""
    import inspect as _inspect

    sig = _inspect.signature(a2kit.tool)
    assert "info_kwarg" not in sig.parameters


def test_tool_kwargs_typeddict_has_no_info_kwarg() -> None:
    """`info_kwarg` is gone from the v0.9 surface (was removed in v0.7)."""
    assert "info_kwarg" not in a2kit.ToolKwargs.__annotations__


# ---------------------------------------------------------------------------- #
# D. Auto-inject param docs at decoration time
# ---------------------------------------------------------------------------- #


def test_auto_inject_prepends_connection_param_doc() -> None:
    _reset_auto_inject_cache()

    @a2kit.tool(connection_param="conn")
    async def get_widget(conn: str) -> dict:
        """Fetch a widget."""
        return {"conn": conn}

    assert "Fetch a widget." in (get_widget.__doc__ or "")
    assert "Saved a2kit connection name" in (get_widget.__doc__ or "")


def test_auto_inject_uses_custom_cli() -> None:
    _reset_auto_inject_cache()

    @a2kit.tool(connection_param="conn", cli="a2widgets")
    async def get_widget(conn: str) -> dict:
        """Fetch a widget."""
        return {"conn": conn}

    assert "a2widgets" in (get_widget.__doc__ or "")


def test_auto_inject_skips_when_param_already_in_docstring() -> None:
    _reset_auto_inject_cache()

    @a2kit.tool(connection_param="conn")
    async def f(conn: str) -> dict:
        """Fetch — conn is already mentioned here."""
        return {"conn": conn}

    # The literal "conn" is in the existing docstring → no addition.
    doc = f.__doc__ or ""
    assert doc.count("Saved a2kit connection name") == 0


def test_auto_inject_registered_param_doc() -> None:
    _reset_auto_inject_cache()
    a2kit.docs.register_param_doc("widget_id", "ID of the widget to fetch.")
    try:

        @a2kit.tool()
        async def f(widget_id: str) -> dict:
            """Fetch."""
            return {"widget_id": widget_id}

        assert "ID of the widget to fetch." in (f.__doc__ or "")
    finally:
        a2kit.docs.clear_param_docs()


def test_auto_inject_disabled_via_pyproject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_auto_inject_cache()
    py = tmp_path / "pyproject.toml"
    py.write_text("[tool.a2kit.docs]\nauto_inject = false\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    @a2kit.tool(connection_param="conn")
    async def f(conn: str) -> dict:
        """X."""
        return {}

    assert "Saved a2kit connection name" not in (f.__doc__ or "")
    _reset_auto_inject_cache()


def test_auto_inject_pyproject_missing_key_keeps_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_auto_inject_cache()
    py = tmp_path / "pyproject.toml"
    py.write_text("[tool.a2kit]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    @a2kit.tool(connection_param="conn")
    async def f(conn: str) -> dict:
        """X."""
        return {}

    assert "Saved a2kit connection name" in (f.__doc__ or "")
    _reset_auto_inject_cache()


def test_auto_inject_pyproject_load_failure_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_auto_inject_cache()

    def boom() -> dict:
        raise RuntimeError("simulated load failure")

    import a2kit.scaffold as _sc

    monkeypatch.setattr(_sc, "_load_pyproject_a2kit", boom)

    @a2kit.tool(connection_param="conn")
    async def f(conn: str) -> dict:
        """X."""
        return {}

    # default True survives → connection-param doc is injected.
    assert "Saved a2kit connection name" in (f.__doc__ or "")
    _reset_auto_inject_cache()


def test_auto_inject_no_additions_short_circuits() -> None:
    _reset_auto_inject_cache()

    @a2kit.tool()
    async def f(x: int) -> dict:
        """No connection param, no registered docs → no additions."""
        return {"x": x}

    # Docstring unchanged.
    assert (f.__doc__ or "").strip() == "No connection param, no registered docs → no additions."


def test_auto_inject_appends_to_empty_docstring() -> None:
    _reset_auto_inject_cache()

    @a2kit.tool(connection_param="conn")
    async def f(conn: str) -> dict:  # no docstring
        return {}

    assert "Saved a2kit connection name" in (f.__doc__ or "")


# ---------------------------------------------------------------------------- #
# E. Public ToolKwargs
# ---------------------------------------------------------------------------- #


def test_tool_kwargs_typed_dict_unpack_works() -> None:
    """`Unpack[ToolKwargs]` builds a higher-order Router decorator factory."""

    class MetricsRouter(Router):
        @classmethod
        def expensive(cls, **kwargs: Unpack[ToolKwargs]) -> Any:
            existing = set(kwargs.get("capabilities", set()) or set())
            kwargs["capabilities"] = existing | {Cap.EXPENSIVE}
            return cls.tool(**kwargs)

    @MetricsRouter.expensive()
    async def heavy(scope: str) -> dict:
        return {"scope": scope}

    assert MetricsRouter._tools[-1].fn is heavy
    assert Cap.EXPENSIVE in MetricsRouter._tools[-1].capabilities


def test_tool_kwargs_omits_info_kwarg_field() -> None:
    """`info_kwarg` was removed from the public TypedDict in v0.7."""
    assert "info_kwarg" not in ToolKwargs.__optional_keys__
    assert "info_kwarg" not in ToolKwargs.__required_keys__ if hasattr(ToolKwargs, "__required_keys__") else True


# ---------------------------------------------------------------------------- #
# F. FQN-based ContextVar naming — collision-free across modules
# ---------------------------------------------------------------------------- #


def test_fqn_context_distinct_for_same_class_name(tmp_path: Path) -> None:
    """Two same-named Router classes in different modules have independent state."""
    pkg = tmp_path / "fqn_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "mod_a.py").write_text(
        textwrap.dedent("""\
            from a2kit.scaffold import Router

            class IssuesRouter(Router):
                pass
        """),
        encoding="utf-8",
    )
    (pkg / "mod_b.py").write_text(
        textwrap.dedent("""\
            from a2kit.scaffold import Router

            class IssuesRouter(Router):
                pass
        """),
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        import importlib

        mod_a = importlib.import_module("fqn_pkg.mod_a")
        mod_b = importlib.import_module("fqn_pkg.mod_b")
        ctx_a = mod_a.IssuesRouter.context
        ctx_b = mod_b.IssuesRouter.context
        # The internal ContextVar names embed the FQN — distinct per module.
        assert ctx_a._info_var.name != ctx_b._info_var.name
        assert "fqn_pkg.mod_a" in ctx_a._info_var.name
        assert "fqn_pkg.mod_b" in ctx_b._info_var.name
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("fqn_pkg", None)
        sys.modules.pop("fqn_pkg.mod_a", None)
        sys.modules.pop("fqn_pkg.mod_b", None)


def test_router_context_fqn_fallback_uses_router_name() -> None:
    """Hand-built `_RouterContext` without `fqn` falls back to bare router name."""
    ctx: _RouterContext[Any] = _RouterContext(router_name="bare")
    assert ctx._info_var.name == "_a2kit_info::bare"


def test_router_context_fqn_explicit() -> None:
    ctx: _RouterContext[Any] = _RouterContext(router_name="x", fqn="pkg.mod.X")
    assert ctx._info_var.name == "_a2kit_info::pkg.mod.X"


# ---------------------------------------------------------------------------- #
# G. A2K012 — re-export resolution + A2K013
# ---------------------------------------------------------------------------- #


def _make_pyproject_root(root: Path) -> None:
    (root / "pyproject.toml").write_text("[tool.a2kit]\n", encoding="utf-8")


def test_a2k012_resolves_through_reexport(tmp_path: Path) -> None:
    """`from pkg import NAME` where pkg/__init__.py re-exports `Final[str]` from pkg.caps."""
    reset_reexport_cache()
    _make_pyproject_root(tmp_path)
    pkg = tmp_path / "myapp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from myapp.caps import TICKETS\n", encoding="utf-8")
    (pkg / "caps.py").write_text(
        "from typing import Final\nTICKETS: Final[str] = 'tickets'\n",
        encoding="utf-8",
    )
    (pkg / "tools.py").write_text(
        "import a2kit\nfrom myapp import TICKETS\n@a2kit.tool(capabilities={TICKETS})\nasync def t() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([pkg / "tools.py"])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_flags_unresolved_reexport(tmp_path: Path) -> None:
    """Re-export chain that does NOT terminate at Final[str] gets flagged."""
    reset_reexport_cache()
    _make_pyproject_root(tmp_path)
    pkg = tmp_path / "myapp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from myapp.caps import TICKETS\n", encoding="utf-8")
    # Note: TICKETS is NOT Final[str] in caps.py — bare assignment.
    (pkg / "caps.py").write_text("TICKETS = 'tickets'\n", encoding="utf-8")
    (pkg / "tools.py").write_text(
        "import a2kit\nfrom myapp import TICKETS\n@a2kit.tool(capabilities={'tickets'})\nasync def t() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([pkg / "tools.py"])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert any("'tickets'" in m.message for m in a2k012)


def test_a2k012_reexport_max_depth(tmp_path: Path) -> None:
    """Re-export depth caps at 3 (no infinite loop on cyclic chains)."""
    reset_reexport_cache()
    pkg = tmp_path / "cyc"
    pkg.mkdir()
    # Cycle: a → b → a → b → ... cap at 3.
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("from cyc.b import X\n", encoding="utf-8")
    (pkg / "b.py").write_text("from cyc.a import X\n", encoding="utf-8")
    # Should return False without hanging.
    assert resolve_through_reexports("cyc.a", "X", tmp_path) is False
    # Cached result returns same answer.
    assert resolve_through_reexports("cyc.a", "X", tmp_path) is False


def test_a2k012_reexport_exhausts_depth_acyclic(tmp_path: Path) -> None:
    """Linear chain longer than max_depth: a→b→c→d (depth 3) — exits via for-else, returns False."""
    reset_reexport_cache()
    pkg = tmp_path / "lin"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("from lin.b import X\n", encoding="utf-8")
    (pkg / "b.py").write_text("from lin.c import X\n", encoding="utf-8")
    (pkg / "c.py").write_text("from lin.d import X\n", encoding="utf-8")
    (pkg / "d.py").write_text("from typing import Final\nX: Final[str] = 'deep'\n", encoding="utf-8")
    # max_depth=3 means we visit a, b, c then exit; d's Final is never reached.
    assert resolve_through_reexports("lin.a", "X", tmp_path) is False


def test_resolve_through_reexports_missing_module(tmp_path: Path) -> None:
    reset_reexport_cache()
    assert resolve_through_reexports("does.not.exist", "X", tmp_path) is False


def test_resolve_through_reexports_syntax_error(tmp_path: Path) -> None:
    reset_reexport_cache()
    (tmp_path / "bad.py").write_text("def !!!", encoding="utf-8")
    assert resolve_through_reexports("bad", "X", tmp_path) is False


def test_resolve_through_reexports_finds_terminal_final(tmp_path: Path) -> None:
    reset_reexport_cache()
    (tmp_path / "term.py").write_text(
        "from typing import Final\nX: Final[str] = 'v'\n",
        encoding="utf-8",
    )
    assert resolve_through_reexports("term", "X", tmp_path) is True


def test_resolve_through_reexports_walks_past_unrelated_assigns(tmp_path: Path) -> None:
    """Cover branches: Final[int] (skip), un-named target, mismatched names, alias forms."""
    reset_reexport_cache()
    # `X: Final[list[str]]` first (Final but not str-direct → skip), then `X: Final[str]`.
    # Same `name` repeats so the loop iterates past a non-matching annotation.
    (tmp_path / "many.py").write_text(
        "from typing import Final\n"
        "import sys as _sys\n"  # non-ImportFrom
        "from os import path as P\n"  # ImportFrom with asname
        "X: Final[list[str]] = []\n"  # Final but slice is Subscript, not Name(str) → continues loop
        "Y: Final[str] = 'wrong-name'\n"  # different target name → continues
        "Z = 'plain'\n"  # not AnnAssign → continues
        "X: Final[str] = 'right'\n",  # this one matches
        encoding="utf-8",
    )
    assert resolve_through_reexports("many", "X", tmp_path) is True


def test_find_reexport_uses_alias_asname(tmp_path: Path) -> None:
    """`from x import a as b` exports name `b`; the chain follows that alias."""
    reset_reexport_cache()
    pkg = tmp_path / "alias_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from alias_pkg.inner import X as RENAMED\n",
        encoding="utf-8",
    )
    (pkg / "inner.py").write_text(
        "from typing import Final\nX: Final[str] = 'v'\n",
        encoding="utf-8",
    )
    # Walking from alias_pkg with name RENAMED finds it via alias→inner.X — but
    # the inner module has X (not RENAMED). So this should return False (chain
    # ends without a matching Final). Exercises the alias path.
    assert resolve_through_reexports("alias_pkg", "RENAMED", tmp_path) is False


def test_resolve_through_reexports_module_to_path_pkg(tmp_path: Path) -> None:
    """Package form: pkg/__init__.py path."""
    reset_reexport_cache()
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from typing import Final\nX: Final[str] = 'v'\n",
        encoding="utf-8",
    )
    assert resolve_through_reexports("pkg", "X", tmp_path) is True


def test_a2k013_flags_manual_param_doc(tmp_path: Path) -> None:
    src = tmp_path / "mod.py"
    src.write_text(
        textwrap.dedent("""\
            import a2kit

            @a2kit.tool(connection_param="conn")
            async def f(conn: str) -> dict:
                f\"\"\"Fetch. {a2kit.docs.connection_param_doc()}\"\"\"
                return {}
        """),
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    # Trick the rule: it skips fixture paths. Move under a fake non-fixture root.
    fake = tmp_path / "src" / "mymod.py"
    fake.parent.mkdir()
    fake.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    findings = run_static_rules([fake])
    a2k013 = [m for m in findings if m.rule == "A2K013"]
    assert any("connection_param_doc" in m.message for m in a2k013)


def test_a2k013_skips_when_no_marker(tmp_path: Path) -> None:
    fake = tmp_path / "src" / "clean.py"
    fake.parent.mkdir()
    fake.write_text(
        'import a2kit\n@a2kit.tool()\nasync def f() -> dict:\n    """Plain."""\n    return {}\n',
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([fake])
    assert not [m for m in findings if m.rule == "A2K013"]


def test_a2k013_noqa_suppresses(tmp_path: Path) -> None:
    fake = tmp_path / "src" / "supp.py"
    fake.parent.mkdir()
    fake.write_text(
        textwrap.dedent("""\
            import a2kit

            @a2kit.tool(connection_param="conn")
            async def f(conn: str) -> dict:  # noqa: A2K013
                f\"\"\"X. {a2kit.docs.param_doc('x')}\"\"\"
                return {}
        """),
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([fake])
    assert not [m for m in findings if m.rule == "A2K013"]


def test_a2k013_skipped_under_fixture_paths(tmp_path: Path) -> None:
    """Fixture paths are skipped to avoid noise on examples/."""
    pkg = tmp_path / "examples"
    pkg.mkdir()
    src = pkg / "mod.py"
    src.write_text(
        textwrap.dedent("""\
            import a2kit

            @a2kit.tool(connection_param="conn")
            async def f(conn: str) -> dict:
                f\"\"\"X. {a2kit.docs.connection_param_doc()}\"\"\"
                return {}
        """),
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    assert not [m for m in findings if m.rule == "A2K013"]


# ---------------------------------------------------------------------------- #
# Examples sanity — v0.8 curated set (smoke-run; full E2E in `make examples`)
# ---------------------------------------------------------------------------- #


def test_tracker_demo_imports_cleanly() -> None:
    """Smoke-import the canonical demo so example regressions surface in test runs."""
    import importlib

    importlib.import_module("examples.tracker.server")
    importlib.import_module("examples.tracker.routers")
    importlib.import_module("examples.tracker.connection")


# ---------------------------------------------------------------------------- #
# Migration recipe smoke — fat decorator on Router-context only path
# ---------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_router_context_info_is_only_path() -> None:
    """The v0.7 canonical pattern — no info kwarg, only ContextVar."""

    class WidgetConn(a2kit.ConnectionInfo):
        url: str = ""

    class WRouter(Router):
        pass

    @WRouter.read(connection_param="conn")
    async def my_tool(conn: str) -> dict:
        info = WRouter.context.info()
        return {"url": info.url}

    server = type("S", (), {"tools": [], "settings": type("X", (), {})()})()

    def _t(*_a: Any, **_k: Any) -> Any:
        async def deco(fn: Any) -> Any:
            return fn

        return deco

    server.tool = _t  # type: ignore[attr-defined]

    store = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), WidgetConn)
    await store.save(WidgetConn(key=("p",), url="https://api"))
    routers = a2kit.RouterRegistry()
    routers.add(WRouter(store=store))
    routers.apply(server, store=None)

    # Pull the wrapped fn by replicating the apply path (already executed); call manually.
    wrapped = a2kit.tool(connection_param="conn", store=store, router_context=WRouter.context)(my_tool)
    assert await wrapped(conn="p") == {"url": "https://api"}
