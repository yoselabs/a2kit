## Why

`a2kit.ToolContext` is currently a lazy re-export of `fastmcp.Context`
— the third-party concrete class IS the implicit contract for "the
per-call request context." The CLI provides `StderrToolContext`, a
duck-typed sibling class that the docstring explicitly describes as
"mimicking fastmcp.Context's public interface."

The word *mimicking* is the smell. The contract is implicit (whatever
fastmcp.Context happens to expose), and a2kit's CLI stub is reverse-
engineered to match. Every fastmcp release adds a method, a2kit either
chases (adds it to the stub) or drifts (some tools break under CLI).

In the clean shape, **the contract is the explicit thing, and concrete
classes are implementations.** This change promotes the implicit
contract into an explicit a2kit-owned Protocol. fastmcp.Context and
the CLI stub continue working unchanged — they satisfy the Protocol
structurally. Future transports add their own concrete classes that
also satisfy.

### What this gets us

1. **The contract is named.** Today: "what is ctx?" → "fastmcp.Context,
   except on CLI where it's a sibling duck-shape." After: "the
   `a2kit.ToolContext` Protocol; concrete impl depends on transport."

2. **No more chasing.** fastmcp evolves on its own schedule; the
   Protocol declares only what *a2kit* cares about. Tools needing
   fastmcp-specific methods continue to annotate
   `ctx: fastmcp.Context` directly (paying the import cost — they're
   in MCP territory anyway).

3. **Honest typing.** Today the CLI passes a `StderrToolContext`
   to a parameter annotated `fastmcp.Context`. Python doesn't
   enforce; the lie is invisible until isinstance fails somewhere
   obscure. After: both impls structurally satisfy `ToolContext`;
   no lie.

4. **Foundation for future capability system.** Feature Protocols
   (`Elicitable`, `Samplable`, etc.) compose cleanly atop the base
   Protocol when needed. **Not built in this change** — see
   "Out of scope".

### Why this is independent of `relax-ldd-ambient-requirement`

The two changes don't depend on each other. `relax-ldd-ambient`
fixes user-visible Friction B (deletes `del ctx` ceremony) and ships
without touching the ToolContext identity. This change is
architectural cleanup that removes the "mimicking" smell, regardless
of what ambient semantics look like. Either can ship first; we plan
to ship `relax-ldd-ambient` first (smaller, user-facing) and this
second (cleanup, no user-facing pain to fix).

## What Changes

### `a2kit.ToolContext` becomes a Protocol

Defined in a new module `src/a2kit/_context_protocol.py` (or similar
private location):

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class ToolContext(Protocol):
    request_id: str
    client_id: str | None
    async def log(self, message: str, *, level: str = "info",
                  logger_name: str | None = None,
                  extra: Any = None) -> None: ...
    async def report_progress(self, progress: float, *,
                              total: float | None = None,
                              message: str | None = None) -> None: ...
    async def debug(self, message: str, *, logger_name: str | None = None,
                    extra: Any = None) -> None: ...
    async def info(self, message: str, *, logger_name: str | None = None,
                   extra: Any = None) -> None: ...
    async def warning(self, message: str, *, logger_name: str | None = None,
                      extra: Any = None) -> None: ...
    async def error(self, message: str, *, logger_name: str | None = None,
                    extra: Any = None) -> None: ...
```

That's the **narrow** Protocol — only cross-transport methods. The
exact surface (whether to include `set_state` / `read_resource` /
`elicit`) is captured in `design.md` after surveying actual consumer
usage patterns.

### `a2kit.__init__.py` updates the lazy re-export

```python
# was: "ToolContext": ("fastmcp", "Context"),
# now:
"ToolContext": ("a2kit._context_protocol", "ToolContext"),
```

Bare `import a2kit` continues to NOT import fastmcp. The Protocol
lives in a2kit's own code.

### `find_context_param` matches the Protocol

`signature.py:84-102` currently calls `_is_tool_context(ann)` to
detect ctx parameters. The matcher walks the annotation type and
checks identity against `fastmcp.Context`. After this change it
checks identity against `a2kit.ToolContext` (the Protocol).

For backward compat: consumers who annotated `ctx: fastmcp.Context`
directly (bypassing `a2kit.ToolContext`) still match — we keep the
fastmcp.Context check as a fallback when fastmcp is loaded. This is
the "consumer in MCP territory pays for fastmcp imports anyway"
scenario.

### `StderrToolContext` — keep the name, update the docstring

The class doesn't move or rename. Its identity changes from "stub
mimicking fastmcp.Context" to "implementation of `a2kit.ToolContext`
for the CLI transport." Docstring rewritten to reflect this.
Renaming to `CliToolContext` is bikeshed-territory and not part of
this change.

### Internal `_is_fastmcp_context`

`packages/ldd/__init__.py:211-228` distinguishes "real fastmcp.Context"
from "CLI stub" at runtime to pick the right wire format
(`ctx.log(extra=...)` vs `_emit`). This check is unchanged — it's
about wire-format dispatch, not contract identity. fastmcp.Context
satisfies both itself AND the Protocol; the runtime check still works.

### Tighten `ldd_state_for_call(ctx=...)` annotation

Today the contextmanager declares `ctx: Any`, which allows
`ldd_state_for_call(ctx=None)` to type-check. Post relax-ldd-
ambient-requirement, that call shape is the only documented misuse
path that still trips Mode B at runtime. The annotation change
moves the loophole-closure from runtime-only to type-checked:

```python
def ldd_state_for_call(*, ctx: ToolContext, ...): ...
```

Internal framework call sites that get ctx from `kwargs.pop(..., None)`
or `kwargs.get(...)` (typed `Any | None`) gain an
`assert ctx_obj is not None` with a `why:` comment documenting the
post-relax invariant. The runtime Mode B raise stays as
defense-in-depth for code paths that escape typing via `cast(Any,
None)` or `# type: ignore`.

The single unit test that intentionally passes `ctx=None` to verify
Mode B raises gets a `# type: ignore[arg-type]` comment — that test
is explicitly testing misuse, so the type-bypass marker reflects
the intent.

Bundled into this change because the annotation change touches
ToolContext semantics. Same area, same review context.

## Out of scope

- **Feature Protocols** (`Elicitable`, `Samplable`, etc.). Parked
  until a real consumer-demand motivator appears.
- **Capability system** (runtime isinstance against feature Protocols
  to gate code branches). Parked alongside.
- **Renaming `StderrToolContext`** to `CliToolContext`. Pure bikeshed,
  defer.
- **Subclassing `fastmcp.Context` from CLI stub.** Hard no — would
  defeat the cold-start budget by importing fastmcp eagerly in CLI
  mode.
- **MCP-specific methods on the base Protocol** (`sample`,
  `list_resources`, `list_prompts`, etc.). These stay accessible
  via `ctx: fastmcp.Context` direct annotation for consumers who
  need them.

## Impact

- **Cold-start budget**: unchanged. The Protocol lives in a2kit;
  no fastmcp import added.
- **Type identity**: `a2kit.ToolContext is fastmcp.Context` was
  True before; becomes False after. Migration risk surveyed:
  - `_is_fastmcp_context` in LDD module — unaffected (still imports
    fastmcp lazily and checks identity).
  - No `isinstance(_, StderrToolContext)` patterns anywhere
    (grepped during proposal scoping).
  - Docstring references to "fastmcp.Context-shaped" are purely
    cosmetic; updated incrementally.
- **Consumer code**: zero migration. `ctx: a2kit.ToolContext`
  annotations work identically; the type they point to changes but
  consumer body code doesn't care.
- **Spec impact**: `mcp-context-passthrough` requirement
  "ToolContext is a re-export of fastmcp.Context" gets MODIFIED to
  "ToolContext is a Protocol satisfied by fastmcp.Context and
  StderrToolContext." Other requirements unaffected.

## Why this is correct (not just convenient)

The "mimicking" relationship between `StderrToolContext` and
`fastmcp.Context` is an artifact of how a2kit grew, not a design
principle. A framework should own its contracts. Promoting the
implicit contract to an explicit Protocol is the standard refactor
for this code smell.

The principle isn't "always use Protocols" — it's "name the
contract when you have one." Today we have an unstated contract
maintained by parallel evolution of two classes. Stating it
removes accidental coupling and clarifies the framework's
relationship with fastmcp (a2kit defines the contract; fastmcp's
Context happens to satisfy it).
