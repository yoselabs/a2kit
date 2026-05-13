"""Transport-neutral tool schema introspection.

Pure-Python schema generator (pydantic + typing). Strips DI / context
parameters via :mod:`a2kit.signature` and builds a pydantic model from
the remaining kwonly params. Returns a dict with ``name``,
``description``, ``inputSchema``, ``outputSchema``, ``annotations``,
``tags``, ``meta``, ``reportSchema``.

No ``fastmcp`` import. No ``click`` import. Imported lazily via
``a2kit.__init__._LAZY_MODULES`` so ``import a2kit`` doesn't pay for it.

Consumed by the CLI ``schema`` subcommand, the in-process test client's
snapshot helpers, and the public re-export ``a2kit.testing.compute_schema``.
"""

from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from pydantic import create_model

from a2kit.metadata import get_meta
from a2kit.signature import wire_input_params

if TYPE_CHECKING:
    from collections.abc import Callable


def _resolved_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    from typing import get_type_hints

    try:
        return get_type_hints(fn)
    except Exception:  # noqa: BLE001
        return {}


def _annotation_to_field(param: inspect.Parameter, resolved: dict[str, Any]) -> tuple[Any, Any]:
    ann = resolved.get(param.name, param.annotation)
    if ann is inspect.Parameter.empty:
        ann = Any
    default = param.default if param.default is not inspect.Parameter.empty else ...
    return (ann, default)


def _input_schema(fn: Callable[..., Any], container: Any | None = None) -> dict[str, Any]:
    params, wire_scopes_needed = wire_input_params(fn, container)
    needs_connection = "connection" in wire_scopes_needed
    if not params and not needs_connection:
        return {"type": "object", "properties": {}}
    resolved = _resolved_hints(fn)
    fields: dict[str, Any] = {name: _annotation_to_field(p, resolved) for name, p in params.items()}
    if needs_connection and "connection" not in fields:
        fields["connection"] = (str, ...)
    fn_name = getattr(fn, "__name__", "tool")
    model = create_model(f"{fn_name}_in", **fields)
    return model.model_json_schema()


def _output_schema(fn: Callable[..., Any]) -> dict[str, Any] | None:
    resolved = _resolved_hints(fn)
    ret = resolved.get("return", fn.__annotations__.get("return"))
    if ret is None or ret is inspect.Parameter.empty:
        return None
    fn_name = getattr(fn, "__name__", "tool")
    try:
        model = create_model(f"{fn_name}_out", value=(ret, ...))
        schema = model.model_json_schema()
    except Exception:  # noqa: BLE001
        return None
    props = schema.get("properties", {})
    return props.get("value", schema)


def _annotations_dict(annotations: Any) -> dict[str, Any]:
    """Fallback path used only when meta is None (rare)."""
    if annotations is None:
        return {}
    if is_dataclass(annotations):
        return asdict(annotations)
    dump = getattr(annotations, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    return {}


def compute_schema(fn: Callable[..., Any], container: Any | None = None) -> dict[str, Any]:
    """Return a dict describing ``fn`` for schema snapshots / CLI dump.

    Output keys: ``name``, ``description``, ``inputSchema``, ``outputSchema``,
    ``annotations``, ``tags``, ``meta``. No ``fastmcp`` import.
    """
    meta = get_meta(fn)
    name = meta.tool_name if meta is not None else getattr(fn, "__name__", "<callable>")
    description = (fn.__doc__ or "").strip()
    out: dict[str, Any] = {
        "name": name,
        "description": description,
        "inputSchema": _input_schema(fn, container),
    }
    output_schema = _output_schema(fn)
    if output_schema is not None:
        out["outputSchema"] = output_schema
    if meta is not None:
        # ``annotations_as_dict`` skips the ``mcp.types`` import that
        # ``meta.annotations`` (the property) would trigger. ~400ms shaved
        # off cold-start ``--schema`` invocations.
        out["annotations"] = meta.annotations_as_dict()
        out["tags"] = sorted(meta.tags)
        out["meta"] = {
            "verb": meta.verb,
            "router": meta.extras.router_slug,  # noqa: A2K-CORE-CLEAN
        }
        report_schema = meta.extras.report_schema  # noqa: A2K-CORE-CLEAN
        if report_schema is not None:  # noqa: A2K-CORE-CLEAN
            out["reportSchema"] = report_schema  # noqa: A2K-CORE-CLEAN
    return out


__all__ = ["compute_schema"]
