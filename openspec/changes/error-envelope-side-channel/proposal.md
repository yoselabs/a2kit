## Why

The 2026-05-26 structural audit flagged a `HIGH`-severity coupling
debt in the typed-error foundation that landed across Groups 1-21
(ADR 0021):

**`ErrorEnvelopeStage` mutates the in-flight `AppError` instance with
two attributes (`rendered_prose`, `rendered_envelope_dict`) that the
type checker doesn't know exist, and two transport adapters read those
attributes back via untyped `getattr` lookups.**

Concrete evidence (file:line):

- **Writer:** `packages/dispatch/envelope.py:99-100`
  ```python
  exc.rendered_prose = format_error_prose(exc)            # ty: ignore[unresolved-attribute]
  exc.rendered_envelope_dict = exc.to_envelope_dict()      # ty: ignore[unresolved-attribute]
  ```
  Two `# ty: ignore[unresolved-attribute]` comments mark the smell
  inline — the static analyser is being silenced because the
  `AppError` class doesn't declare these fields.

- **Reader 1 (MCP):** `packages/mcp/_wrappers.py:129-130`
  ```python
  prose = getattr(exc, "rendered_prose", None) or str(exc)
  envelope = getattr(exc, "rendered_envelope_dict", None) or exc.to_envelope_dict()
  ```

- **Reader 2 (CLI):** `packages/cli/runtime.py:84`
  ```python
  prose = getattr(orig, "rendered_prose", None) or str(orig)
  ```

The coupling is wide: `envelope.py` (writer), `mcp/_wrappers.py`
(reader), `cli/runtime.py` (reader) all share an unwritten contract
that lives only as `getattr` fallbacks. The fallbacks themselves
(`or str(exc)`, `or exc.to_envelope_dict()`) hide what would otherwise
be a missing-precondition bug — if `ErrorEnvelopeStage` ever fails to
run or runs in the wrong order, the readers silently render less
useful output instead of failing loudly.

This is structurally identical to the `Principal-via-magic-string-wire-kwarg`
pattern that `consolidate-principal-bridge` is cleaning up: state
travels through an implicit side channel (here: untyped exception
attributes; there: untyped dict values).

The fix is to make the side channel **explicit and typed**: a
per-call rendered-state carrier that `ErrorEnvelopeStage` writes to,
that transport-specific render stages read from, and that the type
checker can verify both ends of.

## What Changes

- **New** `packages/dispatch/_render_state.py` (private to the
  dispatch package) carrying:
  - A frozen dataclass `RenderedError(prose: str, envelope: dict[str,
    Any])`.
  - A keyed side-channel for the current call:
    `set_rendered_error(exc, rendered) / get_rendered_error(exc) ->
    RenderedError | None`. The mapping key is `id(exc)`; the slot is
    stored in a `ContextVar[dict[int, RenderedError]]` populated by
    `Container.call_scope` (no per-tool global). Cleared when the
    call_scope exits.
- **Modified** `ErrorEnvelopeStage.wrap()`
  (`packages/dispatch/envelope.py:99-100`) — replace the two attribute
  assignments with `set_rendered_error(exc, RenderedError(prose=...,
  envelope=...))`. Remove the two `# ty: ignore[unresolved-attribute]`
  comments.
- **Modified** `McpErrorRenderStage` (`packages/mcp/_wrappers.py:129-130`)
  — replace `getattr(exc, "rendered_prose", ...)` with
  `get_rendered_error(exc)`, with a clear `assert` (or typed
  unwrapping with a precise error) when missing. The
  `or str(exc) / or exc.to_envelope_dict()` fallbacks become
  defensive-only — and the test suite gains a regression scenario for
  "rendered state always present when ErrorEnvelopeStage ran."
- **Modified** `CliErrorRenderStage` (`packages/cli/runtime.py:84`)
  — same treatment.
- **Modified** `AppError` class — no field added. The whole point is
  that `AppError` stays a pure domain type; rendering metadata lives
  outside the exception.
- **Modified capability** `error-envelope-rendering`: adds the
  invariant "rendered prose/envelope live in an explicit side channel,
  not on the exception instance."
- The audit also surfaced a related smell — `_pending_typed_envelope`
  ContextVar in `mcp/_wrappers.py:35` is another side channel between
  `McpErrorRenderStage` and `TypedErrorEnvelopeMiddleware`. This
  change consolidates that channel into the same `_render_state`
  module (one private bridge, two consumers) instead of leaving the
  middleware-and-stage bridge as a separate ContextVar.

## Capabilities

### Modified Capabilities
- `error-envelope-rendering` — rendered state is carried on an
  explicit per-call side channel keyed by `id(exc)`, not on the
  exception instance.

## Impact

- Affected code: `packages/dispatch/envelope.py` (writer),
  `packages/mcp/_wrappers.py` (reader + middleware bridge),
  `packages/cli/runtime.py` (reader), new
  `packages/dispatch/_render_state.py` (~60 LOC).
- Removes two `# ty: ignore[unresolved-attribute]` comments — measurable
  static-analysis health gain.
- No change to `AppError` public API. No change to MCP wire envelope
  shape. No change to CLI exit codes or prose format.
- Test coverage: the readers' silent-fallback paths (`or str(exc)`,
  `or exc.to_envelope_dict()`) currently mask precondition failures;
  this change adds a regression test asserting that
  `ErrorEnvelopeStage`-rendered state is always present when the
  envelope stage ran in the pipeline.
- Cross-ref: ADR 0021 (typed-error foundation), 2026-05-26 audit
  (this conversation), sibling change
  `generalise-context-bridges` (Pattern C — eventually
  `_render_state`'s ContextVar can join the `RequestScope`
  generalisation, but not in this change).
