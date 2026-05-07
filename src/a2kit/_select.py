"""Select expression: parser, AST, evaluator, typed builder `sel()`.

Grammar: atoms (`issues`/`read`), optional namespace prefix
(`tool:`/`router:`/`cap:`), operators `and`/`or`/`not`, parentheses.

Tools carry a `set[str]` of tags (router name, caps, plus namespaced markers
`tool:<name>` / `router:<name>` / `cap:<name>`). `SelectExpr.evaluate(tags)`
returns bool.
"""

from __future__ import annotations

import difflib
import re
from typing import Literal, Self, overload

from pydantic import BaseModel, ConfigDict, Field, model_validator

from a2kit._capabilities import UnknownCapability, capabilities

_TOKEN_RE = re.compile(r"\s*(\(|\)|[a-zA-Z_][a-zA-Z0-9_:-]*)")
_DEFAULT_EXPR = "default and not write and not destructive"
_NAMESPACES: tuple[Literal["tool", "router", "cap"], ...] = ("tool", "router", "cap")


class SelectAtom(BaseModel):
    """One atom inside a SelectExpr."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_-]*$|^default$")
    namespace: Literal["tool", "router", "cap"] | None = None


class SelectExpr(BaseModel):
    """Pydantic AST node for a boolean expression over capability tags."""

    model_config = ConfigDict(frozen=False, extra="forbid")

    op: Literal["atom", "and", "or", "not"]
    atom: SelectAtom | None = None
    children: list[SelectExpr] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.op == "atom":
            if self.atom is None or self.children:
                msg = "atom node requires `atom` and no children"
                raise ValueError(msg)
        elif self.op == "not":
            if self.atom is not None or len(self.children) != 1:
                msg = "not node requires exactly one child and no atom"
                raise ValueError(msg)
        elif self.atom is not None or len(self.children) < 2:
            msg = f"{self.op!r} node requires >= 2 children and no atom"
            raise ValueError(msg)
        return self

    def __and__(self, other: SelectExpr) -> SelectExpr:
        return SelectExpr(op="and", children=[self, other])

    def __or__(self, other: SelectExpr) -> SelectExpr:
        return SelectExpr(op="or", children=[self, other])

    def __invert__(self) -> SelectExpr:
        return SelectExpr(op="not", children=[self])

    def evaluate(self, tool_tags: set[str]) -> bool:
        """Evaluate the expression against the tool's capability tag set."""
        if self.op == "atom":
            assert self.atom is not None  # noqa: S101
            return _atom_matches(self.atom, tool_tags)
        if self.op == "not":
            return not self.children[0].evaluate(tool_tags)
        if self.op == "and":
            return all(c.evaluate(tool_tags) for c in self.children)
        return any(c.evaluate(tool_tags) for c in self.children)


def _atom_matches(atom: SelectAtom, tags: set[str]) -> bool:
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


def _tokenise(text: str) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(text):
        m = _TOKEN_RE.match(text, i)
        if m is None:
            if text[i].isspace():
                i += 1
                continue
            msg = f"Unexpected character {text[i]!r} at position {i}"
            raise ValueError(msg)
        out.append(m.group(1))
        i = m.end()
    return out


def _parse_atom(tokens: list[str], pos: int) -> tuple[SelectExpr, int]:
    tok = tokens[pos]
    if tok == "(":
        node, pos = _parse_or(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            msg = "Expected closing parenthesis"
            raise ValueError(msg)
        return node, pos + 1
    pos += 1
    ns: Literal["tool", "router", "cap"] | None = None
    name = tok
    if ":" in tok:
        prefix, _, rest = tok.partition(":")
        if prefix not in _NAMESPACES:
            msg = f"Unknown atom namespace {prefix!r}; allowed: tool, router, cap"
            raise ValueError(msg)
        ns = prefix  # type: ignore[assignment]
        name = rest
    return SelectExpr(op="atom", atom=SelectAtom(name=name, namespace=ns)), pos


def _parse_not(tokens: list[str], pos: int) -> tuple[SelectExpr, int]:
    if pos < len(tokens) and tokens[pos] == "not":
        inner, pos = _parse_not(tokens, pos + 1)
        return SelectExpr(op="not", children=[inner]), pos
    return _parse_atom(tokens, pos)


def _parse_and(tokens: list[str], pos: int) -> tuple[SelectExpr, int]:
    left, pos = _parse_not(tokens, pos)
    nodes = [left]
    while pos < len(tokens) and tokens[pos] == "and":
        right, pos = _parse_not(tokens, pos + 1)
        nodes.append(right)
    return (nodes[0] if len(nodes) == 1 else SelectExpr(op="and", children=nodes)), pos


def _parse_or(tokens: list[str], pos: int) -> tuple[SelectExpr, int]:
    left, pos = _parse_and(tokens, pos)
    nodes = [left]
    while pos < len(tokens) and tokens[pos] == "or":
        right, pos = _parse_and(tokens, pos + 1)
        nodes.append(right)
    return (nodes[0] if len(nodes) == 1 else SelectExpr(op="or", children=nodes)), pos


def parse_select(text: str) -> SelectExpr:
    """Parse a `--select` expression string into a `SelectExpr`."""
    if not text.strip():
        msg = "Empty select expression"
        raise ValueError(msg)
    tokens = _tokenise(text)
    node, pos = _parse_or(tokens, 0)
    if pos != len(tokens):
        msg = f"Unexpected token at end: {tokens[pos]!r}"
        raise ValueError(msg)
    return node


def default_select_expr() -> SelectExpr:
    """The default `--select` expression: read-only, non-destructive."""
    return parse_select(_DEFAULT_EXPR)


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


__all__ = [
    "SelectAtom",
    "SelectExpr",
    "default_select_expr",
    "parse_select",
    "sel",
    "validate_atoms",
]
