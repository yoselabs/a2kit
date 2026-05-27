"""A2K-NO-DICT-STR-ANY — flag ``dict[str, Any]`` fields on internal dataclasses.

Goal is *deliberate* ``Any`` use, not eradication. Legitimate sites
(JSON envelopes, wire-format payloads, kwarg pass-throughs to third-party
libs) keep their annotation but acknowledge it with
``# noqa: A2K-NO-DICT-STR-ANY -- <why>``.

Scope:
- Class is a ``@dataclass`` / ``@dataclass(frozen=True)`` (decorator
  named ``dataclass``) OR subclasses ``BaseModel`` (pydantic).
- Field is an ``AnnAssign`` whose annotation contains
  ``dict[str, Any]`` or ``Dict[str, Any]`` (with or without
  ``| None`` / ``Optional`` wrapping).

Out of scope:
- Function parameter annotations (covered by ty + reviewer judgement).
- ``Mapping[str, Any]`` / ``MutableMapping[str, Any]`` (intentionally
  narrower than ``dict``).

Rule code: ``A2K-NO-DICT-STR-ANY``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from a2kit.packages.lint.static import LintMessage


def _is_dataclass_decorator(dec: ast.expr) -> bool:
    """``@dataclass`` / ``@dataclass(frozen=True)`` / ``@dataclasses.dataclass``."""
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id == "dataclass"
    if isinstance(target, ast.Attribute):
        return target.attr == "dataclass"
    return False


from a2kit.packages.lint.rules._ast_helpers import is_basemodel_base as _is_basemodel_base  # noqa: E402 -- shared helper (R9)


def _annotation_has_dict_str_any(node: ast.expr) -> bool:
    """True iff the annotation tree contains a ``dict[str, Any]`` shape."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Subscript):
            continue
        value = sub.value
        name = value.id if isinstance(value, ast.Name) else value.attr if isinstance(value, ast.Attribute) else None
        if name not in {"dict", "Dict"}:
            continue
        slice_node = sub.slice
        if not isinstance(slice_node, ast.Tuple) or len(slice_node.elts) != 2:
            continue
        key, val = slice_node.elts
        key_is_str = isinstance(key, ast.Name) and key.id == "str"
        val_is_any = (isinstance(val, ast.Name) and val.id == "Any") or (isinstance(val, ast.Attribute) and val.attr == "Any")
        if key_is_str and val_is_any:
            return True
    return False


def rule_no_dict_str_any(tree: ast.AST, filename: str, source: str) -> Iterable[LintMessage]:
    """Yield A2K-NO-DICT-STR-ANY findings for ``tree``."""
    from a2kit.packages.lint.static import A2K_NO_DICT_STR_ANY, LintMessage, is_fixture_path, parse_noqa, suppressed

    if is_fixture_path(filename):
        return
    noqa = parse_noqa(source)
    body = tree.body if isinstance(tree, ast.Module) else []
    for node in body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_dc = any(_is_dataclass_decorator(d) for d in node.decorator_list)
        is_bm = any(_is_basemodel_base(b) for b in node.bases)
        if not (is_dc or is_bm):
            continue
        for item in node.body:
            if not isinstance(item, ast.AnnAssign) or item.annotation is None:
                continue
            if not _annotation_has_dict_str_any(item.annotation):
                continue
            if suppressed(noqa, A2K_NO_DICT_STR_ANY, item.lineno):
                continue
            field_name = ast.unparse(item.target)
            yield LintMessage(
                rule=A2K_NO_DICT_STR_ANY,
                filename=filename,
                line=item.lineno,
                col=item.col_offset,
                message=(
                    f"{node.name}.{field_name}: `dict[str, Any]` on an internal "
                    "dataclass/BaseModel field. Tighten the value type, or, if "
                    "the looseness is deliberate (wire envelope, third-party "
                    "kwarg pass-through), suppress with "
                    "`# noqa: A2K-NO-DICT-STR-ANY -- <why>`."
                ),
            )


__all__ = ["rule_no_dict_str_any"]
