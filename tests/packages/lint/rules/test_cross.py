"""Tests for `a2kit.packages.lint.rules.cross`.

Split from `tests/packages/lint/test_rules_misc.py` per
`module-layout-discipline / Test directory mirrors source structure`.
"""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.rules.cross import (
    collect_param_descriptions,
    collect_router_names,
    collect_tool_names,
    rule_a2k008_cross,
)
from a2kit.packages.lint.static import (
    A2K006,
    A2K008,
    run_static_rules,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]  # why: intentional type mismatch — exercises error path or removed surface


# --------------------------- cross.py: A2K006 / A2K008 --------------------------- #


def test_a2k006_cross_fires_for_thrice_repeated_param_doc(tmp_path: Path) -> None:
    """Same `param: long-description` repeated across 3 different files → A2K006."""
    body_template = 'import a2kit\n@a2kit.write()\ndef t{n}() -> int:\n    """Yo.\n\n    foo: this is a description longer than twenty chars\n    """\n    return 1\n'
    paths = [_write(tmp_path / "src" / f"m{i}.py", body_template.format(n=i)) for i in range(3)]
    findings = run_static_rules(paths)
    assert A2K006 in _codes(findings)


def test_a2k006_cross_silent_under_threshold(tmp_path: Path) -> None:
    body_template = (
        'import a2kit\n@a2kit.write()\ndef t{n}() -> int:\n    """foo: a long enough description here yes really"""\n    return 1\n'
    )
    paths = [_write(tmp_path / "src" / f"m{i}.py", body_template.format(n=i)) for i in range(2)]
    findings = run_static_rules(paths)
    assert A2K006 not in _codes(findings)


def test_collect_param_descriptions_filters_short_and_non_ident() -> None:
    """`<20-char` text or non-identifier name is filtered out."""
    import ast

    src = (
        "import a2kit\n"
        "@a2kit.write()\n"
        "def t() -> int:\n"
        '    """\n'
        "    foo: short\n"
        "    not-an-ident: this description is over twenty characters fine\n"
        "    bar: this description is also over twenty characters yes really\n"
        "    no_colon_line\n"
        '    """\n'
        "    return 1\n"
    )
    tree = ast.parse(src)
    out = collect_param_descriptions(tree)
    assert "bar" in out
    assert "foo" not in out
    assert "not-an-ident" not in out


def test_collect_router_names_from_class_name_attribute() -> None:
    import ast

    src = "import a2kit\nclass R(a2kit.Router):\n    name = 'my_router'\n"
    tree = ast.parse(src)
    assert "my_router" in collect_router_names(tree)


def test_collect_router_names_from_call_keyword() -> None:
    import ast

    src = "import a2kit\nfoo(name='dynamic_router')\n"
    tree = ast.parse(src)
    assert "dynamic_router" in collect_router_names(tree)


def test_collect_tool_names_uses_explicit_tool_name() -> None:
    import ast

    src = "import a2kit\n@a2kit.write(tool_name='aliased')\ndef t() -> int:\n    return 1\n"
    tree = ast.parse(src)
    names = collect_tool_names(tree)
    # both the explicit tool_name AND the function def name end up in collected set.
    assert "aliased" in names
    assert "t" in names


def test_a2k008_cross_router_tool_collision() -> None:
    """Same name used as router AND tool → collision."""
    per_file = {
        "/x/router.py": ({"shared"}, set()),
        "/x/tool.py": (set(), {"shared"}),
    }
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_router_capability_collision() -> None:
    """Router named after a built-in cap → collision."""
    per_file = {"/x/r.py": ({"read"}, set())}
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_tool_capability_collision() -> None:
    per_file = {"/x/t.py": (set(), {"write"})}
    findings = list(rule_a2k008_cross(per_file))
    assert any(f.rule == A2K008 for f in findings)


def test_a2k008_cross_no_collision_silent() -> None:
    per_file = {
        "/x/r.py": ({"router_a"}, set()),
        "/x/t.py": (set(), {"tool_a"}),
    }
    findings = list(rule_a2k008_cross(per_file))
    assert findings == []


def test_a2k006_cross_disabled_skips(tmp_path: Path) -> None:
    """`disabled=[A2K006]` — collector is not called, no findings."""
    body = 'import a2kit\n@a2kit.write()\ndef t() -> dict:\n    """foo: a long enough description here yes really"""\n    return {}\n'
    p = _write(tmp_path / "_disabled_a2k006.py", body)
    findings = run_static_rules([p], disabled=[A2K006])
    assert A2K006 not in _codes(findings)
