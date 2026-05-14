"""A2K015 / A2K016 / A2K017 — di-scoped-lifecycle anti-pattern rules."""

from __future__ import annotations

import ast
from textwrap import dedent

from a2kit.packages.lint.rules.di_scoped import (
    rule_ensure_pattern,
    rule_lazy_t_suggestion,
    rule_parameterized_lambda_factory,
)
from a2kit.packages.lint.static import A2K015, A2K016, A2K017


def _ensure_findings(src: str) -> list:
    tree = ast.parse(dedent(src))
    return list(rule_ensure_pattern(tree, "<test>", src))


def _lambda_findings(src: str) -> list:
    tree = ast.parse(dedent(src))
    return list(rule_parameterized_lambda_factory(tree, "<test>", src))


def _lazy_findings(src: str) -> list:
    tree = ast.parse(dedent(src))
    return list(rule_lazy_t_suggestion(tree, "<test>", src))


# --- A2K015 — _ensure() pattern -------------------------------------------


def test_a2k015_fires_when_provided_class_has_ensure() -> None:
    src = """
    import a2kit

    class BrowserPool:
        async def _ensure(self):
            return None

    app = a2kit.App("x")
    app.provide(BrowserPool)
    """
    out = _ensure_findings(src)
    assert len(out) == 1
    assert out[0].rule == A2K015
    assert "BrowserPool._ensure()" in out[0].message


def test_a2k015_silent_for_unregistered_class_with_ensure() -> None:
    src = """
    class Unrelated:
        async def _ensure(self):
            return None
    """
    assert _ensure_findings(src) == []


def test_a2k015_silent_when_provided_class_uses_aenter_pattern() -> None:
    src = """
    import a2kit

    class BrowserPool:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None

    app = a2kit.App("x")
    app.provide(BrowserPool)
    """
    assert _ensure_findings(src) == []


def test_a2k015_respects_noqa() -> None:
    src = """
    import a2kit

    class BrowserPool:
        async def _ensure(self):  # noqa: A2K015
            return None

    app = a2kit.App("x")
    app.provide(BrowserPool)
    """
    assert _ensure_findings(src) == []


# --- A2K016 — parameterized lambda as DI factory --------------------------


def test_a2k016_fires_on_parameterized_lambda_factory() -> None:
    src = """
    import a2kit

    app = a2kit.App("x")
    app.provide(SqliteResource, lambda conn: SqliteResource(conn))
    """
    out = _lambda_findings(src)
    assert len(out) == 1
    assert out[0].rule == A2K016


def test_a2k016_silent_on_zero_arg_lambda_factory() -> None:
    src = """
    import a2kit

    app = a2kit.App("x")
    app.provide(SqliteResource, lambda: SqliteResource())
    """
    assert _lambda_findings(src) == []


def test_a2k016_silent_on_def_factory() -> None:
    src = """
    import a2kit

    def make_sqlite(conn: ConnectionConfig) -> SqliteResource:
        return SqliteResource(conn)

    app = a2kit.App("x")
    app.provide(SqliteResource, make_sqlite)
    """
    assert _lambda_findings(src) == []


# --- A2K017 — Lazy[T] suggestion ------------------------------------------


def test_a2k017_fires_when_typed_param_only_used_in_if_branch() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def extract(url: str, browser: Browser) -> str:
        if needs_js(url):
            return await browser.scrape(url)
        return await plain_get(url)
    """
    out = _lazy_findings(src)
    # `browser` only used inside the `if` body — should hint.
    rule_hits = [m for m in out if m.rule == A2K017]
    assert any("browser" in m.message for m in rule_hits)


def test_a2k017_silent_when_typed_param_used_unconditionally() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def extract(browser: Browser) -> str:
        await browser.scrape("x")
        return "ok"
    """
    assert _lazy_findings(src) == []


def test_a2k017_silent_for_str_primitive_params() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def extract(url: str) -> str:
        if url:
            return url
        return ""
    """
    assert _lazy_findings(src) == []


def test_a2k017_silent_when_already_lazy() -> None:
    src = """
    import a2kit

    @a2kit.read()
    async def extract(url: str, browser: Lazy[Browser]) -> str:
        if needs_js(url):
            b = await browser()
            return await b.scrape(url)
        return await plain_get(url)
    """
    assert _lazy_findings(src) == []
