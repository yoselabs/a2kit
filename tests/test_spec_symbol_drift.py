"""SPEC ↔ live-code parity gate.

Spec-tree sibling of ``tests/test_readme_symbol_drift.py``. Scans every
``openspec/specs/*/spec.md`` and asserts that each *checkable* code-font
symbol resolves on the live ``a2kit`` surface — binding against the
imported types, not text-matching ``src/``.

A token inside a backtick span is checkable when it is one of:

- a dotted a2kit path — ``a2kit.X`` / ``a2kit.<submod>.Y`` (optionally
  ``@``-prefixed);
- an attribute access on a canonical type — ``App.x`` / ``app.x`` /
  ``Router.x`` / ``Container.x`` (optionally ``@``-prefixed);
- an a2kit lint-rule code — the ``A2K-`` dashed form.

Bare words, string literals, paths, shell, type-annotation fragments,
and third-party dotted names are not checkable and are skipped by
construction (the three narrow patterns below never match them).

See ADR 0018 and the ``spec-drift-gate`` capability. The allowlist
holds only tombstone-migration targets and illustrative placeholders —
no grandfathered drift. A symbol that does not resolve is a spec to
fix, not an allowlist entry to add.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

import a2kit
from a2kit.packages.di.container import Container
from a2kit.packages.lint.static import ALL_RULES
from a2kit.routers import Router
from a2kit.runtime import build

SPECS_DIR = Path(__file__).resolve().parent.parent / "openspec" / "specs"

#: Live a2kit static lint-rule codes — the resolution target for ``A2K-`` symbols.
_LINT_RULE_CODES: frozenset[str] = frozenset(ALL_RULES)

# Structurally a2kit-shaped symbols that legitimately do not resolve.
# Two groups only: tombstone-migration targets (a spec may cite a
# removed name in a REMOVED requirement's migration line) and
# illustrative placeholders (pattern-description metavariables). The
# grandfathered-drift group is empty — reconcile-spec-drift-residual
# cleared every `# reconcile:` entry. A new entry here is a red flag:
# fix the spec, do not allowlist live drift.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        # --- tombstone migration targets: a spec cites a removed name to
        #     document its migration; not resolving is the point ---
        "a2kit.AppBuilder",  # removed in the one-App collapse (ADR 0017)
        "a2kit.tool",  # removed v0.33 — split into read/write/list_ verbs
        "Container.dispatch",  # renamed to call_scope (d1dddb7); the spec
        # scenario cites the absent symbol as proof the rename is loud
        "a2kit.packages.dispatch.substrate.Substrate",  # removed in
        # remove-substrate-literal; surface-protocol spec cites it in the
        # migration-hint scenario
        "App.debug",  # removed in di-for-sub-configs (2026-05-25); the
        "app.debug",  # core-composition + runtime-config specs cite the
        # name in their tombstone / migration-hint paragraphs.
        # --- example-only / illustrative placeholders cited in pattern
        #     descriptions (not real surface, not drift) ---
        "App.method",  # illustrative metavariable in docs-code-parity
        "Router.attribute",  # illustrative metavariable in docs-code-parity
        "a2kit.log.foo",  # illustrative metavariable in docs-code-parity
        "app.method",  # illustrative metavariable in docs-code-parity
        # --- a2effect-foundation lint rules: spec-declared, runtime
        #     implementation deferred to a2lint-extraction follow-up. The
        #     specs name them now to lock the contract; the live registry
        #     gains them when a2lint-extraction lands. ---
        "A2K-RAISES-CLOSURE",
        "A2K-RAISES-UNCOVERED",
        "A2K-RAISES-NOT-TYPED",
        "A2K-RAISES-HELPER-UNTYPED",
        "A2K-OUTPUT-SCHEMA-COMPAT",
        # --- string names cited in scenarios (logger names, span attrs)
        #     that look like dotted import paths but are not ---
        "a2kit.ldd.sink_failed",  # logger name for the WARN-log on sink failures
        "a2kit.dur_ms",  # OTel span attribute name
        # --- Rego data-namespace paths (policies/data.json keys, NOT Python
        #     imports). The `rego-policy-layer` spec quotes them as
        #     `a2kit.allowlist.<policy>` — they live in OPA's data tree, not
        #     in the Python package surface. ---
        "a2kit.allowlist.body_dup",
        "a2kit.allowlist.name_collision",
        "a2kit.allowlist.github_actions_vendor",
        "a2kit.allowlist.github_actions_vendor_unpinned",
        "a2kit.allowlist.pyproject_upper_bound",
    }
)


_FENCED_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_INLINE_RE = re.compile(r"`([^`\n]+)`")

# Checkable-token patterns. Narrow by design — anything that does not match
# one of these is not checkable and is skipped (D3). The leading lookbehind
# rejects `a2kit` mid-path (e.g. the TOML section `[tool.a2kit.lint]`) —
# only a package-root `a2kit.` is a checkable import path.
_DOTTED_A2KIT = re.compile(r"(?<![\w.])@?a2kit(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
# ``AppRuntime`` precedes ``App`` in the alternation so the longer token
# wins — ordered alternation would otherwise match the ``App`` prefix.
_CANONICAL = re.compile(r"(?:^|[^A-Za-z0-9_])@?(AppRuntime|App|app|Router|Container)\.([A-Za-z_][A-Za-z0-9_]*)")
_LINT_CODE = re.compile(r"A2K-[A-Z0-9-]+")

# Live instance probes — resolving attribute accesses against an instance
# catches attributes set in ``__init__`` (e.g. ``app.ldd``) that a
# class-level ``hasattr`` would miss.
_APP_PROBE = a2kit.App("_spec_drift_probe")
_APPRUNTIME_PROBE = build(a2kit.App("_spec_drift_probe_rt"))
_CONTAINER_PROBE = Container()


class _RouterProbe(Router):
    slug = "_spec_drift_probe"


_CANONICAL_PROBES: dict[str, object] = {
    "App": _APP_PROBE,
    "app": _APP_PROBE,
    "AppRuntime": _APPRUNTIME_PROBE,
    "Router": _RouterProbe(),
    "Container": _CONTAINER_PROBE,
}

# Canonical-access attrs that are not symbols: a source-file extension
# (``app.py`` names a file, not an attribute).
_FILE_EXTENSIONS = frozenset({"py", "md", "txt", "toml", "json", "yaml", "yml", "cfg", "ini", "lock"})


def _is_metavariable(token: str) -> bool:
    """True for a single-letter metavariable (``X``, ``T``, ``x``).

    No real a2kit symbol is one letter, so any single-letter token in a
    code-font span is a placeholder used to describe a pattern.
    """
    return len(token) == 1 and token.isalpha()


def _extract_code_spans(text: str) -> list[tuple[str, int]]:
    """Return ``(span_text, line_number)`` for fenced blocks and inline spans."""
    fenced = [(m.group(1), text.count("\n", 0, m.start()) + 1) for m in _FENCED_RE.finditer(text)]
    inline = [(m.group(1), text.count("\n", 0, m.start()) + 1) for m in _INLINE_RE.finditer(text)]
    return fenced + inline


def _resolve_dotted(path: str) -> tuple[bool, str]:
    """Resolve a dotted ``a2kit.*`` path against the imported surface.

    Walks the path segment by segment from the ``a2kit`` package: each
    segment is tried as a submodule import, then as an attribute. The
    walk stops at the first non-module attribute that resolves — the
    gate verifies the *head* of the path exists; it does not descend
    into instance/dataclass fields (``a2kit.HealthResult.ok`` passes
    once ``a2kit.HealthResult`` resolves).
    """
    path = path.lstrip("@")
    if path in _ALLOWLIST:
        return True, ""
    parts = path.split(".")  # parts[0] == "a2kit"
    obj: object = a2kit
    for i in range(1, len(parts)):
        seg = parts[i]
        try:
            obj = importlib.import_module(".".join(parts[: i + 1]))
            continue
        except ImportError:
            pass
        if hasattr(obj, seg):
            return True, ""  # head resolves to a real attribute; trust the tail
        return False, f"{'.'.join(parts[:i])} has no attribute {seg!r}"
    return True, ""


def _resolve_canonical(type_name: str, attr: str, symbol: str) -> tuple[bool, str]:
    """Resolve ``App.x`` / ``Router.x`` / ``Container.x`` against a live probe.

    Checks the instance probe (catches ``__init__``-set attributes) and the
    class object (catches class-level attributes and dunders like
    ``__name__`` that an instance does not carry).
    """
    if symbol in _ALLOWLIST:
        return True, ""
    probe = _CANONICAL_PROBES[type_name]
    if hasattr(probe, attr) or hasattr(type(probe), attr):
        return True, ""
    return False, f"{type(probe).__name__} has no attribute {attr!r}"


def _resolve_lint_code(code: str) -> tuple[bool, str]:
    """Resolve an ``A2K-`` lint-rule code against the live registry."""
    if code in _ALLOWLIST:
        return True, ""
    return (True, "") if code in _LINT_RULE_CODES else (False, "not in the a2kit lint-rule registry")


def _drift_in_span(span: str, line_no: int) -> list[tuple[str, int, str]]:
    """Yield ``(symbol, line, reason)`` drift entries for one code span."""
    out: list[tuple[str, int, str]] = []

    for m in _DOTTED_A2KIT.finditer(span):
        symbol = m.group(0)
        if _is_metavariable(symbol.lstrip("@").rsplit(".", 1)[-1]):
            continue  # `a2kit.X` — a type metavariable, not a symbol claim
        ok, reason = _resolve_dotted(symbol)
        if not ok:
            out.append((symbol.lstrip("@"), line_no, reason))

    # Strip dotted a2kit paths before scanning canonical accesses so
    # `a2kit.app.App` does not also register as a bare `App.` hit.
    span_no_dotted = _DOTTED_A2KIT.sub("", span)
    for m in _CANONICAL.finditer(span_no_dotted):
        type_name, attr = m.group(1), m.group(2)
        if _is_metavariable(attr) or attr in _FILE_EXTENSIONS:
            continue  # `App.X` metavariable or `app.py` filename
        symbol = f"{type_name}.{attr}"
        ok, reason = _resolve_canonical(type_name, attr, symbol)
        if not ok:
            out.append((symbol, line_no, reason))

    for m in _LINT_CODE.finditer(span):
        code = m.group(0)
        ok, reason = _resolve_lint_code(code)
        if not ok:
            out.append((code, line_no, reason))

    return out


def _collect_drift(text: str, *, label: str) -> list[tuple[str, int, str]]:
    """Return ``(symbol, line, reason)`` for every unresolved symbol in ``text``.

    ``label`` is the source identifier echoed in failure messages (a spec
    file path for the real gate, a fixture name for the unit tests).
    """
    drift: list[tuple[str, int, str]] = []
    for span, line_no in _extract_code_spans(text):
        if span.startswith("$"):  # shell snippet
            continue
        drift.extend(_drift_in_span(span, line_no))
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int, str]] = []
    for sym, line, reason in drift:
        if (sym, line) in seen:
            continue
        seen.add((sym, line))
        unique.append((sym, line, reason))
    return [(f"{label}:{line} — {sym}: {reason}", line, reason) for sym, line, reason in unique]


# --- BDD: the gate's own behaviour ---------------------------------------- #


def test_dead_dotted_symbol_is_caught() -> None:
    drift = _collect_drift("A spec citing `a2kit.NonexistentThing` here.", label="fixture")
    assert drift, "a dead dotted a2kit symbol must fail the gate"
    assert "a2kit.NonexistentThing" in drift[0][0]


def test_dead_canonical_access_is_caught() -> None:
    drift = _collect_drift("The old `Container._totally_fake_seam` seam.", label="fixture")
    assert drift, "a dead Container attribute access must fail the gate"
    assert "Container._totally_fake_seam" in drift[0][0]


def test_dead_lint_rule_code_is_caught() -> None:
    drift = _collect_drift("Enforced by `A2K-NONEXISTENT-RULE` at lint time.", label="fixture")
    assert drift, "a dead A2K- lint-rule code must fail the gate"
    assert "A2K-NONEXISTENT-RULE" in drift[0][0]


def test_allowlisted_name_passes() -> None:
    drift = _collect_drift("Migrate off `a2kit.AppBuilder` per ADR 0017.", label="fixture")
    assert drift == [], "an allowlisted tombstone target must not fail the gate"


def test_illustrative_tokens_are_not_checked() -> None:
    drift = _collect_drift("Use `Lazy[T]` or `pydantic.Field` or `dict[str, int]`.", label="fixture")
    assert drift == [], "type-annotation fragments and third-party tokens are not checkable"


def test_live_symbols_pass() -> None:
    drift = _collect_drift("Construct `a2kit.App`, call `app.provide`, see `A2K-LAYER`.", label="fixture")
    assert drift == [], f"live symbols must resolve, got: {drift}"


# --- the gate ------------------------------------------------------------- #


def test_all_spec_symbols_resolve_in_live_code() -> None:
    """Every checkable symbol in every capability spec resolves in src/a2kit/."""
    spec_files = sorted(SPECS_DIR.glob("*/spec.md"))
    assert spec_files, f"no spec files found under {SPECS_DIR}"

    drift: list[tuple[str, int, str]] = []
    for spec in spec_files:
        rel = spec.relative_to(SPECS_DIR.parent.parent)
        drift.extend(_collect_drift(spec.read_text(encoding="utf-8"), label=str(rel)))

    if drift:
        lines = "\n".join(f"  {entry}" for entry, _, _ in drift)
        pytest.fail(
            "Capability specs cite symbols that do not resolve on the live a2kit "
            "surface. Fix the spec, or allowlist the symbol in "
            "tests/test_spec_symbol_drift.py:\n" + lines
        )
