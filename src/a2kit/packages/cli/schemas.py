"""``schema`` Click command + ``compute_schema`` helper.

Pure-Python schema generator (pydantic + typing). Strips DI / context
parameters via ``a2kit.signature`` and builds a pydantic model from the
remaining kwonly params. Returns a dict with ``name``, ``description``,
``inputSchema``, ``outputSchema``, ``annotations``, ``tags``, ``meta``.

No fastmcp import.

The testing-snapshot helper (``a2kit.packages.testing.snapshots.TOONSnapshotExtension``)
imports ``compute_schema`` from here.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, cast

import click
from pydantic import create_model

from a2kit.metadata import get_meta
from a2kit.packages.formatter import FormatHint, format_response, truncate
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
    params, needs_connection = wire_input_params(fn, container)
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
    ``annotations``, ``tags``, ``meta``. No fastmcp import.
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
        out["annotations"] = _annotations_dict(meta.annotations)
        out["tags"] = sorted(meta.tags)
        out["meta"] = {
            "verb": meta.verb,
            "router": meta.extra.get("a2kit.router_slug"),
        }
        report_schema = meta.extra.get("a2kit.report_schema")
        if report_schema is not None:
            out["reportSchema"] = report_schema
    return out


def _all_schemas(app: Any) -> dict[str, dict[str, Any]]:
    container = getattr(app, "container", lambda: None)()
    out: dict[str, dict[str, Any]] = {}
    for fn in app.tools():
        meta = get_meta(fn)
        name = meta.tool_name if meta is not None else fn.__name__
        out[name] = compute_schema(fn, container)
    return out


def build_schema_command(app: Any) -> click.Command:
    """Build a ``schema`` Click command bound to ``app`` via closure."""

    @click.command("schema")
    @click.argument("tool_name", required=False)
    @click.option(
        "--format",
        "fmt",
        type=click.Choice(["auto", "toon", "json"]),
        default="auto",
        show_default=True,
    )
    @click.option(
        "--jsonl",
        is_flag=True,
        default=False,
        help="Emit one JSON schema per line (only with --format=json).",
    )
    def schema_cmd(tool_name: str | None, fmt: str, jsonl: bool) -> None:
        """Print tool schemas. Default format is TOON (token-efficient for LLMs)."""
        schemas = _all_schemas(app)

        if tool_name is not None:
            result: Any = schemas.get(tool_name)
            if result is None:
                msg = f"Unknown tool: {tool_name!r}. Known: {sorted(schemas)}"
                raise click.UsageError(msg)
        else:
            result = schemas

        if jsonl:
            if fmt != "json":
                raise click.UsageError("--jsonl requires --format=json")
            if tool_name is not None:
                click.echo(truncate(json.dumps(result, separators=(",", ":"), default=str)))
                return
            for s in result.values():
                click.echo(truncate(json.dumps(s, separators=(",", ":"), default=str)))
            return

        response = format_response(result, format_hint=cast("FormatHint", fmt))
        click.echo(truncate(response.data))

    return schema_cmd


__all__ = ["build_schema_command", "compute_schema"]
