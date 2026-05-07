"""Select expression evaluation, atom matching, atom validation + typed builder.

Split from `a2kit._select` in v0.4. The evaluator side is import-light (no
parser code), so consumers that only evaluate pre-parsed expressions can pull
just this module without dragging tokeniser regexes into the import graph.
"""

from __future__ import annotations

import difflib
from typing import Literal, overload

from a2kit._capabilities import UnknownCapability, capabilities
from a2kit._select_parse import SelectAtom, SelectExpr


def _atom_matches(atom: SelectAtom, tags: set[str]) -> bool:
    """Match a single atom against the tool's tag set.

    Bare atoms match either the bare tag or the `tool:<name>` form (so authors
    can write `--select foo` instead of `--select tool:foo`). Namespaced atoms
    only match the namespaced form.
    """
    if atom.namespace is None:
        return atom.name in tags or f"tool:{atom.name}" in tags
    return f"{atom.namespace}:{atom.name}" in tags


@overload
def sel(name: str, /) -> SelectExpr: ...
@overload
def sel(*, tool: str) -> SelectExpr: ...
@overload
def sel(*, router: str) -> SelectExpr: ...
@overload
def sel(*, cap: str) -> SelectExpr: ...


def sel(
    name: str | None = None,
    /,
    *,
    tool: str | None = None,
    router: str | None = None,
    cap: str | None = None,
) -> SelectExpr:
    """Typed atom builder. Use operators `&`, `|`, `~` to compose."""
    pairs: list[tuple[Literal["tool", "router", "cap"] | None, str]] = []
    if name is not None:
        pairs.append((None, name))
    if tool is not None:
        pairs.append(("tool", tool))
    if router is not None:
        pairs.append(("router", router))
    if cap is not None:
        pairs.append(("cap", cap))
    if len(pairs) != 1:
        msg = "sel() takes exactly one of: positional name, tool=, router=, cap="
        raise TypeError(msg)
    ns, n = pairs[0]
    return SelectExpr(op="atom", atom=SelectAtom(name=n, namespace=ns))


def validate_atoms(expr: SelectExpr, *, known_routers: set[str], known_tools: set[str]) -> None:
    """Walk `expr`, raise `UnknownCapability` for unknown atoms."""
    known_caps = capabilities.known()
    known_all = known_caps | known_routers | known_tools | {"default"}
    pools: dict[str | None, set[str]] = {
        "cap": known_caps,
        "router": known_routers,
        "tool": known_tools,
        None: known_all,
    }
    stack: list[SelectExpr] = [expr]
    while stack:
        node = stack.pop()
        if node.op == "atom":
            assert node.atom is not None  # noqa: S101
            pool = pools[node.atom.namespace]
            if node.atom.name not in pool:
                hits = difflib.get_close_matches(node.atom.name, sorted(pool), n=2)
                raise UnknownCapability(node.atom.name, suggestions=hits)
        else:
            stack.extend(node.children)


__all__ = ["sel", "validate_atoms"]
