# Align Context method signatures across CLI stub and fastmcp.Context

## Why

The `field-logging-via-ldd` change repaired Tier 1 of the
Context-shape divergence (the four `info`/`warning`/`error`/`debug`
methods that crashed under MCP). A two-axis signature-drift scan
documented 13 additional methods drifting between
`StderrToolContext` and `fastmcp.Context`. None crash like Tier 1
did, but each is a latent footgun: code written against the looser
shape on one transport silently produces wrong behaviour or wrong
return types on the other.

The full inventory after `field-logging-via-ldd`:

**Tier 3 — return-shape divergence**

| Method | fastmcp returns | stub returns | Risk |
|---|---|---|---|
| `read_resource` | `ResourceResult` | `str \| bytes` | Tool destructuring `.content` crashes on CLI; tool calling `.decode()` crashes on MCP |
| `get_prompt` | `GetPromptResult` | `Any` | Stub raises `MCPOnlyError`; safe but typing lies |
| `list_resources` | `list[SDKResource]` | `Any` (raises) | Stub raises; safe but typing lies |
| `list_prompts` | `list[SDKPrompt]` | `Any` (raises) | Stub raises; safe but typing lies |
| `list_roots` | `list[Root]` | `Any` (raises) | Stub raises; safe but typing lies |

**Tier 4 — argument-acceptance divergence**

| Method | Issue |
|---|---|
| `elicit` | Stub's `response_type: Any` accepts forms fastmcp's overload union rejects (complex schemas, nested types). Tool written against CLI may crash on MCP. |
| `log` | fastmcp narrows `level` to `LoggingLevel` literal; stub takes generic `str`. Runtime tolerant, types misleading. |
| `sample`, `sample_step` | Stub accepts `*args, **kwargs` (raises). Hides fastmcp's real signature from typecheck. |
| `send_notification` | Stub accepts `notification: Any`; fastmcp takes `mcp.types.ServerNotificationType`. Stub raises; typing lies. |

**Tier 2 — reverse divergence** (stub-only)

| Method | Issue |
|---|---|
| `send_log_message` | Present on `StderrToolContext` but not on `fastmcp.Context` (it's on `ctx.session`, not on `ctx`). Tool calling `ctx.send_log_message(...)` works on CLI, `AttributeError` on MCP. |

After `rebuild-test-client-on-real-context` lands, behavioural drift
in Tier 3 surfaces immediately in the in-process test client (it
exercises the real fastmcp.Context). After this change, the
signature-level drift is also pinned by
`tests/test_context_surface.py`'s `CTX_CALL_SHAPES` registry.

## What Changes

This change is a **sequenced sweep** over the 13 drifting methods.
Each method gets one of four treatments:

1. **Match fastmcp exactly** — for methods whose stub has CLI semantics
   (`elicit`, `read_resource`). Narrow the stub to fastmcp's signature
   verbatim; rewrite the body to honour the wider contract.
2. **Match fastmcp's signature; raise `MCPOnlyError` in body** — for
   MCP-only methods that aren't CLI-semantic (`sample`, `sample_step`,
   `get_prompt`, `list_resources`, `list_prompts`, `list_roots`,
   `send_notification`). Stub's signature mirrors fastmcp's so typecheck
   doesn't lie; body raises immediately. This is the same pattern
   `field-logging-via-ldd` used for the logging methods.
3. **Delete from stub** — for `send_log_message`. The method doesn't
   exist on `fastmcp.Context`; pretending otherwise is the bug. Any
   consumer code calling `ctx.send_log_message(...)` migrates to
   `await ctx.session.send_log_message(...)` (the fastmcp-native form)
   or, more idiomatically, to `a2kit.ldd.log(...)` (the protocol-neutral
   primitive).
4. **Pin in `CTX_CALL_SHAPES`** — for `log`. Already aligned on body;
   signature divergence is only the `level` literal type. Adding test
   coverage of the `level="info"` / `level="warning"` strings via
   `CTX_CALL_SHAPES` is enough.

### Per-method treatment

- **`read_resource`** → Treatment 1. Stub returns
  `fastmcp.resources.ResourceResult` (or equivalent) when reading
  `file://` URIs. Body wraps the existing `text or bytes` content in
  the result type. Test-only contract type `_FakeResourceResult` lives
  in the stub module if fastmcp's type is too heavy to construct
  cheaply.

- **`elicit`** → Treatment 1. Stub's signature mirrors fastmcp's
  overload union for `response_type`. Where the stub today accepts
  any type and dispatches by `isinstance`, the new body validates
  upfront against the documented `type[T] | list[str] | dict[...] |
  None` shape and raises `MCPOnlyError` for unsupported forms with a
  pointer at the documented set.

- **`get_prompt`, `list_resources`, `list_prompts`, `list_roots`,
  `sample`, `sample_step`, `send_notification`** → Treatment 2. Stub
  signature matches fastmcp; body raises `MCPOnlyError`. These already
  raise; the change is purely cosmetic (signature) but pins typecheck.

- **`log`** → Treatment 4. Body unchanged; sig-test coverage adds
  the `level` literal values.

- **`send_log_message`** → Treatment 3. Method deleted from
  `StderrToolContext`. The runtime-side path (`a2kit.ldd.event` /
  `report` already use `ctx.log(extra=...)` on MCP and `_emit` on CLI,
  so this method has no internal callers in `src/`). Search reveals
  no external callers either — it's stub-only documentation.

### Signature-test extension

`tests/test_context_surface.py` `CTX_CALL_SHAPES` gains an entry per
drifting method, exercising the canonical call form. After the sweep,
all 13 entries bind cleanly against both Context impls.

### Documentation

- ANTIPATTERNS.md gains an entry per Treatment-3 method removed
  (today only `send_log_message` qualifies): "Don't call
  `ctx.send_log_message`. Use `a2kit.ldd.log` for portable structured
  logs, or `ctx.session.send_log_message` for MCP-side
  protocol-level logging."

## Capabilities

### Modified Capabilities

- `mcp-context-passthrough`: the stub-surface requirement broadens
  to "every public method's signature SHALL match fastmcp.Context
  exactly." The method-by-method behaviour spec in the existing
  capability gets per-method scenarios for the new return types and
  argument validations.

## Impact

- **Affected code**:
  - `src/a2kit/packages/cli/context.py` — 13 method signatures
    rewritten.
  - `tests/packages/cli/test_context.py` — assertion-shape updates
    for `read_resource` and `elicit` (new return / arg validation).
  - `tests/test_context_surface.py` — `CTX_CALL_SHAPES` extension.
  - Any tool currently calling `ctx.send_log_message(...)` — none
    in this repo per grep; document migration recipe for external
    consumers.

- **APIs**: BREAKING for direct stub consumers using
  `ctx.send_log_message(...)` (removed). Non-breaking for everything
  else — signatures narrow, but the previous looser shape was always
  hiding fastmcp's narrower truth.

- **Dependencies**: none.

- **CI cost**: zero. Same test count, slightly tighter assertions.

- **Risk**: low. Tier 3/4 don't crash today the way Tier 1 did; the
  divergence is silent. After the sweep, drift is impossible — every
  shape is pinned by `CTX_CALL_SHAPES` and runs against both impls.
