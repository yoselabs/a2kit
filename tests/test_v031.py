"""Tests for v0.3.1 additions: capabilities registry, sel/SelectExpr grammar,
Router auto-tag, --select runner, configs, lint A2K008/9.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

import pytest
from pydantic import ValidationError

import a2kit
from a2kit import (
    BudgetConfig,
    Cap,
    ConnectionInfo,
    ConnectionStore,
    Router,
    RouterRegistry,
    RunnerConfig,
    SelectExpr,
    UnknownCapability,
    capabilities,
    parse_select,
    sel,
)
from a2kit._capabilities import CapabilityRecord
from a2kit._router_state import _get_active, _set_active
from a2kit._select import default_select_expr, validate_atoms
from a2kit.scaffold import MCPRunner


# ---- _capabilities ----------------------------------------------------------


def test_cap_constants() -> None:
    assert Cap.READ == "read"
    assert Cap.WRITE == "write"
    assert Cap.DESTRUCTIVE == "destructive"
    assert Cap.EXPENSIVE == "expensive"
    assert Cap.PII == "pii"
    assert Cap.EXTERNAL == "external"


def test_capabilities_namespace_all_and_known() -> None:
    snap = capabilities.all()
    assert "read" in snap
    assert "write" in snap
    assert capabilities.is_built_in("read")
    assert "read" in capabilities.known()


def test_capabilities_register_custom() -> None:
    rec = capabilities.register("tickets-management", description="ticket flows", aliases=["tm"])
    assert isinstance(rec, CapabilityRecord)
    assert rec.name == "tickets-management"
    assert rec.is_built_in is False
    assert capabilities.get("tickets-management") is not None


def test_capabilities_register_invalid_name() -> None:
    with pytest.raises(ValueError, match="must match"):
        capabilities.register("Bad-Name")


def test_capabilities_get_missing() -> None:
    assert capabilities.get("does-not-exist-xx") is None


def test_unknown_capability_with_suggestions() -> None:
    e = UnknownCapability("rea", suggestions=["read"])
    assert "Did you mean" in str(e)
    assert e.suggestions == ["read"]


def test_unknown_capability_without_suggestions() -> None:
    e = UnknownCapability("xyz")
    assert "xyz" in str(e)


# ---- _select ----------------------------------------------------------------


def test_sel_positional() -> None:
    e = sel("issues")
    assert e.op == "atom"
    assert e.atom is not None
    assert e.atom.name == "issues"
    assert e.atom.namespace is None


def test_sel_namespaced_tool() -> None:
    e = sel(tool="purge")
    assert e.atom is not None
    assert e.atom.namespace == "tool"


def test_sel_namespaced_router() -> None:
    e = sel(router="issues")
    assert e.atom is not None and e.atom.namespace == "router"


def test_sel_namespaced_cap() -> None:
    e = sel(cap=Cap.WRITE)
    assert e.atom is not None and e.atom.namespace == "cap"


def test_sel_invalid_no_args() -> None:
    with pytest.raises(TypeError):
        sel()


def test_sel_invalid_multi_args() -> None:
    with pytest.raises(TypeError):
        sel("x", tool="y")


def test_select_combinators() -> None:
    e = sel("issues") & ~sel(Cap.DESTRUCTIVE)
    assert e.op == "and"
    assert e.children[1].op == "not"


def test_select_or_combinator() -> None:
    e = sel(Cap.READ) | sel(Cap.WRITE)
    assert e.op == "or"


def test_select_evaluate_atom_match() -> None:
    e = sel("issues")
    assert e.evaluate({"issues"}) is True
    assert e.evaluate({"other"}) is False


def test_select_evaluate_tool_namespace_fallthrough() -> None:
    e = sel("purge")
    # Bare atom matches both bare tag AND `tool:<name>` form:
    assert e.evaluate({"tool:purge"}) is True


def test_select_evaluate_namespaced_match() -> None:
    e = sel(cap=Cap.WRITE)
    assert e.evaluate({"cap:write"}) is True
    assert e.evaluate({"write"}) is False


def test_select_evaluate_and_or_not() -> None:
    e = sel("a") & sel("b")
    assert e.evaluate({"a", "b"}) is True
    assert e.evaluate({"a"}) is False
    e = sel("a") | sel("b")
    assert e.evaluate({"a"}) is True
    e = ~sel("a")
    assert e.evaluate({"a"}) is False
    assert e.evaluate(set()) is True


def test_parse_select_simple() -> None:
    e = parse_select("issues and not destructive")
    assert e.op == "and"
    assert e.children[1].op == "not"


def test_parse_select_or_precedence() -> None:
    e = parse_select("a or b and c")
    # `and` binds tighter
    assert e.op == "or"
    assert e.children[1].op == "and"


def test_parse_select_parens() -> None:
    e = parse_select("(a or b) and c")
    assert e.op == "and"
    assert e.children[0].op == "or"


def test_parse_select_namespaced_atom() -> None:
    e = parse_select("tool:purge or router:issues or cap:write")
    assert e.op == "or"
    assert e.children[0].atom is not None
    assert e.children[0].atom.namespace == "tool"


def test_parse_select_unknown_namespace() -> None:
    with pytest.raises(ValueError, match="Unknown atom namespace"):
        parse_select("xyz:foo")


def test_parse_select_empty() -> None:
    with pytest.raises(ValueError, match="Empty"):
        parse_select("")


def test_parse_select_dangling_close_paren() -> None:
    with pytest.raises(ValueError, match="Unexpected token"):
        parse_select("a)")


def test_parse_select_missing_close_paren() -> None:
    with pytest.raises(ValueError, match="Expected closing"):
        parse_select("(a")


def test_parse_select_bad_char() -> None:
    with pytest.raises(ValueError, match="Unexpected character"):
        parse_select("a + b")


def test_default_select_expr() -> None:
    e = default_select_expr()
    # Default rejects tools tagged 'write':
    assert e.evaluate({"default", "read"}) is True
    assert e.evaluate({"default", "write"}) is False


def test_select_expr_shape_validation_atom_no_atom() -> None:
    with pytest.raises(ValidationError):
        SelectExpr(op="atom")


def test_select_expr_shape_validation_not_two_kids() -> None:
    a = sel("x")
    with pytest.raises(ValidationError):
        SelectExpr(op="not", children=[a, a])


def test_select_expr_shape_validation_and_one_kid() -> None:
    a = sel("x")
    with pytest.raises(ValidationError):
        SelectExpr(op="and", children=[a])


def test_validate_atoms_ok() -> None:
    e = parse_select("issues and not write")
    validate_atoms(e, known_routers={"issues"}, known_tools=set())


def test_validate_atoms_unknown() -> None:
    e = parse_select("nonexistent")
    with pytest.raises(UnknownCapability):
        validate_atoms(e, known_routers=set(), known_tools=set())


def test_validate_atoms_unknown_with_suggestion() -> None:
    e = parse_select("rea")
    with pytest.raises(UnknownCapability) as exc_info:
        validate_atoms(e, known_routers=set(), known_tools=set())
    assert "read" in exc_info.value.suggestions


# ---- Router & RouterRegistry ------------------------------------------------


class _ToolServer:
    def __init__(self) -> None:
        self.tools: list[Any] = []
        self._tool_manager = self  # acts as both

    def list_tools(self) -> list[Any]:
        return list(self.tools)

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            class _T:
                pass

            t = _T()
            t.name = fn.__name__
            t.fn = fn
            self.tools.append(t)
            return fn

        return deco


def test_router_pydantic_init() -> None:
    from typing import ClassVar

    from a2kit import Capability

    class _R(Router):
        capabilities: ClassVar[set[Capability]] = {"pii"}

    r = _R(name="issues")
    assert r.name == "issues"
    assert "pii" in _R.capabilities


def test_router_invalid_name() -> None:
    with pytest.raises(ValidationError):
        Router(name="UPPER")


def test_router_registry_add_blank_raises() -> None:
    with pytest.raises(ValidationError):
        Router(name="")


def test_router_registry_apply_auto_tags() -> None:
    server = _ToolServer()

    class IssuesRouter(Router):
        def register_read(self, server: Any, store: Any) -> None:
            @a2kit.tool(server=server)
            async def list_issues() -> dict:
                return {}

        def register_write(self, server: Any, store: Any) -> None:
            @a2kit.tool(server=server, write=True)
            async def create_issue() -> dict:
                return {}

    reg = RouterRegistry()
    reg.add(IssuesRouter(name="issues"))
    reg.apply(server, None, include_writes=True)

    names = [t.name for t in server.tools]
    assert "list_issues" in names
    assert "create_issue" in names

    # Auto-tags: list_issues should carry router name + read; create_issue → write
    list_caps = next(t for t in server.tools if t.name == "list_issues").fn._a2kit_capabilities
    assert "issues" in list_caps
    assert Cap.READ in list_caps
    create_caps = next(t for t in server.tools if t.name == "create_issue").fn._a2kit_capabilities
    assert Cap.WRITE in create_caps


def test_router_registry_decorator_form() -> None:
    reg = RouterRegistry()

    @reg.router("issues")
    class IssuesCls:
        @staticmethod
        def register_read(s: Any, _store: Any) -> None:
            s.tools.append("issues.read")

    server = _ToolServer()
    reg.apply(server, None)
    assert "issues.read" in server.tools


def test_router_registry_unknown_raises() -> None:
    reg = RouterRegistry()
    with pytest.raises(ValueError, match="Unknown"):
        reg.apply(_ToolServer(), None, enabled=["nope"])


def test_router_state_seam() -> None:
    r = Router(name="x")
    _set_active(r, "read")
    active = _get_active()
    assert active is not None
    assert active.router.name == "x"
    assert active.phase == "read"
    _set_active(None, None)
    assert _get_active() is None


def test_router_no_register_methods_skipped_via_decorator_class() -> None:
    """Router added without register_read/register_write methods just no-ops."""
    reg = RouterRegistry()
    reg.add(Router(name="empty"))  # base Router register_* are no-ops
    reg.apply(_ToolServer(), None, include_writes=True)


def test_router_registry_names() -> None:
    reg = RouterRegistry()
    reg.add(Router(name="a"))
    assert reg.names() == ["a"]


# ---- MCPRunner with --select ------------------------------------------------


class _RunServer:
    def __init__(self) -> None:
        self.settings = type("S", (), {"host": "h", "port": 1})()
        self.run_calls: list[str] = []
        self.tools: list[str] = []

    def run(self, transport: str = "stdio") -> None:
        self.run_calls.append(transport)


def test_runner_select_default() -> None:
    server = _RunServer()
    parsed = MCPRunner(server).run(argv=[])
    assert isinstance(parsed["effective_select"], SelectExpr)


def test_runner_select_string_arg() -> None:
    server = _RunServer()
    parsed = MCPRunner(server).run(argv=["--select", "default and not write"])
    assert parsed["select"] == "default and not write"


def test_runner_default_select_str_arg() -> None:
    server = _RunServer()
    runner = MCPRunner(server, default_select="default")
    assert runner.default_select.op == "atom"


def test_runner_default_select_expr_arg() -> None:
    server = _RunServer()
    runner = MCPRunner(server, default_select=sel("default"))
    assert runner.default_select.op == "atom"


def test_runner_select_with_router_registry() -> None:
    server = _RunServer()
    reg = RouterRegistry()
    visited: list[str] = []

    class A(Router):
        def register_read(self, s: Any, _: Any) -> None:
            visited.append("a.read")

    class B(Router):
        def register_read(self, s: Any, _: Any) -> None:
            visited.append("b.read")

    reg.add(A(name="a", default=True))
    reg.add(B(name="b", default=False))
    MCPRunner(server, router_registry=reg).run(argv=["--select", "router:b"])
    assert visited == ["b.read"]


def test_runner_select_default_keeps_defaults() -> None:
    server = _RunServer()
    reg = RouterRegistry()

    class A(Router):
        def register_read(self, s: Any, _: Any) -> None:
            s.tools.append("a")

    reg.add(A(name="a", default=True))
    MCPRunner(server, router_registry=reg).run(argv=[])
    assert "a" in server.tools


def test_runner_select_includes_writes_when_mentioned() -> None:
    server = _RunServer()
    reg = RouterRegistry()
    visited: list[str] = []

    class A(Router):
        def register_read(self, s: Any, _: Any) -> None:
            visited.append("read")

        def register_write(self, s: Any, _: Any) -> None:
            visited.append("write")

    reg.add(A(name="a", default=True))
    MCPRunner(server, router_registry=reg).run(argv=["--select", "a and write"])
    assert "write" in visited


# ---- Configs ----------------------------------------------------------------


def test_runner_config_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        RunnerConfig(bogus=1)  # type: ignore[call-arg]


def test_budget_config_load() -> None:
    b = BudgetConfig(per_tool={"x": 100}, total=500)
    assert b.per_tool["x"] == 100
    assert b.total == 500


# ---- ConnectionInfo NamedTuple-key validator (v0.5) ------------------------


def test_key_validator_non_namedtuple_raises() -> None:
    with pytest.raises(TypeError, match="must be a NamedTuple"):

        class _Bad(ConnectionInfo, key=tuple):  # type: ignore[arg-type]
            url: str


def test_key_validator_empty_namedtuple_raises() -> None:
    class EmptyKey(NamedTuple):
        pass

    with pytest.raises(ValueError, match="at least one field"):

        class _Bad(ConnectionInfo, key=EmptyKey):
            url: str


def test_key_fields_legacy_raises_migration_required() -> None:
    from typing import ClassVar

    from a2kit import MigrationRequired

    with pytest.raises(MigrationRequired, match="legacy"):

        class _Old(ConnectionInfo):
            KEY_FIELDS: ClassVar[tuple[str, ...]] = ("name",)
            url: str


def test_load_unwraps_validation_error_for_arity(tmp_path: Path) -> None:
    """Manually corrupted TOML triggers KeyArityMismatch (unwrapped)."""

    class _CKey(NamedTuple):
        project: str
        env: str

    class _C(ConnectionInfo, key=_CKey):
        url: str

    cfg = tmp_path / "c"
    cfg.mkdir()
    # Write a TOML file with the right filename but a wrong-arity `key` inside.
    (cfg / "p-e.toml").write_text('key = ["only"]\nurl = "x"\n')
    s: ConnectionStore[_C] = ConnectionStore(cfg, _C)
    from a2kit.exceptions import KeyArityMismatch

    with pytest.raises(KeyArityMismatch):
        s.load(("p", "e"))


# ---- Capability merging in tool decorator -----------------------------------


def test_tool_capabilities_merges_authors() -> None:
    @a2kit.tool(capabilities={Cap.PII, "tickets"})
    async def my_tool() -> dict:
        return {}

    caps = my_tool._a2kit_capabilities  # type: ignore[attr-defined]
    assert Cap.PII in caps
    assert "tickets" in caps
    # No active router → still gets 'default' tag and tool:<name>:
    assert "default" in caps
    assert "tool:my_tool" in caps


def test_tool_capabilities_with_active_router() -> None:
    from typing import ClassVar

    from a2kit import Capability

    class _R(Router):
        capabilities: ClassVar[set[Capability]] = {"pii"}

    r = _R(name="issues")
    _set_active(r, "read")
    try:

        @a2kit.tool()
        async def x() -> dict:
            return {}

        caps = x._a2kit_capabilities  # type: ignore[attr-defined]
        assert "issues" in caps
        assert "pii" in caps
        assert Cap.READ in caps
        assert "router:issues" in caps
    finally:
        _set_active(None, None)


def test_tool_write_flag_adds_write_cap() -> None:
    @a2kit.tool(write=True)
    async def f() -> dict:
        return {}

    assert Cap.WRITE in f._a2kit_capabilities  # type: ignore[attr-defined]


def test_tool_capabilities_router_auto_tag_off() -> None:
    """`Router(auto_tag=False)` does NOT add the router name to tool caps."""
    r = Router(name="silent", auto_tag=False, default=False)
    _set_active(r, "read")
    try:

        @a2kit.tool()
        async def x() -> dict:
            return {}

        caps = x._a2kit_capabilities  # type: ignore[attr-defined]
        assert "silent" not in caps
        assert "router:silent" not in caps
        assert "default" not in caps
    finally:
        _set_active(None, None)


def test_tool_capabilities_router_phase_unknown() -> None:
    """If `phase` is set to something other than 'read'/'write' the branch falls through."""
    r = Router(name="weird", default=False)
    _set_active(r, "configure")  # synthetic phase, not 'read'/'write'
    try:

        @a2kit.tool()
        async def x() -> dict:
            return {}

        caps = x._a2kit_capabilities  # type: ignore[attr-defined]
        assert Cap.READ not in caps
        assert Cap.WRITE not in caps
    finally:
        _set_active(None, None)


# ---- Coverage: edge branches ------------------------------------------------


def test_load_unwraps_validation_error_passthrough(tmp_path: Path) -> None:
    """If ValidationError doesn't carry a key-related inner, original re-raises."""

    class _C(ConnectionInfo):
        url: str  # required field — missing it triggers a different ValidationError

    cfg = tmp_path / "c"
    cfg.mkdir()
    (cfg / "n.toml").write_text('key = ["n"]\n')  # missing `url` field
    s: ConnectionStore[_C] = ConnectionStore(cfg, _C)
    with pytest.raises(ValidationError):
        s.load("n")


def test_runner_select_invalid_atom_logged_silently() -> None:
    """validate_atoms raising shouldn't crash the runner (best-effort post-hoc)."""
    server = _RunServer()
    reg = RouterRegistry()
    reg.add(Router(name="a", default=True))
    # `bogus_atom` — unknown — should be tolerated; the lint rule covers it.
    MCPRunner(server, router_registry=reg).run(argv=["--select", "a or bogus_atom"])


def test_runner_explicit_positive_no_match_falls_back() -> None:
    """If --select mentions only routers we don't have, fall back to defaults."""
    server = _RunServer()
    reg = RouterRegistry()
    reg.add(Router(name="a", default=True))
    # `router:nonexistent` doesn't exist; we should still register defaults.
    MCPRunner(server, router_registry=reg).run(argv=["--select", "router:nonexistent"])


# ---- Lint A2K008/A2K009 -----------------------------------------------------


def test_lint_a2k009_raw_capability_string(tmp_path: Path) -> None:
    """A2K009 — flag `capabilities={'write'}` raw string."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool(capabilities={'write'})\nasync def f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K009" for f in findings)


def test_lint_a2k009_silent_for_custom_cap(tmp_path: Path) -> None:
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool(capabilities={'tickets-management'})\nasync def f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K009" for f in findings)


def test_lint_a2k009_noqa_suppression(tmp_path: Path) -> None:
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool(capabilities={'write'})  # noqa: A2K009\nasync def f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K009" for f in findings)


def test_lint_a2k008_collision_router_and_tool(tmp_path: Path) -> None:
    """A2K008 — router named 'foo' AND tool named 'foo' collide."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\nfrom a2kit import Router\nrouter = Router(name='foo')\n@a2kit.tool()\nasync def foo() -> dict:\n    return {}\n"
    )
    findings = run_static_rules([src])
    assert any(f.rule == "A2K008" for f in findings)


def test_lint_a2k008_collision_with_builtin_cap(tmp_path: Path) -> None:
    """A2K008 — router named 'write' collides with built-in capability."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("from a2kit import Router\nrouter = Router(name='write')\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K008" and "write" in f.message for f in findings)


def test_lint_a2k008_class_attribute_router_name(tmp_path: Path) -> None:
    """A2K008 — picks up `class Foo(Router): name = 'x'` declarations too."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\nclass IssuesRouter(a2kit.Router):\n    name = 'foo'\n@a2kit.tool()\nasync def foo() -> dict:\n    return {}\n"
    )
    findings = run_static_rules([src])
    assert any(f.rule == "A2K008" for f in findings)


def test_lint_a2k008_disabled_via_kwarg(tmp_path: Path) -> None:
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("from a2kit import Router\nrouter = Router(name='write')\n")
    findings = run_static_rules([src], disabled=["A2K008"])
    assert not any(f.rule == "A2K008" for f in findings)


def test_lint_a2k008_skipped_in_fixture_path(tmp_path: Path) -> None:
    """Tests/examples paths are skipped for A2K008 (they often define throwaway routers)."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "tests" / "test_x.py"
    src.parent.mkdir(parents=True)
    src.write_text("from a2kit import Router\nrouter = Router(name='write')\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K008" for f in findings)


def test_lint_a2k009_skips_non_iterable_capabilities(tmp_path: Path) -> None:
    """`capabilities=some_var` (non-literal) is skipped silently."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\nCAPS = {'write'}\n@a2kit.tool(capabilities=CAPS)\nasync def f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert not any(f.rule == "A2K009" for f in findings)


def test_a2kit_config_home_alias() -> None:
    assert a2kit.A2KIT_CONFIG_HOME == "A2KIT_CONFIG_HOME"
    assert a2kit.ENV_CONFIG_HOME == "A2KIT_CONFIG_HOME"


def test_lint_a2k008_explicit_tool_name(tmp_path: Path) -> None:
    """A2K008 — `@a2kit.tool(tool_name='collide')` collides with router 'collide'."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "from a2kit import Router\n"
        "router = Router(name='collide')\n"
        "@a2kit.tool(tool_name='collide')\n"
        "async def real_name() -> dict:\n"
        "    return {}\n"
    )
    findings = run_static_rules([src])
    assert any(f.rule == "A2K008" for f in findings)


def test_lint_a2k009_mixed_set_with_non_string(tmp_path: Path) -> None:
    """A set literal mixing str + int — _iter_string_literals branches over non-str."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("import a2kit\n@a2kit.tool(capabilities={'write', 1})\nasync def f() -> dict:\n    return {}\n")
    findings = run_static_rules([src])
    assert any(f.rule == "A2K009" for f in findings)


def test_lint_a2k008_class_with_non_name_assignments(tmp_path: Path) -> None:
    """Class body containing non-name targets / non-Constant values — covers branch."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text(
        "import a2kit\n"
        "class IssuesRouter(a2kit.Router):\n"
        "    name = 'foo'\n"
        "    other = 1 + 2  # non-Constant value\n"
        "    a, b = 1, 2  # tuple target (non-Name target)\n"
        "    def method(self): pass  # FunctionDef inside body\n"
    )
    findings = run_static_rules([src])
    assert isinstance(findings, list)


def test_lint_a2k008_skips_non_call_decorator(tmp_path: Path) -> None:
    """A bare `@some_func` decorator (no call) is ignored — covers the `if not isinstance(dec, ast.Call)` branch."""
    from a2kit.lint.static import run_static_rules

    src = tmp_path / "src" / "mod.py"
    src.parent.mkdir(parents=True)
    src.write_text("from functools import lru_cache\n@lru_cache\ndef f() -> int:\n    return 1\n")
    findings = run_static_rules([src])
    # No A2K008 collisions here; just ensures the path is exercised.
    assert all(f.rule != "A2K008" for f in findings)
