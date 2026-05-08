"""v0.6 tests — Router auto-name, decorators, ContextVar, multi-store, A2K012."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

import a2kit
from a2kit._router_decorators import _make_decorator, _ToolBinding
from a2kit.scaffold import Router, _parse_multistore_register, _slugify


class _FakeServer:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self.settings = type("S", (), {"host": "h", "port": 1})()

    def tool(self, *_a: Any, **_kw: Any) -> Any:
        def deco(fn: Any) -> Any:
            self.tools.append(fn.__name__)
            return fn

        return deco

    def run(self, transport: str = "stdio") -> None:  # noqa: ARG002
        return


class _Conn(a2kit.ConnectionInfo):
    url: str = ""


# --- A. Auto-name -----------------------------------------------------------


def test_slugify_strips_router_suffix():
    assert _slugify("WidgetsRouter") == "widgets"
    assert _slugify("JiraConfluenceRouter") == "jira-confluence"
    assert _slugify("Router") == ""
    assert _slugify("Widgets") == "widgets"


def test_router_auto_name_from_class():
    class WidgetsRouter(Router):
        pass

    r = WidgetsRouter()
    assert r.name == "widgets"


def test_router_auto_name_camel():
    class JiraConfluenceRouter(Router):
        pass

    r = JiraConfluenceRouter()
    assert r.name == "jira-confluence"


def test_router_explicit_name_overrides():
    class WidgetsRouter(Router):
        pass

    r = WidgetsRouter(name="custom-slug")
    assert r.name == "custom-slug"


def test_router_invalid_explicit_name_raises():
    class XRouter(Router):
        pass

    with pytest.raises(Exception):  # noqa: B017, PT011
        XRouter(name="BadSlug!")


def test_router_no_class_name_falls_back_validation():
    # Bare `Router()` would slug to "" and fail validation.
    with pytest.raises(Exception):  # noqa: B017, PT011
        Router()


# --- B. Decorators + walking _tools ----------------------------------------


def test_decorators_record_bindings_in_subclass_only():
    class ARouter(Router):
        pass

    class BRouter(Router):
        pass

    @ARouter.read(connection_param="conn")
    async def fn_a(conn: str) -> dict:
        return {"a": conn}

    @BRouter.write()
    async def fn_b() -> dict:
        return {"b": True}

    assert len(ARouter._tools) == 1
    assert len(BRouter._tools) == 1
    assert ARouter._tools[0].mode == "read"
    assert BRouter._tools[0].mode == "write"


def test_router_tool_decorator_primitive():
    class CRouter(Router):
        pass

    @CRouter.tool(capabilities={"custom-cap"})
    async def fn(x: int) -> dict:
        return {"x": x}

    assert CRouter._tools[0].mode == "tool"
    assert "custom-cap" in CRouter._tools[0].capabilities


def test_default_register_walks_tools():
    class WRouter(Router):
        pass

    @WRouter.read()
    async def list_things() -> list:
        return []

    @WRouter.write()
    async def create_thing() -> dict:
        return {}

    server = _FakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(WRouter())
    routers.apply(server, store=None, include_writes=True)
    assert "list_things" in server.tools
    assert "create_thing" in server.tools


def test_imperative_register_read_override_wins():
    class IRouter(Router):
        pass

    @IRouter.read()
    async def from_decorator() -> list:
        return []

    class IRouter2(Router):
        def register_read(self, server: Any, store: Any) -> None:  # noqa: ARG002
            @a2kit.tool(server=server)
            async def imperative_tool() -> dict:
                return {}

    server = _FakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(IRouter2())
    routers.apply(server, store=None)
    assert "imperative_tool" in server.tools


# --- C. Router-level DI ----------------------------------------------------


async def test_router_di_inherits_to_tools():
    class DRouter(Router):
        pass

    @DRouter.read(connection_param="conn")
    async def get_thing(conn: str) -> dict:
        return {"conn": conn}

    server = _FakeServer()
    store = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    await store.save(_Conn(key=("prod",), url="https://api"))

    routers = a2kit.RouterRegistry()
    routers.add(DRouter(store=store))
    routers.apply(server, store=None)
    assert "get_thing" in server.tools


# --- E. ContextVar accessor ------------------------------------------------


@pytest.mark.asyncio
async def test_context_info_returns_typed_value():
    class ECRouter(Router):
        pass

    @ECRouter.read(connection_param="conn")
    async def my_tool(conn: str) -> dict:
        info = ECRouter.context.info()
        return {"url": info.url}

    server = _FakeServer()
    store = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    await store.save(_Conn(key=("prod",), url="https://api"))

    routers = a2kit.RouterRegistry()
    routers.add(ECRouter(store=store))
    routers.apply(server, store=None)

    # `my_tool` was wrapped by @a2kit.tool; the wrapper is the original `fn` in
    # the binding — but the decorator returned the original fn. To invoke the
    # wrapped version, we drive through the Router.apply path which assigned
    # @a2kit.tool(...) to fn during registration. That registered version is
    # `_FakeServer.tools` only by name. Easier: build manually.
    wrapped = a2kit.tool(connection_param="conn", store=store, router_context=ECRouter.context)(my_tool)
    result = await wrapped(conn="prod")
    assert result == {"url": "https://api"}


def test_context_info_outside_tool_raises():
    class FRouter(Router):
        pass

    with pytest.raises(RuntimeError, match="outside an active tool"):
        FRouter.context.info()


# --- F. Multi-store --------------------------------------------------------


def test_routers_with_stores():
    class WidgetsRouter(Router):
        pass

    class GadgetsRouter(Router):
        pass

    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    s2 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    routers = a2kit.RouterRegistry()
    routers.add(WidgetsRouter(store=s1))
    routers.add(GadgetsRouter(store=s2))
    pairs = routers.routers_with_stores()
    assert dict(pairs) == {"widgets": s1, "gadgets": s2}


def test_multistore_register_namespaced():
    class WidgetsRouter(Router):
        pass

    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    s2 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    args = ["--register", "widgets:prod", "url=https://w", "--register", "gadgets:prod", "url=https://g"]
    out = _parse_multistore_register(args, {"widgets": s1, "gadgets": s2})
    assert ("prod",) in out
    # both shared the same key tuple — last wins; assert at least one survived.
    assert out[("prod",)].url in {"https://w", "https://g"}


def test_multistore_register_bare_form_raises():
    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    s2 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    args = ["--register", "prod", "url=x"]
    with pytest.raises(ValueError, match="ambiguous"):
        _parse_multistore_register(args, {"a": s1, "b": s2})


def test_multistore_register_unknown_router_raises():
    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    args = ["--register", "missing:prod", "url=x"]
    with pytest.raises(ValueError, match="unknown router prefix"):
        _parse_multistore_register(args, {"a": s1})


def test_multistore_register_missing_key_arg_raises():
    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    args = ["--register"]
    with pytest.raises(ValueError, match="requires a key"):
        _parse_multistore_register(args, {"a": s1})


def test_mcprunner_multistore_routes_register():
    class WRouter(Router):
        pass

    class GRouter(Router):
        pass

    s1 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)
    s2 = a2kit.ConnectionStore(Path(tempfile.mkdtemp()), _Conn)

    server = _FakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(WRouter(store=s1))
    routers.add(GRouter(store=s2))
    runner = a2kit.MCPRunner(server, router_registry=routers)
    runner.run(argv=["--register", "w:prod", "url=https://w"])


# --- H. A2K012 lint --------------------------------------------------------


def test_a2k012_flags_raw_custom_cap(tmp_path: Path):
    src = tmp_path / "myapp.py"
    src.write_text(
        "import a2kit\n@a2kit.tool(capabilities={'tickets-management'})\nasync def my_tool() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert any("tickets-management" in m.message for m in a2k012)


def test_a2k012_skips_imported_constants(tmp_path: Path):
    src = tmp_path / "myapp2.py"
    src.write_text(
        "import a2kit\n"
        "from .caps import TICKETS_MANAGEMENT\n"
        "@a2kit.tool(capabilities={TICKETS_MANAGEMENT})\n"
        "async def my_tool() -> dict:\n"
        "    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_skips_local_final_str(tmp_path: Path):
    src = tmp_path / "myapp3.py"
    src.write_text(
        "from typing import Final\n"
        "import a2kit\n"
        "REPO: Final[str] = 'repo'\n"
        "@a2kit.tool(capabilities={REPO})\n"
        "async def my_tool() -> dict:\n"
        "    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_local_final_int_is_not_str(tmp_path: Path):
    """Final[int] should NOT register as a safe name."""
    src = tmp_path / "myappN.py"
    src.write_text(
        "from typing import Final\n"
        "import a2kit\n"
        "X: Final[int] = 1\n"
        "Y: list[str] = []\n"
        "Z: int = 5\n"  # Non-Subscript annotation
        "@a2kit.tool(capabilities={'unknown-cap'})\n"
        "async def my_tool() -> dict:\n"
        "    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    # The literal still triggers because no safe name covers it.
    assert any("unknown-cap" in m.message for m in a2k012)


def test_a2k012_noqa_suppresses(tmp_path: Path):
    src = tmp_path / "myappQ.py"
    src.write_text(
        "import a2kit\n@a2kit.tool(capabilities={'tickets-management'})  # noqa: A2K012\nasync def my_tool() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_skips_non_set_literal_container(tmp_path: Path):
    """Mapping or other non-Set/List/Tuple containers are skipped."""
    src = tmp_path / "myappM.py"
    src.write_text(
        "import a2kit\nCAPS = {'a'}\n@a2kit.tool(capabilities=CAPS)\nasync def my_tool() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_skips_non_str_constants(tmp_path: Path):
    """Non-string constants in the set are ignored by A2K012."""
    src = tmp_path / "myappI.py"
    src.write_text(
        "import a2kit\n@a2kit.tool(capabilities={1, 2})\nasync def my_tool() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012


def test_a2k012_skips_builtin_caps(tmp_path: Path):
    src = tmp_path / "myapp4.py"
    src.write_text(
        "import a2kit\n@a2kit.tool(capabilities={'write'})\nasync def my_tool() -> dict:\n    return {}\n",
        encoding="utf-8",
    )
    from a2kit.lint.static import run_static_rules

    findings = run_static_rules([src])
    a2k012 = [m for m in findings if m.rule == "A2K012"]
    assert not a2k012  # A2K009 covers built-ins, A2K012 doesn't fire


def test_tool_binding_is_pydantic():
    b = _ToolBinding(fn=lambda: None, decorator_kwargs={}, capabilities=set(), mode="read")
    assert b.mode == "read"


def test_router_tool_mode_no_read_write_caps():
    class TRouter(Router):
        pass

    @TRouter.tool()
    async def neutral_tool() -> dict:
        return {}

    server = _FakeServer()
    routers = a2kit.RouterRegistry()
    routers.add(TRouter())
    # mode='tool' goes to register_read by default (read+tool walk)
    routers.apply(server, store=None, include_writes=False)
    assert "neutral_tool" in server.tools


def test_routers_with_stores_skips_storeless():
    class NRouter(Router):
        pass

    routers = a2kit.RouterRegistry()
    routers.add(NRouter())  # no store, no fallback
    pairs = routers.routers_with_stores(fallback_store=None)
    assert pairs == []


def test_make_decorator_records():
    class ZRouter(Router):
        pass

    deco = _make_decorator(ZRouter, mode="tool", decorator_kwargs={"capabilities": {"x"}})

    async def fn() -> dict:
        return {}

    deco(fn)
    assert ZRouter._tools[-1].fn is fn
