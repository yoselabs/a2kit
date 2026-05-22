# Spike: code-mode sandbox marshalling, type-checking, and output routing

Status: complete. De-risks consumer-aware format routing for a2kit
code mode (the planned `llm-facing-format-routing` change).

## Questions

1. What survives the `call_tool` boundary into the monty sandbox, and
   what access pattern (`r.items` vs `r["items"]`) does each give?
2. Is `page.items[0].title` attribute access achievable?
3. What is the marshalling cost for large arrays (the 40k worry)?
4. Can monty's type checker pre-validate LLM-written code?
5. How do MCP clients treat `content` vs `structuredContent` — does
   emitting both defeat the token-compression goal?

## Method

Three throwaway probes against `pydantic-monty` 0.0.17 plus the FastMCP
3.x `experimental.CodeMode` source, and a web review of the MCP spec
direction. Scripts: `scripts/spike_monty_{marshalling,typecheck,overload}.py`.

## Findings

### F1 — pydantic models cannot cross the sandbox boundary

A `BaseModel` instance returned from an external function fails hard:
`TypeError: Cannot convert <Model> to Monty value`. `call_tool` MUST
hand monty a `dict` or a `dataclass`. (Today `_unwrap_tool_result`
returns `structured_content`, a dict — already compatible.)

### F2 — dict vs dataclass is a hard XOR on access pattern

| Return type | `r["title"]` | `r.title` |
| ----------- | ------------ | --------- |
| `dict`      | works        | `AttributeError` |
| `dataclass` | `TypeError` (not subscriptable) | works |

No type bridges both — monty marshals to its own value system and will
not run an external class's `__getitem__` / `__getattr__`. The
convention is global: pick one.

### F3 — `page.items[0].title` works via nested dataclasses

Nested dataclasses (`PageDC(items=[TaskDC, ...])`) marshal cleanly;
`[t.title for t in p.items]` and `p.next_cursor` both work in-sandbox.
Dataclasses also round-trip *out* of the sandbox as real instances
(`isinstance` holds), registered or not.

### F4 — the 40k-element cost worry is defused

Marshalling cost across the boundary, linear at ~0.8 us/element:

| N      | dict in | dataclass in | in + filter + out |
| ------ | ------- | ------------ | ----------------- |
| 100    | 0.4 ms  | 0.4 ms       | 0.4 ms            |
| 1 000  | 1.5 ms  | 1.6 ms       | 1.5 ms            |
| 10 000 | 11.8 ms | 12.6 ms      | 11.4 ms           |
| 40 000 | 33.6 ms | 32.7 ms      | 38.8 ms           |

dict and dataclass cost the same. 40k elements cross in ~33 ms — not a
bottleneck. Pushdown / pagination remain good hygiene (40k rows to an
LLM is still millions of tokens) but are **not** a hard precondition
for code mode at the sandbox boundary.

### F5 — monty type-checks LLM code pre-execution (the weak-model unlock)

`Monty(code, type_check=True, type_check_stubs=...)` statically rejects,
before any execution, with precise messages:

- typo'd field — `error[unresolved-attribute]: Object of type TaskDC has no attribute 'titel'`
- wrong access pattern — `error[not-subscriptable]`
- nonexistent field, type misuse (`int + str`) — rejected
- `@overload` keyed on `Literal[tool_name]` **resolves** — so
  `await call_tool("list_tasks", {})` is typed as its real return type
- an unknown tool name — `error[no-matching-overload]` (hallucinated
  tool names caught statically)

a2kit holds `ToolDescriptor.return_type` for every tool, so it can
generate dataclass stubs + one `@overload` per tool and type-check the
model's code against the real schemas before running it.

### F6 — the `content` / `structuredContent` tradeoff is resolved by spec

MCP spec direction (SEP-1624) clarifies the two channels:

- `content` — model-oriented, optimized for readability and **token
  efficiency** (the channel conversational clients prefer).
- `structuredContent` — machine-oriented; can be delivered to the
  client at **zero model-token cost**; the channel code mode reads.
- Clients **SHOULD NOT** forward both to the model as distinct inputs;
  when both are present they MUST be semantically equivalent.

Emitting both (TSV in `content`, JSON in `structuredContent`) is the
spec-aligned design, not a compromise. The "double-counting backfire"
risk is spec-prohibited; the residual risk is only non-conformant
clients, which an operator toggle covers.

### F7 — model correctness is gated by the output contract, not capability

A 6-task eval against real `claude-haiku-4-5` and `claude-sonnet-4-6`
via `claude -p`, with the F5 type-checker in a one-retry loop
(`scripts/eval_codemode_correctness.py`):

- With an ambiguous "use `return`" instruction: both models scored
  **0/6** correct — yet **every generated algorithm was logically
  correct**. They wrote `async def main(): ... return ...` then either
  never called it or called it with a top-level `return`.
- monty inconsistency exposed: a top-level `return` *runs* but the
  *type-checker rejects* it (`error[invalid-syntax]: return outside`).
- With a precise contract ("last line is a bare expression; end with
  `await your_function()`; never a top-level `return`"): a 7-task x
  3-repeat re-run (incl. a paginate-and-group-by task) scored
  **Haiku 21/21 and Sonnet 21/21** correct end-to-end. First-try
  type-check: Haiku 21/21, Sonnet 20/21 — the single miss fixed by the
  retry loop.

Cheap-model code-mode correctness is gated by the `execute` tool
description, not by model capability. Haiku writes correct pagination
loops, filters, and reshaping when the output contract is unambiguous.

## Design implications

1. **`call_tool` returns dataclasses, not dicts.** Convert
   `structured_content` -> nested dataclasses using the descriptor's
   `return_type`. This gives `page.items[0].title` attribute access.
2. **Adopt dataclass + `.attr` as the convention.** Its only downside
   (a model's JSON `["key"]` instinct) is neutralized by F5 — the type
   checker rejects it pre-execution with a clear message.
3. **a2kit needs a custom `SandboxProvider`.** `CodeMode` accepts an
   injectable `sandbox_provider`. a2kit's provider generates stubs from
   descriptors, builds `Monty(type_check=True, type_check_stubs=...)`,
   and returns `MontyTypingError` into the retry loop.
4. **Pushdown is hygiene, not a blocker.** F4 removes the boundary-cost
   argument for making `pushdown-listview` a hard dependency.
5. **The weak-model eval is demoted from gate to tuning.** F5 is a
   deterministic safety net; the eval now only measures retry rounds
   and description quality, and is an early implementation task.
6. **Format routing emits both channels.** TSV/page-tsv into `content`,
   structured JSON into `structuredContent` (F6).
7. **The `execute` description is load-bearing** (F7). It must state
   the output contract precisely (last line is a bare expression /
   `await fn()` / never a top-level `return`), attribute access, and
   encourage-flat. a2kit overrides CodeMode's `execute_description`.
   Also wrap submitted code in a function so a top-level `return` works
   too — defence-in-depth against the monty runtime/type-check
   inconsistency.

## Not yet de-risked

- Eval coverage is moderate: 7 tasks x 3 repeats, 2 tools, a
  hand-summarised schema. Still untested — multi-tool joins, error
  paths, the legibility of real verbose `get_schema` JSON-Schema
  output, and a wider model panel. These belong in the permanent
  implementation-phase eval fixture, not in further pre-proposal spikes.
- Stub-generation for deeply generic return types (`Page[T]` with
  non-trivial `T`); F5 covered the common scalar-row case.
