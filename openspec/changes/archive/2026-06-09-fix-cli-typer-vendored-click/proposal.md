## Why

a2kay (downstream consumer) reports its CLI is **dead on typer ≥ 0.26**.
Root cause: at 0.26 typer ships its own *vendored* copy of click. After
`command = typer.main.get_command(main)` the returned root command is an
instance of typer's **vendored** `click.Group`, but `build_full_cli`
guards the `add_cli` attachment with `isinstance(command, _click.Group)`
where `_click` is the top-level PyPI `click` (`builder.py:597-601`).
Vendored-Group is not an instance of standalone-Group, so the guard
fails and raises:

> `build_full_cli: root Typer command is not a click.Group; cannot
> attach cli_extras`

Any app that calls `app.add_cli(...)` (e.g. `connections_cli(store)`,
a2kay's admin commands) therefore cannot build its CLI at all under
typer ≥ 0.26. a2kit's own dev env pins `typer >=0.25,<1` at the bottom
of the range, so the repo's tests pass while real consumers (whose
transitive deps — docling et al. — pull typer ≥ 0.26) hit a hard
`TypeError` at startup.

A second latent seam: `__main__.py`'s `LazyGroup(click.Group)` subclasses
**standalone** click while running inside typer's vendored-click command
tree.

This is the headliner friction (#1) from the a2kay feedback round and a
hard blocker, not a polish item. It is a **non-breaking correctness
fix** and ships ahead of the unified surface model (ADR 0028, Wave 0).

## What Changes

Make CLI assembly robust to typer's vendored click, without coupling to
typer's internal module path.

- **`build_full_cli` (`packages/cli/builder.py`)**: stop comparing the
  built command against the standalone `click.Group` type. Attach
  `cli_extras` via a capability check (the command exposes
  `add_command`) rather than an `isinstance` against a possibly-different
  click. Keep the existing "is it actually a group" safety, but express
  it structurally so it holds whether typer vendored click or not.
- **`__main__.py` `LazyGroup`**: ensure the lazy root group composes
  cleanly under typer ≥ 0.26 (subclass the click class typer actually
  uses, or restructure so the lazy-load seam does not depend on
  standalone-vs-vendored identity).
- **Test matrix**: add coverage that exercises CLI assembly with
  `add_cli`-supplied commands present, asserting the `add_cli` subcommand
  is reachable — the scenario that regresses under vendored click.

This is a stopgap that lands the fix today; Wave 1 (`cli-as-surface`,
ADR 0028) later folds the typer-compat handling into `CliSurface.bind`
so it is quarantined in one place. Nothing here pre-commits to that
shape.

## Capabilities

### Modified Capabilities

- `core-composition` — the `add_cli` contract ("the `<app> connections
  {…}` subcommand is available") gains an explicit guarantee that
  attachment holds across typer versions, including when typer vendors
  its own click.

## Impact

- Affected code: `src/a2kit/packages/cli/builder.py` (the `cli_extras`
  attachment guard), `src/a2kit/__main__.py` (`LazyGroup`).
- Unblocks every consumer on typer ≥ 0.26 that uses `app.add_cli(...)`
  (a2kay, and any app wiring `connections_cli`).
- No public API change; no wire change; no rename. Pure correctness.
- a2kit's dev `typer` pin should additionally be exercised against
  ≥ 0.26 in CI so this class of break is caught in-repo, not downstream
  (tracked in tasks; may land as a tox/uv matrix entry).

## Non-goals

- **Not** the `cli-as-surface` refactor (ADR 0028 Wave 1). This change
  does not move CLI assembly behind the `Surface` protocol.
- **Not** changing CLI naming, layout, or the `add_cli` signature.
- **Not** bumping the `typer` floor — the fix makes the code work across
  the whole supported range, it does not narrow it.
