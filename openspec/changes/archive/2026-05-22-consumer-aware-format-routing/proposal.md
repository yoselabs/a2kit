## Why

a2kit's format routing (JSON / TSV / page-tsv) is wired into the CLI
surface only. The MCP surface ships raw JSON — so an LLM consuming a
tool over MCP pays full token cost, even though `ToolDescriptor`
already carries the right `format_hint`. The `TestClient` even
format-routes MCP results itself, proving the wiring was *intended* and
is simply missing.

Code mode compounds this. There is no defined story for the two
different consumers of a tool result: the **sandbox code** that calls
`call_tool` needs structured, manipulable values; the **LLM** that
reads the `execute` output needs the fewest tokens. One result, two
incompatible needs.

The fix is to make rendering **consumer-aware**: the same tool result
renders differently depending on who consumes it. This is de-risked —
see `docs/SPIKE_CODEMODE_MARSHALLING.md` (7 findings, F1–F7) and the
42/42 model eval (`scripts/eval_codemode_correctness.py`).

## What Changes

- Rendering becomes a function of `(value, consumer)`. Consumer is one
  of `llm` (compress — TSV/page-tsv), `code` (structured — dataclasses),
  `machine` (JSON). The `code_mode` build flag selects the regime, so
  the consumer is fixed at build time — no runtime sniffing.
- **BREAKING.** The MCP surface now format-routes results: TSV/page-tsv
  goes into the MCP `content` block (the token-efficient, LLM-facing
  channel per MCP spec SEP-1624); structured JSON stays in
  `structuredContent`. MCP clients that parsed `content` as JSON see a
  changed shape.
- A new `build_encoding_plan` walks a return type, calling the
  existing `infer_format_hint` per `BaseModel` field, to emit a static
  **encoding plan** — so a flat array nested inside a larger object
  (not just a top-level `list`/`Page`) is TSV-compressed. page-tsv
  becomes the depth-1 case; `infer_format_hint` itself is unchanged.
- Code mode's `call_tool` returns **dataclasses**, not dicts —
  attribute access (`page.items[0].title`) in the sandbox. (pydantic
  models cannot cross the monty boundary; dict and dataclass are a hard
  XOR on access pattern — spike F1/F2.)
- a2kit ships a custom monty `SandboxProvider` that generates
  type-stubs from tool descriptors (dataclass mirrors + one
  `@overload` per tool), **type-checks the LLM's code before
  execution**, and feeds type errors into a one-retry loop. Catches
  typos, wrong access patterns, and hallucinated tool names
  pre-execution (spike F5).
- The `execute` output (dynamically typed) is rendered for the `llm`
  consumer by **value-driven** inference — shallow head-sampling, not a
  deep walk.
- a2kit owns the `execute` tool description — a load-bearing,
  eval-gated artifact stating the output contract precisely (last line
  is a bare expression; never a top-level `return`), attribute access,
  and encourage-flat. The eval (F7) becomes a permanent fixture.

## Capabilities

### New Capabilities

- `consumer-aware-rendering`: a tool result is rendered per a consumer
  profile (`llm` / `code` / `machine`); the `code_mode` flag selects
  the regime; format routing applies on every LLM-facing surface (CLI
  and MCP), never REST; `content` carries the compressed payload and
  `structuredContent` the structured one.
- `code-mode-sandbox-runtime`: `call_tool` marshals results as
  dataclasses; a a2kit `SandboxProvider` generates type-stubs from
  descriptors, type-checks LLM code pre-execution with a retry loop;
  a2kit owns the eval-gated `execute` description and contract.

### Modified Capabilities

None. The existing `infer_format_hint` (`type-driven-format-routing`)
is unchanged — `build_encoding_plan` (new, under
`consumer-aware-rendering`) wraps it for nested structures, and the
consumer profile decides whether its hint is honored at all.

## Impact

- Code: `packages/formatter/*` (encoding plan, value-driven inference,
  single-pass encoding), `packages/mcp/server.py` (format-routing
  wrapper returning `fastmcp.ToolResult`), `packages/codemode/*`
  (dataclass marshalling, `SandboxProvider`, `execute` description),
  `tool.py` (`ToolDescriptor` encoding plan).
- Dependencies: no new runtime deps — `pydantic-monty`'s `type_check`
  and `dataclass_registry` are existing API; `fastmcp.ToolResult` is
  the blessed serialization path (`tool_serializer` is deprecated).
- Surfaces: MCP `content` shape changes (BREAKING, above). CLI
  unchanged. REST surface — a binding requirement that it never
  format-compresses (machine consumer).
- Sibling work: an ADR records the consumer-profile decision; a
  permanent eval fixture follows from F7; `pushdown-listview` remains
  good hygiene but is no longer a hard dependency (spike F4).
