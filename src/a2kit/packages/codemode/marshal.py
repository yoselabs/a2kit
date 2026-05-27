"""dict→dataclass marshalling for the code-mode sandbox — ``call_tool`` results cross the Monty boundary as dataclasses."""

from __future__ import annotations

import dataclasses
import re
import types
from typing import Any, Union, get_args, get_origin

# Mirror types are stable per pydantic model — cache globally so the same
# model always yields the same dataclass (stubs and runtime stay in lockstep).
_MIRROR_CACHE: dict[type, type] = {}
_NAME_USED: dict[str, type] = {}


def _sanitize(name: str) -> str:
    """Turn a (possibly generic) model name into a valid Python identifier —
    ``Page[Task]`` → ``Page_Task``.
    """
    cleaned = re.sub(r"\W", "_", name).strip("_")
    return cleaned or "Mirror"


from a2kit.packages.formatter import is_basemodel as _is_basemodel  # noqa: E402 -- R7: front-door import of canonical


def dataclass_mirror(model: type) -> type:
    """Return (and cache) a ``@dataclass`` mirroring ``model``'s field names.

    Fields are typed ``Any`` at runtime — marshalling rebuilds the structure
    from the return-type annotation, so the runtime mirror only needs the
    field slots. The stub text (see ``stubs.py``) carries the real types for
    the type-checker.
    """
    cached = _MIRROR_CACHE.get(model)
    if cached is not None:
        return cached

    base = _sanitize(getattr(model, "__name__", "Mirror"))
    name = base
    while name in _NAME_USED and _NAME_USED[name] is not model:
        name += "_"

    fields = [(fname, Any, dataclasses.field(default=None)) for fname in getattr(model, "model_fields", {})]
    mirror = dataclasses.make_dataclass(name, fields)
    _MIRROR_CACHE[model] = mirror
    _NAME_USED[name] = model
    return mirror


def marshal_result(value: Any, annotation: Any) -> Any:  # noqa: PLR0911 -- one return per type shape reads clearer than nesting
    """Rebuild ``value`` (plain JSON data) into dataclass mirrors per ``annotation``.

    A ``BaseModel`` (or parametrized generic such as ``Page[Task]``) becomes
    a mirror dataclass instance; ``list`` / ``tuple`` recurse into the item
    type; ``X | None`` marshals the non-``None`` branch. Scalars, plain
    dicts, and anything untyped pass through unchanged.
    """
    if value is None:
        return None

    cls = _is_basemodel(annotation)
    if cls is not None:
        if not isinstance(value, dict):
            return value
        mirror = dataclass_mirror(cls)
        kwargs = {fname: marshal_result(value.get(fname), mf.annotation) for fname, mf in cls.model_fields.items()}
        return mirror(**kwargs)

    origin = get_origin(annotation)

    if origin in (list, tuple):
        args = get_args(annotation)
        item_ann = args[0] if args else Any
        if isinstance(value, (list, tuple)):
            return [marshal_result(v, item_ann) for v in value]
        return value

    if origin is Union or isinstance(annotation, types.UnionType):
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            if _is_basemodel(arg) and isinstance(value, dict):
                return marshal_result(value, arg)
        return value

    # Scalars, plain dicts, Any, unresolved — pass through.
    return value


def collect_models(annotation: Any, acc: list[type]) -> None:
    """Append every ``BaseModel`` reachable in ``annotation`` to ``acc``,
    nested types before the types that reference them, de-duplicated.
    """
    if annotation is None:
        return
    cls = _is_basemodel(annotation)
    if cls is not None:
        for mf in cls.model_fields.values():
            collect_models(mf.annotation, acc)
        if cls not in acc:
            acc.append(cls)
        return
    for arg in get_args(annotation):
        collect_models(arg, acc)


def unwrap_tool_result(result: Any) -> Any:
    """Extract the sandbox-facing payload from a FastMCP ``ToolResult``.

    Prefers ``structured_content`` (a dict matching the output schema);
    falls back to concatenated text content. FastMCP wraps a non-object
    return as ``{"result": ...}`` with a ``wrap_result`` meta flag — this
    unwraps that so the marshaller sees the bare payload.
    """
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        meta = getattr(result, "meta", None) or {}
        wrapped = bool(isinstance(meta, dict) and meta.get("fastmcp", {}).get("wrap_result"))
        if wrapped and isinstance(structured, dict) and "result" in structured:
            return structured["result"]
        return structured

    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        parts.append(text if text is not None else str(block))
    return "\n".join(parts)


__all__ = [
    "collect_models",
    "dataclass_mirror",
    "marshal_result",
    "unwrap_tool_result",
]
