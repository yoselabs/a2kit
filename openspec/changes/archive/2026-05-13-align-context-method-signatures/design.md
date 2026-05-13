# Design — align Context method signatures

## Context

`field-logging-via-ldd` fixed Tier 1 (the four field-logging methods
that crashed under MCP) by routing field-bearing logging through
`a2kit.ldd.*` free functions and narrowing the stub's
`info`/`warning`/`error`/`debug` to fastmcp's signature. This change
extends the same architectural rule — "stub signatures must match
fastmcp.Context exactly" — to the 13 remaining methods.

The Tier 1 fix relied on a free-function escape valve (the LDD primitives)
because the kwargs-form was load-bearing for a real use case. None of
the Tier 3/4 methods need an escape valve:

- Tier 3 return-shape methods (`read_resource`, `get_prompt`, list_*)
  either return real fastmcp types (and the stub should too) or
  raise `MCPOnlyError` (and don't need a return type at all).
- Tier 4 arg-acceptance methods (`elicit`, `sample`, `send_notification`)
  either have well-defined fastmcp overload unions to mirror or
  raise on the stub.
- Tier 2 (`send_log_message`) is the stub inventing API. Delete.

So this is a straight signature-alignment sweep. The hard call is
per-method: which methods get real CLI semantics (Treatment 1) vs.
signature-mirror-then-raise (Treatment 2). The proposal classifies
each.

## Goals / Non-Goals

### Goals

- Every public method on `StderrToolContext` SHALL have a signature
  identical to its counterpart on `fastmcp.Context` (modulo `self`).
  `inspect.signature(StderrToolContext.<method>)` ==
  `inspect.signature(fastmcp.Context.<method>)` for every public name.
- `tests/test_context_surface.py` `CTX_CALL_SHAPES` registry gains
  one entry per drifting method, exercising the canonical call form
  against both impls.
- ANTIPATTERNS.md gains an entry for `ctx.send_log_message` →
  `a2kit.ldd.log` migration.

### Non-Goals

- Adding new CLI-side capabilities. Stub methods that currently raise
  `MCPOnlyError` continue to raise; only the signature changes.
- Reworking the LDD primitives. They're already aligned post
  `field-logging-via-ldd`.
- Touching the `mcp-context-passthrough` re-export rule. `a2kit.ToolContext`
  stays as a `fastmcp.Context` re-export.

## Decisions

### D-TREATMENT-1 — methods with real CLI semantics

`read_resource(uri: str | AnyUrl) -> ResourceResult` and
`elicit(message, response_type, *, response_title=None, response_description=None)`.

Stub signature matches fastmcp's exactly. Bodies preserve the
existing CLI behaviour but adapt to the new return / arg types:

- `read_resource` — wrap the file-content `str`/`bytes` result in a
  `ResourceResult` (or, if constructing the upstream type is heavy,
  a duck-typed `_StubResourceResult` namedtuple with `content` /
  `is_text` fields matching the protocol consumers expect). Tests
  for the wrapper land in `test_context.py`.
- `elicit` — split the body by the documented `response_type` union
  fastmcp accepts. `None` / `type[T]` / `list[str]` / `dict[str,
  dict[str, str]]` each get a branch. Currently the stub `isinstance`-
  switches on shape; the new body explicitly validates against the
  documented overload set and raises a more specific `MCPOnlyError`
  for forms that need a real MCP client.

### D-TREATMENT-2 — signature-mirror-then-raise

`sample`, `sample_step`, `get_prompt`, `list_resources`,
`list_prompts`, `list_roots`, `send_notification`.

Stub method signature is copy-paste-identical to fastmcp's. Body is
a single line: `raise MCPOnlyError(<method-name>, hint=...)`.

For `sample` and `sample_step`, fastmcp's signatures are large and
have overload unions. Use `inspect.signature` to copy the upstream
sig programmatically? Too clever. Just copy the source signatures
verbatim into the stub, and add a test
(`test_stub_signature_matches_fastmcp[<method>]`) that asserts the
match. If fastmcp updates its signature, the test fails and the
stub gets updated.

### D-TREATMENT-3 — delete

`send_log_message` is removed from `StderrToolContext`. Confirmed
no caller in `src/` (event/report use `_emit` directly on CLI and
`ctx.log(extra=...)` on MCP). No caller in `tests/` or `examples/`
per grep.

External consumers — if any — migrate one of two ways:

- For protocol-neutral structured logging:
  `await a2kit.ldd.log(ctx, level, msg, **fields)`. This is the
  idiomatic post-`field-logging-via-ldd` path.
- For MCP-protocol-level admin logging (rare):
  `await ctx.session.send_log_message(level, logger, data)`. This
  is fastmcp's native shape; the stub doesn't speak it because the
  stub has no "session" concept.

### D-TREATMENT-4 — pin without code change

`log` method. Already matches at the body level. Signature drifts
only in the `level: LoggingLevel` literal type (fastmcp) vs. `str`
(stub). Adding `("log", ("msg",), {"level": "info"})` and
`("log", ("msg",), {"level": "warning", "extra": {"k": 1}})` to
`CTX_CALL_SHAPES` is enough to pin the contract — both forms
`bind()` cleanly against both signatures.

If we want to tighten the stub's signature to use fastmcp's
`LoggingLevel` literal, that's a follow-up; not done here because
the runtime accepts the wider `str` happily.

### D-SIGTEST-REGISTRY — extend `CTX_CALL_SHAPES`

After this change, every method in the table below has an entry in
`CTX_CALL_SHAPES`:

| Method | New shape entry |
|---|---|
| `read_resource` | `("read_resource", ("file:///x",), {})` (string), `("read_resource", (AnyUrl("file:///x"),), {})` (typed) |
| `elicit` | `("elicit", ("prompt",), {"response_type": str})`, `("elicit", ("prompt",), {"response_type": ["a","b"]})` |
| `get_prompt` | `("get_prompt", ("name",), {"arguments": {"k": "v"}})` |
| `list_resources` | `("list_resources", (), {})` |
| `list_prompts` | `("list_prompts", (), {})` |
| `list_roots` | `("list_roots", (), {})` |
| `sample` | `("sample", ("hello",), {})` |
| `sample_step` | `("sample_step", ("hello",), {})` |
| `send_notification` | omitted — `mcp.types.ServerNotificationType` requires a real notification instance to bind against; covered by name-coverage test instead |
| `log` | `("log", ("msg",), {"level": "info"})`, `("log", ("msg",), {"level": "warning", "extra": {"k": 1}})` |

The test passes when all entries bind against both `fastmcp.Context`
and `StderrToolContext`.

## Alternatives Considered

### Alt-A — leave Tier 3/4 alone

Argument: Tier 1 was the only crash; Tier 3/4 are silent. Don't
prematurely fix.

Rejected. The same architectural fault that produced Tier 1 produced
Tier 3/4. Leaving the divergence means the next Context-shape bug
will land via one of these 13 methods, with the same diagnostic
opacity (debug=False masks; debug=True shows traceback). The
signature-test registry is cheap once we land the canonical shapes;
the cost of *not* landing is unbounded future debt.

### Alt-B — fully type the stub with the runtime overload union

For `elicit`, replicate fastmcp's six-way `@overload` block on the
stub. For `read_resource`, replicate the `str | AnyUrl` union.

Rejected as the implementation path but **partially adopted**.
Replicating overloads verbatim is brittle (fastmcp evolves; we'd
re-sync per release). The proposal's approach: copy the *runtime*
signature, which `inspect.signature` reports, and pin it via the
sig-test. If fastmcp changes the runtime signature, the test fails
and we re-sync. Overload-level fidelity is left to ty's normal
type-narrowing.

### Alt-C — do this work inside `field-logging-via-ldd`

Argument: one big sweep, one PR.

Rejected. `field-logging-via-ldd` was already sized at 40 tasks
across 10 phases; adding 13 more methods would balloon the diff
and obscure the architectural insight. The Tier 1 fix is the proof
point; this change is the sequel applying the proof to the rest.
Separate changes also allow `rebuild-test-client-on-real-context`
to land between them and surface any drift that this change misses.

## Open Questions

1. **Should `read_resource`'s CLI return type be the real fastmcp
   `ResourceResult` or a stub-side duck-typed shape?** Real type is
   honest; stub-side shape avoids importing the heavy mcp types at
   CLI cold-start. Decide during phase 1 — if importing the type
   adds >10ms to CLI cold-start, use the stub-side shape.

2. **Sequencing relative to `rebuild-test-client-on-real-context`**:
   if the test-client rebuild lands first, this change's behavioural
   tests get teeth (the real fastmcp.Context surfaces in tests). If
   this lands first, the rebuilt client benefits from already-aligned
   signatures. Either order works; recommend test-client-rebuild
   first so this change can lean on it.

3. **Should `send_notification` be in `CTX_CALL_SHAPES`?** Its
   argument type (`mcp.types.ServerNotificationType`) requires
   constructing a real notification. Either build a small fixture,
   or accept that this method is covered by the name-coverage test
   only. Default: name-coverage only; document in the test header.
