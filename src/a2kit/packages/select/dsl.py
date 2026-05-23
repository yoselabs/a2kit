"""``--select EXPR`` runtime filter for the a2kit registry.

Per ``add-tool-select`` (`tool-selection` spec): operators narrow the
exposed tool surface at build time with a key=value DSL parsed by
:func:`compile_selector`. Multiple ``--select`` flags AND together; the
resulting filter is applied once during ``App.build(select=...)`` and
frozen on the ``AppRuntime`` — the dispatch hot path never re-evaluates.

DSL: ``category=value1,value2,!value3``

- ``category`` ∈ ``{verb, name, surface}``
- ``values`` is comma-separated; each value is plain (include) or
  ``!``-prefixed (exclude).
- Whitespace around tokens is stripped.
- Reserved characters ``=,!`` may not appear inside a value.
- Empty include set passes vacuously; exclude check always runs.
- ``name`` values use ``fnmatch.fnmatchcase`` (shell-style glob).
- ``verb`` matches by string equality against ``descriptor.verb``.
- ``surface`` accepts only ``mcp`` and ``api``; reduces the
  descriptor's ``expose`` tuple to the include intersection.

Stdlib-only parser; no ``lark``/``regex``/``cel-python`` dependency.
The CEL escape hatch lives in design D7 if/when needed.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Literal

# ``Selector.matches`` accepts any object exposing ``.verb``, ``.name``,
# and ``.expose`` — structural duck-typing, not a nominal dependency on
# ``ToolDescriptor`` (which lives at L2 authoring and is forbidden to L0
# `select` per A2K-LAYER). Tests use plain dataclasses with those fields.
Category = Literal["verb", "name", "surface"]
_CATEGORIES: frozenset[str] = frozenset({"verb", "name", "surface"})
_RESERVED_CHARS: frozenset[str] = frozenset({"=", ",", "!"})
_SURFACE_VALUES: frozenset[str] = frozenset({"mcp", "api"})


class SelectorError(ValueError):
    """Parse / validation failure in a ``--select`` expression.

    Raised by :func:`compile_selector` for any malformed expression.
    The CLI wrapper (``serve --select EXPR``) catches this, prints the
    single-line message to stderr, and exits with status 2.
    """


@dataclass(frozen=True)
class Selector:
    """Compiled selector — one category, an include set, an exclude set.

    ``Selector.matches(desc)`` returns True when ``desc`` survives the
    filter for this category. Empty include set passes vacuously
    (operators sometimes use exclude-only); exclude always runs.

    For ``surface`` selectors, ``matches`` is True if any element of
    ``desc.expose`` is in the include set; the runtime filter then
    further narrows ``expose`` itself elsewhere (see ``App.build``).
    """

    category: Category
    include: frozenset[str]
    exclude: frozenset[str]

    def matches(self, desc: Any) -> bool:
        if self.category == "verb":
            value = desc.verb
            if self.include and value not in self.include:
                return False
            return value not in self.exclude
        if self.category == "name":
            value = desc.name
            if self.include and not any(fnmatch.fnmatchcase(value, pat) for pat in self.include):
                return False
            return not any(fnmatch.fnmatchcase(value, pat) for pat in self.exclude)
        if self.category == "surface":
            expose = set(desc.expose)
            if self.include and not (expose & self.include):
                return False
            return not (expose & self.exclude)
        msg = f"unknown category {self.category!r}"  # pragma: no cover -- Literal narrows
        raise SelectorError(msg)


def compile_selector(expr: str) -> Selector:
    """Parse one ``category=values`` expression into a :class:`Selector`.

    Raises :class:`SelectorError` on any parse problem:

    - Missing ``=`` (no separator).
    - Unknown category (not in ``{verb, name, surface}``).
    - Empty value (``verb=``).
    - Reserved character ``,`` / ``=`` / ``!`` inside a value.
    - ``surface=`` value outside ``{mcp, api}``.
    """
    if "=" not in expr:
        msg = f"selector must be 'category=values'; got {expr!r}"
        raise SelectorError(msg)
    raw_cat, raw_values = expr.split("=", 1)
    category = raw_cat.strip()
    if category not in _CATEGORIES:
        msg = f"unknown category {category!r}; expected verb|name|surface (in selector {expr!r})"
        raise SelectorError(msg)
    parts = [p.strip() for p in raw_values.split(",")]
    if not parts or any(not p for p in parts) or (len(parts) == 1 and not parts[0]):
        msg = f"empty value in selector {expr!r}"
        raise SelectorError(msg)
    include: set[str] = set()
    exclude: set[str] = set()
    for raw in parts:
        if raw.startswith("!"):
            value = raw[1:].strip()
            target = exclude
        else:
            value = raw
            target = include
        if not value:
            msg = f"empty value in selector {expr!r}"
            raise SelectorError(msg)
        if any(c in _RESERVED_CHARS for c in value):
            msg = f"value {value!r} contains reserved char ('=', ',', or '!'); in selector {expr!r}"
            raise SelectorError(msg)
        target.add(value)
    if category == "surface":
        bad = (include | exclude) - _SURFACE_VALUES
        if bad:
            msg = f"surface accepts only 'mcp' or 'api'; got {sorted(bad)!r} in selector {expr!r}"
            raise SelectorError(msg)
    return Selector(
        category=category,  # type: ignore[arg-type]
        include=frozenset(include),
        exclude=frozenset(exclude),
    )


__all__ = ["Category", "Selector", "SelectorError", "compile_selector"]
