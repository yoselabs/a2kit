---
id: "0021"
status: accepted
date: 2026-05-25
last_reviewed: 2026-05-25
supersedes: []
superseded_by: null
tags: [errors, surface, di, lint, foundation]
deciders: [Denis Tomilin]
---

# ADR 0021: Typed errors via metadata + isinstance — Effect's guarantee without its mechanism

## Status

Accepted, 2026-05-25.

## Summary

In the context of a2kit's value proposition (write one typed function,
get every transport), facing the fact that errors broke that promise —
every tool shipped untyped exceptions as wire strings, agents could not
reason about retryability, the framework could not auto-retry, and the
CLI had no exit-code discipline — we chose to introduce a standalone
`a2effect` package providing `AppError` + `Annotated[T, Raises(...)]` +
default enricher chain + envelope wire schema, deliberately rejecting
the Effect-TS approach (HKTs, `Result` monad, fiber runtime) in favour
of Python-native primitives (sealed exception hierarchy, `Annotated`
metadata, `isinstance` dispatch, AST lint), to achieve Effect's
guarantee (declared failure vocabulary; nothing else escapes the
wire) without paying for its mechanism (which Python cannot carry).

## Why

Three forces converged in May 2026:

1. **Open runway in the MCP ecosystem.** Anthropic's 2026 roadmap
   didn't mention typed errors. FastMCP's PR #2885 explicitly stripped
   typed-error design, keeping plain `ToolError(str)`. No competing
   convention had converged across the ecosystem. First mover wins
   the contract.
2. **a2kit's wedge depended on it.** "One typed function, every
   transport" was already true for the success path (pydantic models →
   MCP outputSchema, FastAPI response_model, CLI JSON). The error path
   was a parallel system: enrichers returned strings, the wire dropped
   them into a content field with no shape, and consumers (Cursor,
   langchain, our own smart client) had to regex-parse them.
3. **Effect-style monads don't fit Python.** Python lacks HKTs;
   `Result[T, E]` requires every call-site to be ceremonial; async
   composition fights the language. The Effect community has tried
   it (`returns`, `expression`); none of it landed. Replicating
   Effect's *mechanism* loses; replicating its *guarantee* via
   different mechanism wins.

## What we chose

The contract is built from five Python-native primitives:

- **`AppError` sealed hierarchy** with a `kind` ClassVar taxonomy
  (`input | auth | policy | infra | bug`) and per-class `http_status` /
  `cli_exit_code` overrides. Extension kinds register via
  `register_error_kind(name, base=...)`. Per-instance `retryable` /
  `hint` / `details` overrides for declared exceptions, otherwise
  the class defaults.
- **`Annotated[ReturnT, Raises(E1, E2, ...)]`** as the declared raise
  set. Read via `get_type_hints(fn, include_extras=True)` at
  descriptor materialisation; multiple markers in one `Annotated`
  flatten additively; non-`AppError` members rejected at registration
  with a named `TypeError`. Zero per-call runtime cost.
- **Enricher chain** with two forms detected from the first
  parameter's annotation: wide
  (`def f(exc: Exception) -> AppError | None`) is called for every
  raise; narrow (`def f(exc: SpecificType) -> ...`) is called only on
  `isinstance` match. Chain order: per-tool inline (`raises_as` /
  `translate_to`) → router enrichers (registration order) → app
  enrichers (registration order) → defect quarantine. First non-None
  `AppError` wins.
- **`UnexpectedDefect` quarantine.** Anything escaping all enrichers
  is wrapped: `kind="bug"`, `retryable=False`, original preserved on
  `__cause__`. The wire never sees the raw type; the typed envelope
  always reaches the consumer.
- **`ErrorEnvelope` wire schema.** Pydantic-shaped, versioned
  (`envelope_version: Literal["1"]`). Single rendering pass via
  `ErrorEnvelopeStage` attaches `rendered_prose` and
  `rendered_envelope_dict` to the in-flight `AppError` so MCP / HTTP /
  CLI surfaces read them without re-computing per transport.

The wire rule: `structuredContent` is emitted ONLY when its payload
carries information `content[0].text` does not. On the error path,
prose goes in content and the envelope goes in structured — two
channels with non-overlapping info. There is no configuration knob;
the rule is fixed.

## What we rejected

See `docs/ANTIPATTERNS.md` for the rejected alternatives and the
reasoning. The short list:

- `Result[T, E]` return type (Pythonic ergonomics tax outweighs the
  benefit; killed by Python's lack of HKTs).
- `@a2kit.read(enricher=fn)` per-tool decorator kwarg (too easy to
  forget; couples to the verb decorator's surface).
- Dual-write on success (`content` + `structuredContent` both
  carrying the same JSON — pure bloat with no info gain).
- Soft mode / backwards-compat shim (the contract is strict from
  v1 day 1; consumers migrate or stay on pre-v1).

## Consequences

- **a2effect is a standalone package.** Pydantic-only, no a2kit dep.
  Adoptable by any Python framework wanting typed errors (FastAPI,
  Litestar, raw ASGI). Cross-framework convergence on the
  `ErrorEnvelope` shape is the unspoken longer-term bet.
- **Lint rules ship in a2effect** registered via the `a2lint.rules`
  entry point group. Today they run via the bundled
  `python -m a2effect.lint` shim; later, when the deferred
  `a2lint-extraction` change lands, the same rules will load into
  the standalone rule-runner without code change.
- **Three surfaces converge on one envelope.** MCP, HTTP, CLI all
  read the same `ErrorEnvelope`; the rendering differs (prose +
  structured, JSON body + status, prose + exit code) but the
  underlying contract is one.
- **Consumer migration is mechanical and lints itself.** The recipe
  in `docs/MIGRATION_TYPED_ERRORS.md` covers the four steps;
  `A2K-RAISES-UNCOVERED` flags any tool body whose declared raise
  set drifts from its actual raises.

## What this does NOT do

- It does not provide `Result`/`Option` monads. They were considered
  and explicitly rejected.
- It does not auto-retry on `retryable=True` envelopes. That's the
  scope of a follow-up (`@retry_on` decorator reading envelope
  metadata).
- It does not emit OpenAPI from the typed-error contract. That rides
  on top once the contract is load-bearing across consumers.

## References

- OpenSpec change: `openspec/changes/a2effect-foundation/`
- Migration recipe: `docs/MIGRATION_TYPED_ERRORS.md`
- Antipatterns: `docs/ANTIPATTERNS.md`
- a2effect package: `packages/a2effect/`
