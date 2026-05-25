# Antipatterns

Rejected approaches in a2kit, with the *why*. Useful both for future
decision-makers ("did we consider X?") and for consumer authors trying
to repeat a pattern that we have a sharper alternative for.

Each entry is dated to the decision-context. Don't read these as
universal "never do this"; read them as "here's why this particular
problem in this particular codebase doesn't take that shape."

## Typed errors — what we rejected (2026-05, see ADR 0021)

### `Result[T, E]` return type

The Effect-TS / Rust shape: tools return `Result[T, E]` and callers
either match on it or `?`-propagate. Considered and rejected.

Why no:

- Python has no HKTs. `Result[T, E]` is encodable but every callsite
  becomes ceremonial; chained `await` calls have to spell out the
  unwrap explicitly.
- Async composition fights the language. Effect-TS gets away with it
  because TS has a fiber runtime; Python's `await` is a different
  semantic shape and the `Result`-wrapper pattern doesn't compose
  through it cleanly.
- The Python community has tried it (`returns`, `expression`); none
  landed. The friction is real, not stylistic.
- We can have the *guarantee* (no error escapes undeclared) without
  the *mechanism*: declare the failure vocabulary in `Raises(...)`
  metadata, dispatch via `isinstance`, lint the closure.

If you find yourself reaching for `Result[T, E]` in an a2kit tool,
the actual ask is usually "how do I make failure types declared and
checked?" That's `Annotated[T, Raises(E1, E2)]` plus the
`A2K-RAISES-CLOSURE` lint rule.

### `@a2kit.read(enricher=fn)` per-tool decorator kwarg

Earlier iterations attached enrichers via a decorator kwarg. Rejected.

Why no:

- Couples enrichment to the verb decorator's surface, which we are
  deliberately keeping narrow (see core-purity).
- Too easy to forget on a new tool that should share a router-wide
  translator.
- The instance-decorator form (`@router.enricher`) reads at the
  composition root, scales to "five tools share three enrichers"
  without copy-paste, and naturally splits per-router vs
  app-fallback.

### `Router(enrichers=...)` class attribute / `def enrich(self, exc)` method

The pre-`a2effect-foundation` shape. Removed.

Why no:

- Forces an early decision at class-definition time before the
  enricher list is necessarily known.
- Two declaration surfaces (tuple vs method) with precedence rules
  is a teaching burden with no offsetting expressiveness.
- The new instance decorator's narrow/wide form is detected from the
  parameter annotation — that information lives next to the
  enricher itself, where the author writes it.

### Dual-write on success — `content` + `structuredContent` both carrying the same JSON

MCP allows both channels; FastMCP's default fills both with
equivalent info. Rejected for our wire rule.

Why no:

- Pure bloat: two copies of the same JSON, charged to context.
- Confuses smart clients trying to decide which channel is
  authoritative.
- Makes the error path messier: if success dual-writes, the error
  path's "structured carries info content doesn't" rule loses its
  contrast.

The single-mode wire rule: `structuredContent` is emitted ONLY when
its payload carries information `content[0].text` does not. On
success this means content-only when info would be duplicate; on
error this means content carries prose and structured carries the
typed envelope.

### Soft mode / backwards-compat shim for the old enricher signature

We could have shipped a deprecation shim that accepts the old
`(exc) -> str | None` shape and adapts it to the new
`(exc) -> AppError | None`. Rejected.

Why no:

- The contract is strict from v1 day 1. A shim invites consumers to
  postpone migration indefinitely and the wire shape becomes a
  many-year contortion.
- The migration is mechanical and lints itself
  (`A2K-RAISES-UNCOVERED` flags drift between declared and actual
  raises).
- Pre-v1 had no released consumers depending on the old contract;
  no actual upgrade path needs preservation.

### Configuration knob for the wire format

The early design had a `wire_mode` flag controlling whether
structuredContent appears on success. Rejected.

Why no:

- The whole value of "one typed function, every transport" is that
  the wire shape is fixed and consumers can rely on it. A knob
  fragments the consumer side.
- The single-mode rule (info-differs-then-emit) is deterministic
  from the result type; no operator decision needed.

## Other antipatterns

(Earlier rejected approaches predate this file; they live in the
ADR record under their respective superseded entries — see
`docs/adr/INDEX.md`.)
