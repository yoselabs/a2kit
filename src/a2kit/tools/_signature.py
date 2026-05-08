"""Signature manipulation + list-view local concerns.

Decoration-time helpers:
  - `preserve_return_annotation` / `_resolve_return_annotation` /
    `_check_return_annotation` — wrangle PEP 563 string annotations.
  - `_listview_local_params` — build kit-injected kwonly params.
  - `_verify_passthrough_params` — fail loudly when fn sig and decorator
    kwargs disagree on Passthrough/Local mode.
  - `_splice_wrapper_signature` — synthesize the agent-facing signature.

Call-time helpers:
  - `_listview_extract_local` — pop Local kwargs from the call.
  - `_listview_apply` — post-process the result through filter/fields/paginate.
  - `_encode_cursor` / `_decode_cursor` — opaque pagination cursors.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from a2kit.exceptions import InvalidToolReturnTypeError
from a2kit.formatter import FormatName, ListViewMode, Page

if TYPE_CHECKING:
    from collections.abc import Callable


def preserve_return_annotation(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Copy `fn.__annotations__["return"]` onto the wrapper. Idempotent.

    Use directly if you want the FastMCP annotation-hygiene fix without the rest
    of `@tool(...)`. The trick: FastMCP walks `__wrapped__` chains via
    `inspect.signature(follow_wrapped=True, eval_str=True)`; setting the
    annotation on BOTH the wrapper and the wrapped survives that walk.
    """
    return_anno = fn.__annotations__.get("return")
    if return_anno is None:
        return fn
    fn.__annotations__["return"] = return_anno
    return fn


def _resolve_return_annotation(fn: Any, raw: Any) -> Any:
    """Resolve a possibly string-form return annotation to its runtime type.

    Under `from __future__ import annotations`, `fn.__annotations__["return"]`
    is a string. Use `inspect.get_annotations(eval_str=True)` so format-from-
    type detection sees `list[Row]` rather than `"list[Row]"`.
    """
    if raw is None or not isinstance(raw, str):
        return raw
    try:
        hints = inspect.get_annotations(fn, eval_str=True)
    except (NameError, AttributeError, SyntaxError):
        return None
    return hints.get("return")


def _check_return_annotation(fn: Callable[..., Any]) -> Any:
    """Reject `-> str` at decoration time. Returns the resolved annotation."""
    annos = getattr(fn, "__annotations__", {})
    if "return" not in annos:
        return None
    ret = annos["return"]
    if ret is str or ret == "str":
        raise InvalidToolReturnTypeError(getattr(fn, "__name__", "<tool>"))
    return ret


def _listview_local_params(
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> list[inspect.Parameter]:
    """Build kwonly params the kit injects for **Local** concerns.

    Passthrough concerns are owned by the function — the author declares
    them in the signature directly. Local concerns are kit-owned: the
    function never sees them, so we splice them into the wrapper sig.
    """
    extra: list[inspect.Parameter] = []
    kwonly = inspect.Parameter.KEYWORD_ONLY
    if filter_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("filter", kwonly, default="", annotation=str))
    if fields_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("fields", kwonly, default=None, annotation="list[str] | None"))
    if pagination_mode is ListViewMode.LOCAL:
        extra.append(inspect.Parameter("limit", kwonly, default=50, annotation=int))
        extra.append(inspect.Parameter("cursor", kwonly, default=None, annotation="str | None"))
    return extra


def _verify_passthrough_params(
    fn: Any,
    sig: inspect.Signature,
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> None:
    """Each Passthrough concern requires its param on the fn signature.

    Mode mismatch is an author bug — fail loudly at decoration so the agent
    never sees a tool that promises filter/fields/pagination passthrough
    but silently drops the kwarg.
    """
    expected: list[str] = []
    if filter_mode is ListViewMode.PASSTHROUGH:
        expected.append("filter")
    if fields_mode is ListViewMode.PASSTHROUGH:
        expected.append("fields")
    if pagination_mode is ListViewMode.PASSTHROUGH:
        expected.extend(("limit", "cursor"))
    missing = [name for name in expected if name not in sig.parameters]
    if missing:
        msg = (
            f"Passthrough mode declared on {fn.__name__!r} but the function does "
            f"not accept {missing}. Either declare them in your function "
            "signature (Passthrough = your tool body handles them) or switch "
            "the matching decorator kwarg to Local."
        )
        raise ValueError(msg)


def _splice_wrapper_signature(
    wrapper: Any,
    fn: Any,
    sig: inspect.Signature,
    extra: list[inspect.Parameter],
    *,
    hide_names: set[str] | None = None,
) -> None:
    """Build the agent-facing wrapper signature.

    - Splices `extra` (kit-injected kwonly params: `connection`, list-view
      knobs) before any VAR_KEYWORD on the fn.
    - Removes any params named in `hide_names` (used to hide DI-injected
      params like the typed `info: WidgetConn`).

    FastMCP reads `inspect.signature(wrapper, follow_wrapped=True)`;
    setting `wrapper.__signature__` short-circuits the `__wrapped__` walk so
    the synthetic sig wins.
    """
    hide = hide_names or set()
    if not extra and not hide:
        return
    collisions = [p.name for p in extra if p.name in sig.parameters]
    if collisions:
        msg = (
            f"Kit-injected params {collisions} collide with parameters "
            f"declared on {fn.__name__!r}. Either rename your function param, "
            "drop the matching decorator kwarg, or switch list-view modes to "
            "Passthrough."
        )
        raise ValueError(msg)
    params = [p for name, p in sig.parameters.items() if name not in hide]
    insert_at = next(
        (i for i, p in enumerate(params) if p.kind == inspect.Parameter.VAR_KEYWORD),
        len(params),
    )
    new_params = params[:insert_at] + extra + params[insert_at:]
    wrapper.__signature__ = sig.replace(parameters=new_params)
    extras_anno = {p.name: p.annotation for p in extra}
    wrapper.__annotations__ = {k: v for k, v in {**wrapper.__annotations__, **extras_anno}.items() if k not in hide}
    fn.__annotations__ = {**fn.__annotations__, **extras_anno}


def _encode_cursor(offset: int) -> str:
    """Opaque base64 string from an integer offset."""
    import base64  # noqa: PLC0415

    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    """Reverse `_encode_cursor`. Invalid input → 0 (start of list)."""
    if not cursor:
        return 0
    import base64  # noqa: PLC0415

    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return max(0, int(base64.urlsafe_b64decode(padded.encode()).decode()))
    except (ValueError, UnicodeDecodeError):
        return 0


def _listview_extract_local(
    kwargs: dict[str, Any],
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
) -> dict[str, Any]:
    """Pop Local concern kwargs out of `kwargs` so the fn never sees them.

    Passthrough kwargs stay in `kwargs` for the fn body to handle.
    Returns a state dict with whatever the kit needs for post-processing.
    """
    state: dict[str, Any] = {}
    if filter_mode is ListViewMode.LOCAL:
        raw = kwargs.pop("filter", "")
        state["filter"] = raw if isinstance(raw, str) else ""
    if fields_mode is ListViewMode.LOCAL:
        raw_f = kwargs.pop("fields", None)
        state["fields"] = [str(f) for f in raw_f] if isinstance(raw_f, list) else None
    if pagination_mode is ListViewMode.LOCAL:
        raw_limit = kwargs.pop("limit", 50)
        state["limit"] = raw_limit if isinstance(raw_limit, int) and raw_limit > 0 else 50
        state["cursor"] = kwargs.pop("cursor", None)
    return state


def _listview_apply(
    result: Any,
    state: dict[str, Any],
    *,
    filter_mode: ListViewMode | None,
    fields_mode: ListViewMode | None,
    pagination_mode: ListViewMode | None,
    format_hint: FormatName | None = None,
) -> Any:
    """Pipeline: unwrap Page → local filter → local fields → local paginate → Response.

    If `result` isn't a list or Page (e.g. a scalar / single dict), bypass
    list-view processing and return as-is. Pydantic-model items are dumped
    to dicts so the tabular encoder sees flat rows.
    """
    from a2kit.formatter import _dump_items as _fmt_dump_items  # noqa: PLC0415

    next_cursor: str | None = None
    items: list[dict[str, Any]]
    if isinstance(result, Page):
        items = _fmt_dump_items(list(result.items))
        next_cursor = result.next_cursor
    elif isinstance(result, list):
        items = _fmt_dump_items(result)
    else:
        return result

    if filter_mode is ListViewMode.LOCAL and state.get("filter"):
        from a2kit import projection  # noqa: PLC0415

        items = list(projection.filter_records(items, expr=state["filter"]))

    if fields_mode is ListViewMode.LOCAL and state.get("fields"):
        from a2kit import projection  # noqa: PLC0415

        items = list(projection.project_fields(items, fields=state["fields"]))

    if pagination_mode is ListViewMode.LOCAL:
        limit = state.get("limit", 50)
        offset = _decode_cursor(state.get("cursor"))
        sliced = items[offset : offset + limit]
        next_cursor = _encode_cursor(offset + limit) if offset + limit < len(items) else None
        items = sliced

    from a2kit.formatter import Response, format_response  # noqa: PLC0415

    base = format_response(items, format_hint=format_hint)
    return Response(format=base.format, data=base.data, truncated=base.truncated, next_cursor=next_cursor)


__all__ = [
    "_check_return_annotation",
    "_decode_cursor",
    "_encode_cursor",
    "_listview_apply",
    "_listview_extract_local",
    "_listview_local_params",
    "_resolve_return_annotation",
    "_splice_wrapper_signature",
    "_verify_passthrough_params",
    "preserve_return_annotation",
]
