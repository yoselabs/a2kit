## Why

a2web's round-4 feedback (`A2KIT_FEEDBACK_v0.26.md`) surfaced four gaps and two soft notes. The architectural ones (Gaps 2, 3, 4) ship as their own change (`di-sync-and-unleak`) because they restructure the DI substrate. This change addresses the **ergonomic items that are independent of that restructuring**:

- **Gap 1 — typed-emit half-shipped.** `app.ldd.events.register(T)` works but the free function `a2kit.ldd.event(ctx, ...)` still wants a name + kwargs. a2web wrote a 25 LOC `_event_payload` flattener to bridge typed dataclasses to kwargs. The registry knows the type; the free function should honor it.
- **Soft B — `ToolContext.null()` for tests.** Internal phase functions that bypass `a2kit.testing.client` receive `ctx=None`, forcing `ctx: ToolContext | None` annotations and `if ctx is None: return` guards at every emit site. A null context shim lets production code take non-`Optional` `ctx`.
- **Soft A — Param description verbosity.** Tool signatures with long `Param(description=...)` strings read 80% schema, 20% Python. Document the existing trade-off (intentional for MCP self-description) and add a shorter positional form `Param("description text")` for the common case.

These are additive. No breaking changes. Ships independently of `di-sync-and-unleak`.

## What Changes

- **Typed free-function emit.** `a2kit.ldd.event(ctx, payload)` SHALL accept an instance of any class as its second positional argument. When called with an instance:
  - Name defaults to `type(payload).__name__`.
  - Payload is serialized via `dataclasses.asdict` (for dataclasses), `payload.model_dump(mode="json")` (for pydantic `BaseModel`), or `vars(payload)` (fallback).
  - Enum values are coerced via `.value`.
  - The existing `a2kit.ldd.event(ctx, "name", **kwargs)` form stays available for ad-hoc calls.
- **`a2kit.testing.null_context()`.** A factory returning a no-op `ToolContext`-shaped stub. All `fastmcp.Context` public methods are present and do nothing (logging methods no-op, `report_progress` no-op, `request_id` returns a fixed string, etc.). Internal phase tests construct one and pass it to production functions that take `ctx: ToolContext` (non-Optional).
- **`Param` positional shorthand.** `a2kit.Param("description text")` becomes equivalent to `a2kit.Param(description="description text")` when only the description is set. The Annotated form `Annotated[str, Param("Absolute URL.")]` reads ~30% shorter.
- **Param documentation note.** README's "Tool description contract" section gains a paragraph explaining that long `Param(description=...)` strings are intentional (MCP agents read them via `list_tools`) and pointing at the shorthand for short descriptions.

## Capabilities

### Modified Capabilities

- `mcp-context-passthrough`: Extends `a2kit.ldd.event` to accept an instance positional. Adds the contract for null context behavior.
- `tool-description-contract`: Adds the `Param("description")` positional shorthand.
- `in-process-test-client`: Adds `a2kit.testing.null_context()` as a peer to `a2kit.testing.client`.

### New Capabilities

None. All changes extend existing capabilities.

## Impact

- **API.** Three additive surfaces. No breaking changes.
- **Code.** ~50 LOC net add. Typed emit: ~25 LOC in `a2kit/ldd.py`. Null context: ~20 LOC in `a2kit/packages/testing/`. Param shorthand: ~3 LOC in `a2kit/params.py`. Tests: ~150 LOC across new test files.
- **Consumer savings (a2web).** Deletes `_event_payload` (~25 LOC) and `_emit` (~6 LOC). Removes `ctx: ToolContext | None` annotations and `if ctx is None: return` guards (~6 sites). Each tool with long `Param` strings shortens by ~10-15% if it uses the positional form.
- **Backwards compat.** Strict additive. Existing kwargs-based `event(ctx, "name", **kw)` calls keep working unchanged.
