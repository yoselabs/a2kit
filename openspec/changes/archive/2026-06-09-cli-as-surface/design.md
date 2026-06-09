# Design — cli-as-surface (Wave 1, the spine)

This is the spine change of ADR 0028 / `docs/SURFACE_ARCHITECTURE.md`.
It makes the CLI a `Surface` so MCP, HTTP, and CLI are uniform and
Wave 2's homomorphism can land on one composition model.

## The Surface protocol grows a `kind`

Today the `Surface` Protocol (`packages/dispatch/surface.py`) is:

```
Surface
├─ name: ClassVar[str]
├─ reserved_types: ClassVar[frozenset[type]]
├─ substrate_dep_markers: ClassVar[frozenset[type]]
├─ bind(runtime, descriptors) -> Any
└─ install_di_bridge(runtime, substrate_app) -> None
```

We add one field and one enum:

```python
class SurfaceKind(enum.Enum):
    NETWORK = "network"   # reachable over the wire (MCP, HTTP)
    LOCAL = "local"       # process-local transport (the CLI)

class Surface(Protocol):
    name: ClassVar[str]
    kind: ClassVar[SurfaceKind]        # NEW
    reserved_types: ClassVar[frozenset[type]]
    substrate_dep_markers: ClassVar[frozenset[type]]
    def bind(self, runtime, descriptors=None) -> Any: ...
    def install_di_bridge(self, runtime, substrate_app) -> None: ...
```

`McpSurface` and `ApiSurface` declare `kind = SurfaceKind.NETWORK`;
`CliSurface` declares `kind = SurfaceKind.LOCAL`. The `kind` is the seam
that lets composition code treat "mount into the parent ASGI app" as a
NETWORK-only concern without special-casing the CLI by name. (Wave 3's
`ctx-surface-identity` will also read `kind` when stamping the call
scope.)

This module sits at L4 and MUST NOT import any substrate library
(`typer`, `fastapi`, `fastmcp`). `SurfaceKind` is a plain stdlib enum,
so the cold-start invariant holds.

## How `CliSurface.bind` wraps Typer

The free `build_full_cli(app)` in `packages/cli/builder.py` already does
all the Typer composition. `CliSurface.bind(runtime, descriptors)`
becomes the owner of that body:

```python
class CliSurface:
    name: ClassVar[str] = "cli"
    kind: ClassVar[SurfaceKind] = SurfaceKind.LOCAL
    reserved_types: ClassVar[frozenset[type]] = frozenset()
    substrate_dep_markers: ClassVar[frozenset[type]] = frozenset()

    def bind(self, runtime, descriptors=None):
        # everything build_full_cli does today:
        #   - build(runtime) idempotent finalize
        #   - per-router sub-Typers (_register_router)
        #   - schema / list-tools / serve / code / health subcommands
        #   - A2KIT_TOOLS tool-selection seam
        #   - cli_extras attachment via the vendored-click guard (below)
        return command   # the click.Command (Typer-backed)

    def install_di_bridge(self, runtime, substrate_app):
        # CLI resolves DI per-invocation through the existing
        # invoke_tool_sync path; no separate bridge install is required,
        # so this is a structural no-op that keeps the protocol uniform.
        ...
```

Mechanically the simplest landing keeps the existing private helpers
(`_register_router`, `_register_schema`, `_register_list_tools`,
`_build_tool_callback`, `register_serve`, `register_code`,
`_register_health`) as module functions and has `CliSurface.bind` call
them — the same code, now reachable through the uniform protocol. The
free `build_full_cli` may remain as a thin shim that delegates to
`CliSurface().bind(...)` during the transition, or be deleted with
`a2kit.run` switched to call `bind` directly; either is non-breaking.

`bind` signature note: the Protocol passes `descriptors` (used by the
network surfaces to drive route/tool registration). The CLI already
reads its descriptors off `runtime.tools()` inside the builder, so
`descriptors` is accepted for protocol uniformity and may be ignored or
used as an override; behavior is unchanged.

## The `app.cli` accessor

`App` exposes `api` and `mcp` as lazy properties (`app.py:405-435`) that
`importlib`-load the surface class so touching them does not eagerly
import the substrate. `App.cli` mirrors that shape exactly:

```python
@property
def cli(self) -> Any:
    """The CLI surface, peer of `app.api` / `app.mcp`.

    Lazy: first touch loads `CliSurface` via `importlib` so the
    constructor stays a plain call that does NOT pull `typer`.
    Idempotent thereafter.
    """
    if self._cli is None:
        import importlib
        CliSurface = importlib.import_module(
            "a2kit.packages.cli.surface"
        ).CliSurface
        self._cli = CliSurface()
    return self._cli
```

Same cold-start guarantee, same idempotency, same `_cli` backing slot
added next to `_api` / `_mcp` in `__init__`. (Module path for
`CliSurface` is an implementation choice — `packages/cli/surface.py`
keeps the builder module focused; either co-located works.)

## How Wave 0's stopgap folds in

Wave 0 landed a structural guard in `build_full_cli` (`builder.py:594-608`):
at typer ≥ 0.26 the root command is an instance of typer's *vendored*
click `Group`, not the standalone `click.Group`, so an `isinstance`
check would wrongly reject a valid group when attaching `cli_extras`.
The guard instead checks the capability actually used — a callable
`add_command` — via `getattr`, and fails loud if it is absent.

This change makes `CliSurface.bind` the single home of that guard:

- The compatibility shim moves *inside* `bind`, satisfying ADR 0028
  decision 1 ("the typer ≥ 0.26 vendored-click compatibility shim lives
  inside `CliSurface.bind` — contained, not smeared across the
  builder").
- It stays a duck-typed `add_command` capability check (never an
  `isinstance` against standalone click), so attachment holds whichever
  click distribution typer vendors.
- The fail-loud `TypeError` for a root command with no callable
  `add_command` is preserved verbatim — no silent extras drop.

After this change there is exactly one place the vendored-click concern
is expressed, which is the point of Wave 1.

## Why LOCAL is not mounted into the parent ASGI app

`serve-topology` builds a parent ASGI app and mounts each NETWORK
surface under a path (`/mcp`, `/api`). The CLI has no HTTP path — it is
materialized on demand by `a2kit.run`. The `kind = LOCAL` discriminator
lets the mount loop stay "mount every NETWORK surface" without naming
the CLI as an exception. The default `surfaces=` tuple
(`(McpSurface(), ApiSurface())`) is therefore unchanged; the CLI
participates in the uniform `bind(...)` protocol without joining the
network mount set.

## Dependency note — Wave 2 depends on this

`docs/SURFACE_ARCHITECTURE.md` § 7: Wave 1 (`cli-as-surface`) precedes
Wave 2 because the homomorphism (`native-tree-homomorphism`), the
projection axis (`surfaces-projection-axis`), and the authoring shape
(`router-class-auto-collect`) all assume **all three surfaces share one
`bind(...)` composition model**. Until the CLI is a Surface with a
`bind`, Wave 2 would have to special-case the CLI a second time. This
change removes that special case, so Wave 2 can treat MCP, HTTP, and
CLI uniformly — including the eventual `CliConfig.layout = "flat" |
"nested"` flag (out of scope here; the door is left open by keeping
identity structured on the descriptor, per ADR 0028 § 5).

## Non-goals (boundary with Wave 2)

- No `surfaces` projection matrix — `expose` + `visibility` are untouched.
- No flat `slug_leaf` rename, no `canonical_name_override`.
- No class auto-collect authoring change.
- No `CliConfig.layout` nested CLI — flat default unchanged.
- No CLI behavior, tool name, flag, or output change of any kind.
