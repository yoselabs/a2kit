"""Tests for `a2kit.packages.lint.rules.importing`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import (
    A2K_IMPORT_DISCIPLINE,
    A2K_LAYER,
    A2K_PKG_FRONT_DOOR,
    A2K_PKG_INIT_IMPL,
    A2K_PKG_INIT_IMPORT,
    A2K_PKG_INIT_PURITY,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: test helper accepts findings as `object` to match the broad return contract of upstream lint runners


# --------------------------- importing.py: allowlist edges --------------------------- #


def test_import_discipline_plain_import_form_fires(tmp_path: Path) -> None:
    """`import fastmcp` (Import, not ImportFrom) outside allowlist."""
    body = "import fastmcp\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_dotted_module_fires(tmp_path: Path) -> None:
    """`import fastmcp.server` is also covered."""
    body = "import fastmcp.server\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE in _codes(findings)


def test_import_discipline_other_imports_silent(tmp_path: Path) -> None:
    body = "import os\nfrom typing import Any\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_skipped_on_fixture_path(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "tests" / "fixtures" / "m.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_otel_dir(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "otel" / "middleware.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_silent_inside_context_pkg(tmp_path: Path) -> None:
    """``packages/context/`` is allowlisted for the lazy elicit() import."""
    body = "from fastmcp.server.elicitation import AcceptedElicitation\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "context" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_user_tool_with_fastmcp_context_annotation_is_silent(tmp_path: Path) -> None:
    """Tool annotations ``ctx: fastmcp.Context`` import fastmcp at module top.

    User code under their own package isn't subject to A2K-IMPORT-DISCIPLINE
    (the rule only fires inside ``a2kit/``). This regression locks that in
    so portable tool authors aren't penalized for using the real type.
    """
    body = "from fastmcp import Context\nasync def my_tool(*, ctx: Context) -> dict:\n    return {}\n"
    p = _write(tmp_path / "user_app" / "tools.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


def test_import_discipline_noqa(tmp_path: Path) -> None:
    body = "from fastmcp import FastMCP  # noqa: A2K-IMPORT-DISCIPLINE\n"
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_IMPORT_DISCIPLINE not in _codes(findings)


# ----------------------- importing.py: A2K-PKG-INIT-IMPORT ----------------------- #


def test_pkg_init_absolute_self_import_fires(tmp_path: Path) -> None:
    """A submodule doing `from a2kit.<...>.<pkg> import X` is flagged."""
    body = "from a2kit.packages.formatter import render\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT in _codes(findings)


def test_pkg_init_relative_self_import_fires(tmp_path: Path) -> None:
    """`from . import X` pulls the package `__init__` — flagged."""
    body = "from . import render\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT in _codes(findings)


def test_pkg_init_sibling_import_is_silent(tmp_path: Path) -> None:
    """Importing a sibling submodule (`from .formats import X`) is allowed."""
    body = "from .formats import FormatName\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_cross_package_import_is_silent(tmp_path: Path) -> None:
    """Importing from another package is allowed."""
    body = "from a2kit.packages.di import container\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_self_import_in_init_is_silent(tmp_path: Path) -> None:
    """A package `__init__.py` re-exporting its own submodules is allowed."""
    body = "from .render import render\nfrom a2kit.packages.formatter import render as r2\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


def test_pkg_init_import_noqa(tmp_path: Path) -> None:
    body = "from . import render  # noqa: A2K-PKG-INIT-IMPORT\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "formatter" / "sub.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPORT not in _codes(findings)


# --------------------------- A2K-LAYER --------------------------- #


def test_layer_higher_import_fires(tmp_path: Path) -> None:
    """A kernel package importing core (a higher layer) is flagged."""
    body = "from a2kit.app import App\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "di" / "probe.py", body)
    findings = run_static_rules([p])
    assert A2K_LAYER in _codes(findings)


def test_layer_core_importing_kernel_is_clean(tmp_path: Path) -> None:
    """Core importing a kernel package (a lower layer) is clean."""
    body = "from a2kit.packages.di import Container\n"
    p = _write(tmp_path / "src" / "a2kit" / "app.py", body)
    findings = run_static_rules([p])
    assert A2K_LAYER not in _codes(findings)


def test_layer_same_layer_non_cycle_is_clean(tmp_path: Path) -> None:
    """A same-layer import that closes no cycle is allowed."""
    body = "from a2kit.packages.ldd import format_ldd_line\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "context" / "probe.py", body)
    findings = run_static_rules([p])
    assert A2K_LAYER not in _codes(findings)


def test_layer_same_layer_cycle_fires(tmp_path: Path) -> None:
    """Two same-layer kernel packages importing each other close a cycle."""
    a = _write(
        tmp_path / "src" / "a2kit" / "packages" / "di" / "probe.py",
        "from a2kit.packages.formatter import render\n",
    )
    b = _write(
        tmp_path / "src" / "a2kit" / "packages" / "formatter" / "probe.py",
        "from a2kit.packages.di import Container\n",
    )
    findings = run_static_rules([a, b])
    assert A2K_LAYER in _codes(findings)


def test_layer_type_only_cycle_fires(tmp_path: Path) -> None:
    """A cycle is flagged even when one leg is a TYPE_CHECKING import."""
    a = _write(
        tmp_path / "src" / "a2kit" / "packages" / "di" / "probe.py",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from a2kit.packages.formatter import render\n",
    )
    b = _write(
        tmp_path / "src" / "a2kit" / "packages" / "formatter" / "probe.py",
        "from a2kit.packages.di import Container\n",
    )
    findings = run_static_rules([a, b])
    assert A2K_LAYER in _codes(findings)


def test_layer_noqa_suppresses(tmp_path: Path) -> None:
    body = "from a2kit.app import App  # noqa: A2K-LAYER\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "di" / "probe.py", body)
    findings = run_static_rules([p])
    assert A2K_LAYER not in _codes(findings)


# --------------------------- A2K-PKG-FRONT-DOOR --------------------------- #


def test_front_door_deep_cross_package_import_fires(tmp_path: Path) -> None:
    body = "from a2kit.packages.di.container import Container\n"
    p = _write(tmp_path / "src" / "a2kit" / "app.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_FRONT_DOOR in _codes(findings)


def test_front_door_front_import_is_clean(tmp_path: Path) -> None:
    body = "from a2kit.packages.di import Container\n"
    p = _write(tmp_path / "src" / "a2kit" / "app.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_FRONT_DOOR not in _codes(findings)


def test_front_door_same_package_submodule_is_clean(tmp_path: Path) -> None:
    """A module reaching a sibling inside its own package is internal wiring."""
    body = "from a2kit.packages.di.container import Container\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "di" / "scope.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_FRONT_DOOR not in _codes(findings)


def test_front_door_noqa_suppresses(tmp_path: Path) -> None:
    body = "from a2kit.packages.di.container import Container  # noqa: A2K-PKG-FRONT-DOOR\n"
    p = _write(tmp_path / "src" / "a2kit" / "app.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_FRONT_DOOR not in _codes(findings)


# --------------------------- A2K-PKG-INIT-IMPL --------------------------- #


def test_init_impl_class_body_fires(tmp_path: Path) -> None:
    """A class defined in a package `__init__.py` is flagged."""
    body = "class Widget:\n    def go(self) -> int:\n        return 1\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL in _codes(findings)


def test_init_impl_function_body_fires(tmp_path: Path) -> None:
    """A logic-bearing function defined in a package `__init__.py` is flagged."""
    body = "def compute(x: int) -> int:\n    return x * 2\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "health" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL in _codes(findings)


def test_init_impl_async_function_body_fires(tmp_path: Path) -> None:
    """An `async def` in a package `__init__.py` is flagged too."""
    body = "async def emit(name: str) -> None:\n    print(name)\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL in _codes(findings)


def test_init_impl_re_export_front_door_is_clean(tmp_path: Path) -> None:
    """An `__init__.py` of imports + re-exports + `__all__` + constants is clean."""
    body = 'from .wire import format_ldd_line\n\nTEXT_CAP = 60\n\n__all__ = ["format_ldd_line", "TEXT_CAP"]\n'
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL not in _codes(findings)


def test_init_impl_lazy_getattr_facade_is_clean(tmp_path: Path) -> None:
    """The lazy `__getattr__` / `__dir__` re-export facade is exempt."""
    body = (
        "_LAZY = {'install': ('a2kit.packages.otel.middleware', 'install')}\n\n"
        "def __getattr__(name: str) -> object:\n"
        "    import importlib\n"
        "    mod, attr = _LAZY[name]\n"
        "    return getattr(importlib.import_module(mod), attr)\n\n"
        "def __dir__() -> list[str]:\n"
        "    return sorted(_LAZY)\n"
    )
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "otel" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL not in _codes(findings)


def test_init_impl_silent_in_submodule(tmp_path: Path) -> None:
    """A class in a named submodule (not `__init__.py`) is exactly the goal — clean."""
    body = "class Widget:\n    def go(self) -> int:\n        return 1\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "wire.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL not in _codes(findings)


def test_init_impl_noqa_suppresses(tmp_path: Path) -> None:
    body = "class Widget:  # noqa: A2K-PKG-INIT-IMPL\n    pass\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_IMPL not in _codes(findings)


# --------------------------- A2K-PKG-INIT-PURITY ------------------------- #


def test_init_purity_underscore_in_all_fires(tmp_path: Path) -> None:
    """A `_`-prefixed name in `__all__` is flagged."""
    body = '__all__ = ["public_thing", "_internal_thing"]\n'
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY in _codes(findings)


def test_init_purity_underscore_from_import_fires(tmp_path: Path) -> None:
    """`from ._x import _y` re-exports a private name through the front door."""
    body = "from ._impl import _internal\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY in _codes(findings)


def test_init_purity_aliased_underscore_fires(tmp_path: Path) -> None:
    """`from ._x import y as _z` — the bound name still leaks privately."""
    body = "from ._impl import public_y as _z\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY in _codes(findings)


def test_init_purity_dunder_names_pass(tmp_path: Path) -> None:
    """Dunder names like `__all__`, `__getattr__` are not private leaks."""
    body = '__all__ = ["__version__"]\nfrom .meta import __version__\n'
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY not in _codes(findings)


def test_init_purity_clean_init_passes(tmp_path: Path) -> None:
    """An `__init__.py` re-exporting only public names is clean."""
    body = 'from .wire import format_ldd_line\n\n__all__ = ["format_ldd_line"]\n'
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "ldd" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY not in _codes(findings)


def test_init_purity_outside_packages_silent(tmp_path: Path) -> None:
    """The rule scopes to `src/a2kit/packages/<x>/__init__.py` only."""
    body = '__all__ = ["_private"]\n'
    p = _write(tmp_path / "src" / "a2kit" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY not in _codes(findings)


def test_init_purity_noqa_suppresses_import(tmp_path: Path) -> None:
    """An inline `# noqa: A2K-PKG-INIT-PURITY` on the import line suppresses."""
    body = "from ._impl import _internal  # noqa: A2K-PKG-INIT-PURITY\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY not in _codes(findings)


def test_init_purity_noqa_suppresses_all_entry(tmp_path: Path) -> None:
    """An inline `# noqa: A2K-PKG-INIT-PURITY` on an `__all__` entry suppresses."""
    body = '__all__ = [\n    "public",\n    "_internal",  # noqa: A2K-PKG-INIT-PURITY\n]\n'
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "foo" / "__init__.py", body)
    findings = run_static_rules([p])
    assert A2K_PKG_INIT_PURITY not in _codes(findings)
