"""Shared symbol-drift engine — doc/spec ↔ live-code parity.

Extraction + resolution machinery shared by the parity gates
(``tests/test_spec_symbol_drift.py``, ``tests/test_docs_symbol_drift.py``).
Each gate supplies its own ``allowlist`` and the set of files to scan; the
engine here owns *how* a backtick-quoted token is decided checkable and
resolved against the live ``a2kit`` surface.

A token inside a backtick span (fenced block or inline) is checkable when
it is one of:

- a dotted a2kit path — ``a2kit.X`` / ``a2kit.<submod>.Y`` (optionally
  ``@``-prefixed);
- an attribute access on a canonical type — ``App.x`` / ``app.x`` /
  ``Router.x`` / ``Container.x`` (optionally ``@``-prefixed);
- an a2kit lint-rule code — ``AK###`` / ``AKR###`` / ``RG###`` or a legacy
  ``A2K-*`` / ``REGO-*`` dashed spelling (resolved via ``normalize_code``).

Bare words, string literals, paths, shell, type-annotation fragments, and
third-party dotted names are not checkable and are skipped by construction
(the three narrow patterns below never match them).
"""

from __future__ import annotations

import importlib
import re

import a2kit
from a2kit.packages.di.container import Container
from a2kit.packages.lint.runtime import ALL_CHECKS
from a2kit.packages.lint.static import ALL_RULES, LEGACY_CODE_ALIASES, normalize_code
from a2kit.routers import Router
from a2kit.runtime import build
from a2kit.testing import app_of

#: Live a2kit lint-rule codes — the resolution target for code-font lint-rule
#: symbols. Covers static ``AK*``, runtime ``AKR*``, and the rego ``RG*``
#: family (sourced from the alias-table values, since RG codes live in the
#: .rego bundle). A legacy spelling resolves via :func:`normalize_code`.
_LINT_RULE_CODES: frozenset[str] = frozenset(
    set(ALL_RULES) | set(ALL_CHECKS) | {new for new in LEGACY_CODE_ALIASES.values() if new.startswith("RG")}
)

_FENCED_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_INLINE_RE = re.compile(r"`([^`\n]+)`")

# Checkable-token patterns. Narrow by design — anything that does not match
# one of these is not checkable and is skipped. The leading lookbehind
# rejects `a2kit` mid-path (e.g. the TOML section `[tool.a2kit.lint]`) —
# only a package-root `a2kit.` is a checkable import path.
_DOTTED_A2KIT = re.compile(r"(?<![\w.])@?a2kit(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
# ``AppRuntime`` precedes ``App`` in the alternation so the longer token
# wins — ordered alternation would otherwise match the ``App`` prefix.
_CANONICAL = re.compile(r"(?:^|[^A-Za-z0-9_])@?(AppRuntime|App|app|Router|Container)\.([A-Za-z_][A-Za-z0-9_]*)")
# New-shape codes (`AK###` / `AKR###` / `RG###`) plus legacy *dashed* spellings
# (`A2K-*` / `REGO-*`), which resolve through the deprecation window via
# ``normalize_code``. Bare numeric legacy codes (`A2K014`) are intentionally NOT
# matched — they were never validated by this gate and reading them now would
# surface long-standing illustrative refs; specs cite the new `AK###` form.
_LINT_CODE = re.compile(r"A2K-[A-Z0-9-]+|REGO-[A-Z0-9-]+|AKR?[0-9]+|RG[0-9]+")

# Live instance probes — resolving attribute accesses against an instance
# catches attributes set in ``__init__`` (e.g. ``app.ldd``) that a
# class-level ``hasattr`` would miss.
_APP_PROBE = app_of("_symbol_drift_probe")
_APPRUNTIME_PROBE = build(app_of("_symbol_drift_probe_rt"))
_CONTAINER_PROBE = Container()


class _RouterProbe(Router):
    slug = "_symbol_drift_probe"


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


def _resolve_dotted(path: str, allowlist: frozenset[str]) -> tuple[bool, str]:
    """Resolve a dotted ``a2kit.*`` path against the imported surface.

    Walks the path segment by segment from the ``a2kit`` package: each
    segment is tried as a submodule import, then as an attribute. The
    walk stops at the first non-module attribute that resolves — the
    gate verifies the *head* of the path exists; it does not descend
    into instance/dataclass fields (``a2kit.HealthResult.ok`` passes
    once ``a2kit.HealthResult`` resolves).
    """
    path = path.lstrip("@")
    if path in allowlist:
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


def _resolve_canonical(type_name: str, attr: str, symbol: str, allowlist: frozenset[str]) -> tuple[bool, str]:
    """Resolve ``App.x`` / ``Router.x`` / ``Container.x`` against a live probe.

    Checks the instance probe (catches ``__init__``-set attributes) and the
    class object (catches class-level attributes and dunders like
    ``__name__`` that an instance does not carry).
    """
    if symbol in allowlist:
        return True, ""
    probe = _CANONICAL_PROBES[type_name]
    if hasattr(probe, attr) or hasattr(type(probe), attr):
        return True, ""
    return False, f"{type(probe).__name__} has no attribute {attr!r}"


def _resolve_lint_code(code: str, allowlist: frozenset[str]) -> tuple[bool, str]:
    """Resolve a lint-rule code against the live registry (legacy via alias)."""
    if code in allowlist:
        return True, ""
    return (True, "") if normalize_code(code) in _LINT_RULE_CODES else (False, "not in the a2kit lint-rule registry")


def _drift_in_span(span: str, line_no: int, allowlist: frozenset[str]) -> list[tuple[str, int, str]]:
    """Yield ``(symbol, line, reason)`` drift entries for one code span."""
    out: list[tuple[str, int, str]] = []

    for m in _DOTTED_A2KIT.finditer(span):
        symbol = m.group(0)
        if _is_metavariable(symbol.lstrip("@").rsplit(".", 1)[-1]):
            continue  # `a2kit.X` — a type metavariable, not a symbol claim
        ok, reason = _resolve_dotted(symbol, allowlist)
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
        ok, reason = _resolve_canonical(type_name, attr, symbol, allowlist)
        if not ok:
            out.append((symbol, line_no, reason))

    for m in _LINT_CODE.finditer(span):
        code = m.group(0)
        ok, reason = _resolve_lint_code(code, allowlist)
        if not ok:
            out.append((code, line_no, reason))

    return out


def collect_drift(text: str, *, label: str, allowlist: frozenset[str]) -> list[tuple[str, int, str]]:
    """Return ``(entry, line, reason)`` for every unresolved symbol in ``text``.

    ``label`` is the source identifier echoed in failure messages (a spec or
    doc file path for a real gate, a fixture name for a unit test).
    ``allowlist`` holds the caller's tombstone-migration targets, logger
    names, and illustrative placeholders — symbols that look a2kit-shaped but
    legitimately do not resolve.
    """
    drift: list[tuple[str, int, str]] = []
    for span, line_no in _extract_code_spans(text):
        if span.startswith("$"):  # shell snippet
            continue
        drift.extend(_drift_in_span(span, line_no, allowlist))
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int, str]] = []
    for sym, line, reason in drift:
        if (sym, line) in seen:
            continue
        seen.add((sym, line))
        unique.append((sym, line, reason))
    return [(f"{label}:{line} — {sym}: {reason}", line, reason) for sym, line, reason in unique]
