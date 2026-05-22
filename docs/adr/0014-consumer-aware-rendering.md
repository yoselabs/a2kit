---
id: "0014"
status: proposed
date: 2026-05-22
last_reviewed: 2026-05-22
supersedes: []
superseded_by: null
tags: [formatter, rendering, mcp, code-execution, surface]
deciders: [Denis Tomilin]
---

# ADR 0014: Consumer-aware rendering — `(value, consumer)` is the rendering seam

## Status

Proposed, 2026-05-22. Implements the consumer-aware-format-routing
OpenSpec change. Pairs with the spike
`docs/SPIKE_CODEMODE_MARSHALLING.md` (findings F1–F7) and the 42/42
model eval (`scripts/eval_codemode_correctness.py`). Builds on
ADR 0013 (the bundled code-execution surface). Promote to `accepted`
when the surface ships and a downstream consumer (a2web, a2atlassian,
a2db, a2sdlc) has re-validated against it per ADR 0005.

## Summary

In the context of a2kit's wire-format routing — wired into the CLI
surface only, while the MCP surface ships raw JSON and code mode has
no defined story for its two opposite consumers — facing the fact
that one tool result must serve both the sandbox code that wants
structured values and the LLM that wants the fewest tokens, we
decided to make rendering a function of `(value, consumer)` where
consumer is one of `llm` / `code` / `machine` and the `code_mode`
build flag fixes the consumer at `build_mcp_server` time, and against
runtime call-context sniffing, to achieve compression on every
LLM-facing surface (CLI and MCP) and structured dataclass marshalling
into the sandbox without the two needs ever colliding on the same
result, accepting a BREAKING change to the MCP `content` shape and a
dependency on `pydantic-monty`'s `type_check` / `dataclass_registry`
API.

## The problem

a2kit already infers a format hint from each tool's return type
(`infer_format_hint` → `tsv` / `json` / `page-tsv`). But the hint is
only honored on one surface: the CLI runtime
(`_invoke_tool_in_process` → `format_response`). `build_mcp_server`
hands FastMCP the raw return value and never consults the hint, so an
LLM consuming a tool over MCP pays full JSON token cost. The
`TestClient` format-routes MCP results itself — evidence the wiring
was intended and is simply absent.

Code mode (ADR 0013) sharpens the problem. A tool result now has two
possible consumers with opposite needs:

- **The sandbox code** that calls `call_tool` wants structured,
  manipulable values — `page.items[0].title`, not a TSV string it
  must re-parse.
- **The LLM** that reads the `execute` output wants the fewest
  tokens — TSV for a flat table, not verbose JSON.

One result, two incompatible renderings. The question is the seam:
where the rendering decision lives, and what decides it.

## What we considered (and why this one)

### Option 1: Rendering is `(value, consumer)`, regime fixed at build time (chosen)

Rendering becomes `render(value, consumer)` where `consumer ∈ {llm,
code, machine}`. The `code_mode` flag, already passed to
`build_mcp_server`, selects which consumer a given tool result faces —
fixed once at build time, never sniffed per call:

- `code_mode=True` — real tools are sandbox-only, rendered for `code`
  (dataclasses); only the `execute` output faces the LLM, rendered
  for `llm`.
- `code_mode=False` — real tools face the LLM directly, rendered for
  `llm`.
- the future REST surface is bound to `machine` (plain JSON).

Why it wins: the compression-vs-structure conflict **dissolves**. The
two needs never land on the same result because the regime split
routes them to different consumers before rendering. There is no
runtime branch, no value sniffing for typed results, no call-context
inspection — the consumer is a build-time constant.

### Option 2: Sniff the call context at runtime

Rejected. Inspecting "am I being called from the sandbox or directly?"
on every dispatch is fragile (the sandbox `call_tool` bridge routes
through the same `ctx.fastmcp.call_tool` path as a direct MCP call —
ADR 0013's spike confirmed this) and pushes a decision to the hot path
that the `code_mode` flag already answers statically.

### Option 3: One rendering, let the consumer adapt

Rejected. Forcing the sandbox to re-parse TSV defeats code mode's
ergonomics (spike F1/F2: a model's `["key"]` instinct on a TSV string
is a silent bug). Forcing the LLM to read raw JSON defeats the
token-compression goal that motivated format routing at all.

## The decision

a2kit adopts consumer-aware rendering:

- **`render(value, consumer)` is the one seam.** `llm` compresses
  (TSV / page-tsv where the encoding plan marks data tabular, JSON
  otherwise); `code` produces structured dataclasses; `machine`
  produces plain JSON. The CLI and MCP surfaces both route through it;
  CLI behaviour is unchanged (it was already `llm`).

- **The `code_mode` flag selects the regime at build time.** No
  runtime sniffing — the consumer for every tool result is a
  build-time constant.

- **The MCP surface format-routes.** A new `build_encoding_plan` walks
  a return type once at registration, calling the unchanged
  `infer_format_hint` per `BaseModel` field, so a flat array nested
  inside a larger object (not just a top-level `list` / `Page`) is
  TSV-compressed. page-tsv becomes the depth-1 case.

- **An `llm`-rendered MCP result emits both channels.** TSV / page-tsv
  goes in the MCP `content` block (the token-efficient, LLM-facing
  channel); the equivalent structured JSON goes in
  `structuredContent`. Per MCP spec SEP-1624 the two channels are
  semantically equivalent and clients SHOULD NOT forward both to the
  model — so emitting both is spec-aligned, not a compromise (spike
  F6). The wrapper returns a `fastmcp.ToolResult` (`tool_serializer`
  is deprecated).

- **Code mode's `call_tool` marshals dataclasses, not dicts.**
  pydantic models cannot cross the monty boundary; dict and dataclass
  are a hard XOR on access pattern (spike F1/F2). Dataclass + `.attr`
  is chosen — `page.items[0].title` matches the schema's object mental
  model. Its only downside (a model's JSON `["key"]` instinct) is
  neutralised by the pre-execution type-checker.

- **The `execute` output is rendered by value-driven inference.** It
  has no static return type, so the renderer samples the head of the
  value: a uniform flat list → TSV, else JSON, with a JSON fallback
  if TSV encoding raises.

## Consequences

### Positive

- Compression on every LLM-facing surface — the MCP token-cost gap
  closes.
- The code-mode story is coherent: structured dataclasses into the
  sandbox, compressed TSV out of `execute`.
- One rendering seam, shared by every surface, replaces CLI-local
  format routing.
- `infer_format_hint` is untouched — `build_encoding_plan` wraps it,
  so the existing type-driven-format-routing spec still holds.

### Negative

- **BREAKING — the MCP `content` shape changes.** A tabular result
  that previously emitted raw JSON in `content` now emits TSV /
  page-tsv. MCP clients that parsed `content` as JSON see a changed
  shape. Carried as a `CHANGELOG` BREAKING row; an operator
  `--compact` toggle covers known-non-conformant clients.
- **`pydantic-monty` API dependency.** Dataclass marshalling and
  pre-execution type-checking use `type_check` and
  `dataclass_registry` — `0.0.x` API, confined to
  `a2kit.packages.codemode`.
- **Value-driven `execute` inference can misclassify.** Mitigated by
  conservative head-sampling and the TSV-failure JSON fallback.

### Re-evaluation triggers

- MCP spec SEP-1624 changes the `content` / `structuredContent`
  contract — re-validate the emit-both-channels decision.
- `pydantic-monty` changes its `type_check` / `dataclass_registry`
  API — re-pin and re-validate `a2kit.packages.codemode`.
- A consumer files a real need for per-call consumer selection that
  the build-time regime cannot serve.

Any of these triggers an ADR amending or superseding this one.

## References

- `docs/SPIKE_CODEMODE_MARSHALLING.md` — the de-risking spike,
  findings F1–F7.
- `scripts/eval_codemode_correctness.py` — the 42/42 model eval (F7).
- OpenSpec change `consumer-aware-format-routing` — proposal, design,
  specs, tasks.
- ADR 0013 — the bundled code-execution surface this builds on.
- ADR 0005 — consumer-feedback / re-validation doctrine.
- `openspec/specs/type-driven-format-routing/spec.md` — the
  `infer_format_hint` contract `build_encoding_plan` wraps.
