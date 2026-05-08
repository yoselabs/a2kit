"""Tool decorator — composes with FastMCP's `@server.tool()`, does not replace it.

v0.2 makes the decorator *fat*: connection lookup, token resolution, write-mode
enforcement, tool-call envelope contamination guard, OTel spans, streaming
awareness — all opt-in, all behind keyword args, all defaulting to v0.1's
behaviour. A bare `@a2kit.tool()` (or the legacy `@a2kit.tools.tool()`) is
byte-equivalent to v0.1.

Behaviour order, before the wrapped function runs:

1. Connection lookup (if `connection_param` set) — finds the connection key in
   bound args, looks it up in `store`, raises `ConnectionNotFound` enumerating
   available names if missing. Ephemeral connections are merged into `store` at
   the Router level (v0.8); the decorator no longer takes an `ephemeral=` kwarg.
2. Token resolution — recursively resolves `${ENV}` / `op://` / literals on every
   string field of the loaded `ConnectionInfo`. The resolved info is exposed via
   `Router.context.info()` (or a hand-built `_RouterContext`); the v0.6
   `info=` kwarg-injection path was removed in v0.7.
3. Read-only enforcement — if `write=True` and `info.read_only` is True, raises
   `WriteNotAllowed`.
4. Tool-call envelope guard — every `str` argument is checked for the
   `<parameter name=` pattern (tool-call-envelope contamination observed in
   production). Disable via `tool_call_guard=False`.
5. Run wrapped function (await if coroutine).
6. Refuse `-> str` returns (decoration time) + preserve return annotation (v0.1).
7. Error enrichment via the optional `enricher` (v0.1).
8. OTel span — if `otel=True` AND `opentelemetry` is installed AND a non-default
   tracer provider is configured, wraps the call in `a2kit.tool.<name>`. No-op
   otherwise.
9. Streaming awareness — if `streaming=True` and the wrapped function returns an
   async iterator, the decorator collects items into a list on stdio transport
   and yields them through on HTTP. Transport is read from the thread-local
   `_current_transport` set by `MCPRunner`. No transport set → stdio.

Standalone helper `assert_clean_string(value, param_name)` exposed for tests
or non-decorated use.

v0.11: split from a single `tools.py` into a package. Public surface is
unchanged. Internal modules:

- `_runtime.py`    — transport seam, contamination guard, async-iter
- `_signature.py`  — annotation resolution, listview, signature splicing
- `_connection.py` — connection lookup, key coercion, info DI
- `_metadata.py`   — capability compute, doc injection, ToolMetadata, register
- `_decorator.py`  — the `tool()` decorator itself
"""

from a2kit.tools._connection import (
    _lookup_connection_async,
    _lookup_connection_sync,
    _resolve_connection_key,
    _resolve_info_strings,
)
from a2kit.tools._decorator import tool
from a2kit.tools._metadata import (
    ToolMetadata,
    _auto_inject_enabled,
    _compute_tool_capabilities,
    _inject_param_docs,
    _register_with_server,
    _reset_auto_inject_cache,
    tool_metadata,
)
from a2kit.tools._runtime import (
    _check_tool_call_contamination,
    _consume_or_passthrough_async,
    _get_current_transport,
    _set_current_transport,
    assert_clean_string,
)
from a2kit.tools._signature import (
    _check_return_annotation,
    _decode_cursor,
    _encode_cursor,
    _listview_apply,
    _listview_extract_local,
    _listview_local_params,
    _resolve_return_annotation,
    _splice_wrapper_signature,
    _verify_passthrough_params,
    preserve_return_annotation,
)
from a2kit.tools._verbs import list as list_tool
from a2kit.tools._verbs import read as read_tool
from a2kit.tools._verbs import write as write_tool

__all__ = [
    "ToolMetadata",
    "_auto_inject_enabled",
    "_check_return_annotation",
    "_check_tool_call_contamination",
    "_compute_tool_capabilities",
    "_consume_or_passthrough_async",
    "_decode_cursor",
    "_encode_cursor",
    "_get_current_transport",
    "_inject_param_docs",
    "_listview_apply",
    "_listview_extract_local",
    "_listview_local_params",
    "_lookup_connection_async",
    "_lookup_connection_sync",
    "_register_with_server",
    "_reset_auto_inject_cache",
    "_resolve_connection_key",
    "_resolve_info_strings",
    "_resolve_return_annotation",
    "_set_current_transport",
    "_splice_wrapper_signature",
    "_verify_passthrough_params",
    "assert_clean_string",
    "list_tool",
    "preserve_return_annotation",
    "read_tool",
    "tool",
    "tool_metadata",
    "write_tool",
]
