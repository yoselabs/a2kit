"""CEL-based filter expressions for tool selection.

Public API:
    compile(expr) -> CelProgram
    evaluate(program, atoms) -> bool
    validate_atoms(expr, known_atoms) -> None
    UnknownAtomError

Grammar is real CEL via cel-python: `&&`, `||`, `!`, with atoms as field
accesses (`tool.foo`, `cap.write`, `surface.mcp`) or bare booleans
(`default`). Legacy a2kit `--select` syntax (`and`/`or`/`not`, `tool:foo`,
`cap:foo`) is NOT supported. Migration table:

    Legacy                                CEL
    ------------------------------------  ------------------------------------
    default and not write                 default && !write
    default and not write and surface.mcp default && !write && surface.mcp
    surface.cli                           surface.cli
    cap:write                             cap.write
    tool:foo                              tool.foo
    default                               default
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

import celpy
import celpy.celtypes as cel_types
from lark import Tree

from a2kit.exceptions import InvalidFilterExpression


class UnknownAtomError(InvalidFilterExpression):
    """Raised when an expression references an atom not in the known set."""

    def __init__(self, atom: str, expr: str, known: set[str]) -> None:
        self.atom = atom
        self.known = known
        suggestions = difflib.get_close_matches(atom, sorted(known), n=3, cutoff=0.6)
        if suggestions:
            hint = f"unknown atom {atom!r}; did you mean {', '.join(repr(s) for s in suggestions)}?"
        else:
            hint = f"unknown atom {atom!r}; known atoms: {', '.join(sorted(known)) or '<none>'}"
        super().__init__(expr, hint)


@dataclass(frozen=True)
class CelProgram:
    """Compiled CEL expression. Holds the source, parse tree, and runner."""

    expr: str
    tree: Tree
    runner: celpy.Runner


_ENV = celpy.Environment()


def compile(expr: str) -> CelProgram:  # noqa: A001 - matches public API contract
    """Parse `expr` as CEL. Raise InvalidFilterExpression on syntax error."""
    if not isinstance(expr, str) or not expr.strip():
        raise InvalidFilterExpression(expr, "expression is empty")
    try:
        tree = _ENV.compile(expr)
    except celpy.CELParseError as e:
        raise InvalidFilterExpression(expr, f"CEL parse error: {e}") from e
    runner = _ENV.program(tree)
    return CelProgram(expr=expr, tree=tree, runner=runner)


def evaluate(program: CelProgram, atoms: dict[str, Any]) -> bool:
    """Evaluate `program` against `atoms`. Return bool. Raise on non-bool / unknown atom."""
    activation = _to_activation(atoms)
    try:
        result = program.runner.evaluate(activation)
    except celpy.CELEvalError as e:
        # KeyError args carry the missing atom name in cel-python 0.5.x
        missing: str | None = None
        if e.args and isinstance(e.args[-1], tuple) and e.args[-1]:
            candidate = e.args[-1][0]
            if isinstance(candidate, str):
                missing = candidate
        if missing is not None:
            known = _collect_atom_names(atoms)
            raise UnknownAtomError(missing, program.expr, known) from e
        raise InvalidFilterExpression(program.expr, f"CEL evaluation error: {e}") from e

    # Unwrap celpy.celtypes.BoolType (subclass of int) — accept only true bool semantics.
    if isinstance(result, cel_types.BoolType):
        return bool(result)
    if isinstance(result, bool):
        return result
    raise InvalidFilterExpression(
        program.expr,
        f"expression must evaluate to bool; got {type(result).__name__} ({result!r})",
    )


def validate_atoms(expr: str, known_atoms: set[str]) -> None:
    """Strict-mode check: raise UnknownAtomError for any referenced atom not in `known_atoms`.

    Walks the CEL parse tree, collecting bare identifiers (`default`) and
    top-level dotted references (`tool.foo`, `cap.write`, `surface.mcp`).
    """
    program = compile(expr)
    referenced = _extract_atoms(program.tree)
    for atom in referenced:
        if atom not in known_atoms:
            raise UnknownAtomError(atom, expr, known_atoms)


# ---- internals ----


def _to_activation(atoms: dict[str, Any]) -> dict[str, Any]:
    """Convert a nested atoms dict to a celpy activation (BoolType / MapType leaves)."""
    out: dict[str, Any] = {}
    for k, v in atoms.items():
        out[k] = _convert(v)
    return out


def _convert(v: Any) -> Any:
    if isinstance(v, bool):
        return cel_types.BoolType(v)
    if isinstance(v, dict):
        return cel_types.MapType({cel_types.StringType(k): _convert(sub) for k, sub in v.items()})
    return v


def _collect_atom_names(atoms: dict[str, Any]) -> set[str]:
    """Flatten an atoms dict to the set of all referenceable names (top + dotted)."""
    names: set[str] = set()
    for k, v in atoms.items():
        names.add(k)
        if isinstance(v, dict):
            for sub in v:
                names.add(f"{k}.{sub}")
    return names


def _extract_atoms(tree: Tree) -> set[str]:
    """Collect identifiers and dotted member-accesses referenced in the parse tree.

    For `tool.foo && !write && surface.mcp`, returns
    `{"tool.foo", "write", "surface.mcp"}`. Bare top-level identifiers count;
    nested dotted access (e.g. `a.b.c`) is recorded as the full `a.b.c` path.
    """
    atoms: set[str] = set()
    # Track idents that are part of a dotted access so we don't double-count `tool` alone.
    consumed: set[int] = set()

    for node in tree.iter_subtrees():
        if node.data == "member_dot":
            path = _read_dotted(node)
            if path is not None:
                atoms.add(path)
                # mark every ident leaf inside this subtree as consumed
                for _ident in node.scan_values(lambda v: False):  # pragma: no cover - placeholder
                    pass
                for sub in node.iter_subtrees():
                    if sub.data == "ident":
                        consumed.add(id(sub))

    for node in tree.iter_subtrees():
        if node.data == "ident" and id(node) not in consumed:
            # ident has a single Token child carrying the name
            for child in node.children:
                name = str(child)
                # filter out CEL builtin pseudo-idents we don't care about
                if name and not name.startswith("_"):
                    atoms.add(name)

    return atoms


def _read_dotted(member_dot: Tree) -> str | None:
    """Read a member_dot subtree as a dotted path (e.g. `tool.foo` or `a.b.c`).

    Tree shape for `tool.foo`:
        member_dot
          member
            primary
              ident  tool
          foo                 ← Token IDENT
    """
    parts: list[str] = []

    def walk(node: Any) -> bool:
        if isinstance(node, Tree):
            if node.data == "member_dot":
                # left side first
                if not node.children:
                    return False
                if not walk(node.children[0]):
                    return False
                # remaining children are the dotted suffix tokens
                for tok in node.children[1:]:
                    parts.append(str(tok))
                return True
            if node.data == "ident":
                if node.children:
                    parts.append(str(node.children[0]))
                    return True
                return False
            # walk through wrapper nodes (member, primary, etc.)
            if len(node.children) == 1:
                return walk(node.children[0])
            return False
        return False

    if not walk(member_dot):
        return None
    return ".".join(parts) if parts else None
