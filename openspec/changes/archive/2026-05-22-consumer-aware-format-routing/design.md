## Context

a2kit's format routing (JSON / TSV / page-tsv) is wired only into the
CLI runtime (`_invoke_tool_in_process` → `format_response`). The MCP
registration path (`build_mcp_server`) hands FastMCP the raw return
value and never consults `ToolDescriptor.format_hint`. The `TestClient`
format-routes MCP results itself — evidence the wiring was intended and
is simply absent.

Code mode raises the stakes: a tool result has two possible consumers
with opposite needs — sandbox code wants structured values, the LLM
reading `execute` output wants the fewest tokens.

This design is de-risked by `docs/SPIKE_CODEMODE_MARSHALLING.md`
(findings F1–F7) and a 42/42 model eval
(`scripts/eval_codemode_correctness.py`).

## Goals / Non-Goals

**Goals:**

- One rendering seam — `render(value, consumer)` — shared by every
  surface, replacing CLI-local format routing.
- Format compression on every LLM-facing surface (CLI + MCP).
- A coherent code-mode story: structured (dataclass) into the sandbox,
  compressed out of `execute`.
- Pre-execution type-checking of LLM code as the weak-model safety net.

**Non-Goals:**

- The REST surface itself (separate change) — this only binds it to the
  `machine` consumer.
- `pushdown-listview` — good hygiene, but spike F4 shows it is not a
  hard precondition (40k elements marshal in ~33 ms).
- A thin/native re-implementation of the encoders — the seam is stable;
  the impl can be tuned later (VISION: heavy first, thin later).

## Decisions

### D1 — Rendering is `(value, consumer)`; the regime is build-time

The consumer (`llm` / `code` / `machine`) is fixed by `(surface,
code_mode)` at `build_mcp_server` time — no runtime call-context
sniffing. With `code_mode=True`, real tools are sandbox-only (`code`)
and only `execute` faces the LLM (`llm`); with `code_mode=False` real
tools face the LLM. This is what makes the compression-vs-structure
conflict dissolve: the two needs never land on the same result.

### D2 — `call_tool` marshals dataclasses, not dicts

Spike F1/F2: pydantic models cannot cross the monty boundary; dict and
dataclass are a hard XOR (dict → subscript only, dataclass → attribute
only). Dataclass + `.attr` is chosen — matches the schema's
object mental model and gives `page.items[0].title`. Its only downside
(a model's JSON `["key"]` instinct) is neutralised by D3.
*Alternative considered:* return dicts (works today, zero conversion) —
rejected because attribute access reads better and the type-checker
removes the safety argument.

### D3 — a custom `SandboxProvider` type-checks before executing

Spike F5: monty type-checks (`type_check=True`) and `@overload` keyed
on `Literal[tool_name]` resolves real return types. a2kit ships a
`SandboxProvider` (CodeMode's is injectable) that generates stubs from
descriptors, type-checks submitted code, and feeds errors into a
one-retry loop. Catches typos, wrong access patterns, and hallucinated
tool names pre-execution.

### D4 — emit both MCP channels

Research B (MCP spec SEP-1624): `content` is the token-efficient
LLM channel, `structuredContent` is machine-oriented at zero
model-token cost, and clients SHOULD NOT forward both to the model.
So `llm`-rendered MCP results put TSV/page-tsv in `content` and JSON in
`structuredContent`, returned as a `fastmcp.ToolResult` (the blessed
path; `tool_serializer` is deprecated). This is spec-aligned, not a
compromise.

### D5 — static plan for typed results, value-driven for `execute`

`build_encoding_plan` walks the return type once at registration and
calls the unchanged `infer_format_hint` per node — zero runtime
decision cost. `execute` output has no static type, so it is
value-driven: sample the head, never deep-walk; TSV on a uniform flat
list, else JSON; fall back to JSON if TSV encoding raises.

### D6 — the `execute` description is an eval-gated artifact

Spike F7: both Haiku and Sonnet write correct algorithms but fail 100%
on an ambiguous output contract; a precise contract scores 42/42.
a2kit owns the `execute` description; the eval becomes a permanent
fixture (regression gate when the description or stub-gen changes, or a
new model ships).

## Risks / Trade-offs

- **MCP `content` shape changes (BREAKING)** → Mitigation: CHANGELOG
  BREAKING entry; a2kit's own MCP tests updated in this change; the
  change is semantically a fix (compression was always intended).
- **Non-conformant MCP clients** (drop `structuredContent`, or
  double-count) → Mitigation: default to emitting both (D4); an
  operator "compact" toggle for a known-misbehaving client.
- **Value-driven misclassification of `execute` output** → Mitigation:
  conservative head-sampling + TSV-failure fallback to JSON (D5).
- **`pydantic-monty` 0.0.17 is early** → Mitigation: pinned dependency;
  spikes exercised the exact API used (`type_check`,
  `dataclass_registry`, `@overload` resolution).
- **Stub generation for deeply generic return types** → Mitigation:
  the scalar-row case is covered; complex generics are an open
  question below.

## Migration Plan

1. Land the rendering seam and `build_encoding_plan` behind
   `render(value, consumer)`; CLI keeps current behaviour (`llm`).
2. Wire the MCP format-routing wrapper (returns `ToolResult`); update
   a2kit's MCP tests for the new `content` shape.
3. Land the code-mode `SandboxProvider` + dataclass marshalling +
   `execute` description.
4. CHANGELOG BREAKING entry; ADR recording the consumer-profile
   decision.

Rollback: the MCP wrapper is additive and gated — reverting it
restores raw-JSON MCP output without touching the CLI path.

## Open Questions

- The α/β residual for `code_mode=False`: default to emitting both
  channels; confirm the exact `--compact` operator-toggle wording.
- Stub generation for non-trivial generic return types beyond
  `Page[scalar-row]`.
- Whether to also wrap submitted code in a function (defence-in-depth
  so a top-level `return` works too, reconciling the monty
  runtime-allows / type-check-rejects inconsistency).
