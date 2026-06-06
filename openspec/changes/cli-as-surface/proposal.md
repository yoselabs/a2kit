## Why

The CLI is **not a `Surface`**. MCP and HTTP each satisfy the
`surface-protocol` contract (`name`, `reserved_types`,
`substrate_dep_markers`, `bind(runtime, descriptors)`,
`install_di_bridge`) and are assembled by one uniform `bind(...)` shape;
the CLI is special-cased — built by a free `build_full_cli` function
(`packages/cli/builder.py`) that sits *outside* the surface set. There
is no `app.cli` accessor to pair with `app.api` and `app.mcp`, and the
typer ≥ 0.26 vendored-click compatibility concern is handled inline in
the builder rather than contained in a surface's `bind`.

This asymmetry is the root of three of the seven a2kay frictions behind
ADR 0028: friction #1 (CLI dead on typer ≥ 0.26 — the vendored-click
shim has no home of its own), the missing `app.cli` parity, and the
fact that the homomorphism (Wave 2) can only land once *all three*
surfaces are uniform. Wave 0 already shipped a structural `add_command`
capability guard inside the builder as a stopgap; that guard now wants
a permanent home.

This is **the spine** (ADR 0028 / `docs/SURFACE_ARCHITECTURE.md` § 7,
Wave 1). It makes MCP, HTTP, and CLI uniform so Wave 2's native-tree
homomorphism and the `surfaces` projection axis can land on top of one
composition model instead of three bespoke builders.

## What Changes

The CLI becomes a third `Surface`. A new `CliSurface` satisfies the
`surface-protocol` with `name = "cli"` and `kind = SurfaceKind.LOCAL`
(vs `SurfaceKind.NETWORK` for MCP and HTTP). `CliSurface.bind(runtime,
descriptors)` owns the Typer build — the per-router sub-Typers, the
`schema` / `list-tools` / `serve` / `code` / `health` subcommands,
body-model UX, format routing, and the `A2KIT_TOOLS` tool-selection
seam — re-homed from `build_full_cli` with no behavior change.

- **`packages/dispatch/surface.py`**: add a `SurfaceKind` enum
  (`NETWORK` | `LOCAL`) and a `kind: ClassVar[SurfaceKind]` field to the
  `Surface` Protocol. `McpSurface` / `ApiSurface` declare `NETWORK`.
- **`packages/cli/`**: add `CliSurface` (`name = "cli"`,
  `kind = LOCAL`). `CliSurface.bind` absorbs the body of the former
  `build_full_cli`, including the vendored-click compatibility shim —
  folding Wave 0's structural `add_command` capability guard in so it
  lives in **one** place, not smeared across the builder.
- **`app.py`**: add an `App.cli` accessor symmetric with `App.api` /
  `App.mcp` (lazy `importlib` load, cold-start preserved, idempotent).
- **`serve-topology`**: the CLI is assembled via `CliSurface.bind`. As a
  `LOCAL`-kind surface it is not mounted into the network parent ASGI
  app; the default network `surfaces=` tuple stays
  `(McpSurface(), ApiSurface())`.

This is a **non-breaking** re-homing: the assembled CLI behaves exactly
as the pre-Surface builder produced it. No tool names, no flags, no
output shapes change. The `surfaces` projection axis and the flat
canonical-name rename are explicitly **out of scope** here (Wave 2).

## Capabilities

### Added Capabilities

- `cli-surface` — `CliSurface` (`name = "cli"`, `kind = LOCAL`)
  satisfies the `Surface` Protocol; `CliSurface.bind` owns the Typer
  build + the contained vendored-click compatibility shim; `App.cli`
  accessor mirrors `App.api` / `App.mcp`.

### Modified Capabilities

- `surface-protocol` — the `Surface` Protocol gains a
  `kind: ClassVar[SurfaceKind]` field (`NETWORK` | `LOCAL`); `CliSurface`
  is added to the set of conforming surfaces (LOCAL), `McpSurface` /
  `ApiSurface` are NETWORK.
- `serve-topology` — the top-level CLI is assembled via
  `CliSurface.bind(runtime, descriptors)` rather than a free
  `build_full_cli`; the LOCAL CLI surface is not mounted into the
  network parent ASGI app, so the default network `surfaces=` tuple is
  unchanged.

## Impact

- Affected code: `src/a2kit/packages/dispatch/surface.py` (`SurfaceKind`
  + `kind` field), `src/a2kit/packages/cli/builder.py` (body moves into
  `CliSurface.bind`; the Wave 0 `add_command` guard folds in),
  `src/a2kit/app.py` (`App.cli` accessor), and the `a2kit.run` entry
  point (calls `CliSurface.bind` instead of `build_full_cli`).
- **Non-breaking**: the assembled CLI is behaviorally identical; this is
  internal re-homing plus one new accessor and one new protocol field.
- Cold-start preserved: `App.cli` lazy-loads `CliSurface` via
  `importlib`; `import a2kit` still does not import `typer`.
- Unblocks Wave 2 — the native-tree homomorphism and the `surfaces`
  projection axis depend on all three surfaces sharing one `bind(...)`
  composition model, which this change establishes.

## Non-goals

- **Not** the `surfaces` projection axis (Wave 2 /
  `surfaces-projection-axis`) — `expose` + `visibility` stay as-is.
- **Not** the flat `slug_leaf` canonical-name rename or
  `canonical_name_override` (Wave 2 / `native-tree-homomorphism`).
- **Not** the router/app class auto-collect authoring change (Wave 2 /
  `router-class-auto-collect`).
- **Not** changing any CLI behavior, tool name, flag, or output shape —
  this is a re-homing of the existing builder.
- **Not** a nested CLI layout (`CliConfig.layout`) — deferred; the
  flat default is unchanged here.
