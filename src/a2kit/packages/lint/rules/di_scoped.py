"""di-scoped-lifecycle anti-pattern rules (A2K015, A2K016, A2K017).

- **A2K015** — `_ensure()` lazy-init pattern on a class that's registered
  via `app.provide(...)`. The v0.36+ container enters the resource on
  first `Container.get(T)` and unwinds at scope exit — the `_ensure`
  pattern duplicates that machinery and leaks state on exception.

- **A2K016** — parameterized lambda as a DI factory. Lambdas can't carry
  parameter annotations, so chain resolution can't see the param types.
  Use a `def` factory (or pass the class directly to `provide`) so DI
  can introspect the constructor.

- **A2K017** — `Lazy[T]` suggestion. A tool parameter typed as a
  registered DI type that's only used inside conditional branches in
  the body would benefit from `Lazy[T]` (the resource isn't entered
  unless the branch fires). Non-binding warning — heuristic only.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from a2kit.packages.lint.static import (
    A2K015,
    A2K016,
    A2K017,
    LintMessage,
    _msg,
    parse_noqa,
    suppressed,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


# --- A2K015 — `_ensure()` lazy-init pattern -------------------------------


def _provided_class_names(tree: ast.AST) -> set[str]:
    """Return class names mentioned as the first positional arg to ``app.provide(...)``.

    Catches the two common shapes:
    - ``app.provide(SomeClass)``
    - ``app.provide(SomeClass, factory, ...)``
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "provide":
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Name):
            names.add(first.id)
    return names


def rule_ensure_pattern(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    provided = _provided_class_names(tree)
    if not provided:
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in provided:
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "_ensure":
                continue
            line = getattr(item, "lineno", 1)
            if suppressed(noqa, A2K015, line):
                continue
            yield _msg(
                A2K015,
                filename,
                item,
                (
                    f"{node.name}._ensure() is a v0.35 lazy-init pattern; "
                    "v0.36+ containers enter resources via __aenter__ on "
                    "first Container.get(T). Replace _ensure with "
                    "__aenter__/__aexit__ on the resource so the framework "
                    "drives lifecycle. See ANTIPATTERNS.md v0.36 section."
                ),
            )


# --- A2K016 — parameterized lambda as a DI factory ------------------------


def rule_parameterized_lambda_factory(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "provide":
            continue
        # provide(Type, factory) — factory is positional arg index 1
        if len(node.args) < 2:
            continue
        factory = node.args[1]
        if not isinstance(factory, ast.Lambda):
            continue
        args = factory.args
        # A lambda with no positional or keyword params is fine
        # (constant-factory pattern). One with params CAN'T carry type
        # annotations under Python's lambda syntax, so DI chain
        # resolution will fail.
        if not args.args and not args.kwonlyargs and not args.posonlyargs:
            continue
        line = getattr(factory, "lineno", 1)
        if suppressed(noqa, A2K016, line):
            continue
        yield _msg(
            A2K016,
            filename,
            factory,
            (
                "parameterized lambda as DI factory — lambdas can't carry "
                "parameter type annotations, so chain resolution can't see "
                "the param types. Use a `def` factory (or pass the class "
                "directly to provide) so DI introspects the constructor. "
                "See ANTIPATTERNS.md v0.36 section."
            ),
        )


# --- A2K017 — Lazy[T] suggestion for conditional-use deps -----------------


_PRIMITIVE_NAMES = frozenset({"str", "int", "float", "bool", "bytes", "None"})


def _is_primitive_ann(ann: ast.expr) -> bool:
    """True for ``str``/``int``/etc., ``X | None``, ``Optional[X]`` over primitives."""
    if isinstance(ann, ast.Name) and ann.id in _PRIMITIVE_NAMES:
        return True
    if isinstance(ann, ast.Constant) and ann.value is None:
        return True
    # PEP 604: `X | None` parses as ``BinOp(left, BitOr, right)``.
    if isinstance(ann, ast.BinOp) and isinstance(ann.op, ast.BitOr):
        return _is_primitive_ann(ann.left) and _is_primitive_ann(ann.right)
    # ``Optional[X]`` → Subscript(value=Name('Optional'), slice=X).
    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "Optional":
        return _is_primitive_ann(ann.slice)
    return False


def _is_typed_param(arg: ast.arg) -> bool:
    """True when an arg has a non-trivial type annotation (not str/int/bool/etc)."""
    ann = arg.annotation
    if ann is None:
        return False
    if _is_primitive_ann(ann):
        return False
    # Lazy[T] params already optimized; skip.
    return not (isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) and ann.value.id == "Lazy")


def _name_referenced_only_in_conditionals(fn: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:  # noqa: C901 -- single AST walker; splitting would obscure the cond_depth state
    """True if ``name`` is referenced ONLY inside ``If`` / ``IfExp`` / ``Try`` branches.

    Best-effort. Returns False if the name has any unconditional reference
    in the function body (including via attribute access at module level
    of the function).
    """
    seen_anywhere = False
    seen_only_conditional = True

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._cond_depth = 0

        def _check_name(self, node: ast.AST) -> None:  # noqa: ARG002 -- node not used but kept for symmetry with NodeVisitor methods
            nonlocal seen_anywhere, seen_only_conditional
            seen_anywhere = True
            if self._cond_depth == 0:
                seen_only_conditional = False

        def visit_If(self, node: ast.If) -> None:
            self._cond_depth += 1
            self.generic_visit(node)
            self._cond_depth -= 1

        def visit_IfExp(self, node: ast.IfExp) -> None:
            self._cond_depth += 1
            self.generic_visit(node)
            self._cond_depth -= 1

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == name and isinstance(node.ctx, ast.Load):
                self._check_name(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            # `name.foo` — count as a use of `name`
            if isinstance(node.value, ast.Name) and node.value.id == name:
                self._check_name(node.value)
            self.generic_visit(node)

    for stmt in fn.body:
        _Visitor().visit(stmt)

    return seen_anywhere and seen_only_conditional


def rule_lazy_t_suggestion(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    noqa = parse_noqa(source)
    # Only look at functions decorated with @a2kit.read/write/list_ (tool methods).
    from a2kit.packages.lint.rules import is_a2kit_tool_decorator

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(is_a2kit_tool_decorator(d) for d in node.decorator_list):
            continue

        # Walk each typed parameter.
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            if arg.arg == "self":
                continue
            if not _is_typed_param(arg):
                continue
            if not _name_referenced_only_in_conditionals(node, arg.arg):
                continue
            line = getattr(arg, "lineno", node.lineno)
            if suppressed(noqa, A2K017, line):
                continue
            yield _msg(
                A2K017,
                filename,
                arg,
                (
                    f"tool param {arg.arg!r} is only used inside conditional "
                    "branches — consider `Lazy[T]` so the resource isn't "
                    "entered unless the branch fires. Non-binding hint; "
                    "see docs/patterns/conditional-deps.md."
                ),
            )


__all__ = [
    "rule_ensure_pattern",
    "rule_lazy_t_suggestion",
    "rule_parameterized_lambda_factory",
]
