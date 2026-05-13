# Design — replace `surfaces` with `visibility` tier

## Why three tiers, not two

Two booleans (`cli_help: bool`, `api: bool`) admit a meaningless
combination (`cli_help=False, api=True` — "hidden from CLI help
but exposed to agents"). Agents discover programmatically; hiding
from `--help` does not hide from them. So the boolean cross-product
includes one impossible state.

A single three-tier enum (`"hidden" | "cli" | "all"`) is exactly the
set of meaningful states. No `Flag` enum needed (which we just
audited as the wrong shape); a `Literal` type captures it for
type-checkers without an import.

## Why a Literal, not an Enum

We just removed `Surface` (a `Flag`) and `Cap` (a `StrEnum`) from
the top-level surface. Re-introducing a `Visibility` enum would
reverse that cleanup. The values are stable string literals
(`"hidden"`, `"cli"`, `"all"`); `Literal[...]` gives the
type-checker the same protection without the import cost or the
namespace export.

If a future need emerges for value-comparison via attribute access
(`Visibility.HIDDEN`), the type alias can be promoted to a
`StrEnum` without breaking string consumers.

## Resolution order at mount time

```
effective_visibility(tool) =
    tool.meta.extras.visibility                    # explicit per-tool kwarg
    if explicitly set
    else type(router).visibility                   # router class attr
    if defined
    else "all"                                     # baseline default
```

The "explicitly set" check uses the kwarg's `None` sentinel: if the
decorator was called without `visibility=`, the meta field is
`None` and falls through to the router. Any string value (including
`"all"`) is treated as an explicit override.

## Why fold `connections_cli` into `install_connections`

`install_connections(app, *types)` already has side effects on the
App (installs dispatch hook, registers wire scope on the container).
Adding `app.add_cli(...)` is the same kind of side effect, on the
same App, for the same plugin. Splitting them into two calls is
historical, not principled.

The "no magic install" rule applies to **core** verbs (`add_router`,
`add_cli`, `add_mcp_middleware`). Plugin entry points are exempt by
design: they bundle multiple core calls under one identifier. ADR
follow-up to document this distinction.

## Why no `visibility="mcp"`

The audit's gut check: an MCP-only tool would be one a human
operator can never invoke from CLI. That shape has zero real-world
analogue. Every tool we ship is callable from CLI; the only
question is whether agents can also see it.

If a need emerges (e.g., a tool requiring MCP-only context like
elicitation, where the CLI path is meaningless), the kwarg has
room to grow — `Literal["hidden", "cli", "all", "mcp"]` is a
non-breaking extension when adding a new string value, since
existing `"all"`/`"cli"`/`"hidden"` callers are unaffected. Add
the value when the demand materializes, not now.

## CLI mechanics

Click already has `@click.command(hidden=True)` which omits the
command from the parent group's `--help` listing but keeps it
fully invokable. The CLI builder maps `visibility == "hidden"`
to that flag. No new Click machinery.

The `--help` output for a hidden command is unchanged when the
user knows the name: `<app> ops force_unlock --help` works the
same as a visible tool. Only the parent group's listing omits it.

## MCP mechanics

The MCP server registration loop already filters tools by
`meta.extras.surfaces`. The same loop now filters by
`meta.extras.visibility`:

```python
if visibility in ("hidden", "cli"):
    continue   # skip MCP registration
```

The `_meta.*` namespace filter (e.g. `_meta.health` hidden from
agent `list_tools`) is **orthogonal** to `visibility`. The health
tool registers on MCP (visibility="all") but a separate
`server.disable(tags={"_meta"})` post-loop call hides it from
agent listing. The `visibility` field is about which transports
the tool registers on; the `_meta` tag is about agent-listing
visibility within a transport.

## Backward compatibility window

The `Surface` flag and `surfaces=` kwarg are removed in one
release. No deprecation aliasing (`surfaces=Surface.CLI` does
NOT secretly map to `visibility="cli"`). Reason: the surface is
small, callers are countable, and a deprecation window doubles
the meta-extras storage for a single release cycle. Mechanical
migration is faster.

The lint rule update lands in the same release: any leftover
`surfaces=` callsite raises a lint error pointing at the
`visibility=` form.
