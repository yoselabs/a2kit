# Tasks — cli-as-surface

BDD-first / TDD red → green. Each behavior gets a failing test that
proves the asymmetry (CLI is not a Surface; no `app.cli`; the shim has no
home) before the re-homing makes it pass. The assembled CLI must stay
behaviorally identical throughout — the regression suite is the green
guard.

## 1. `SurfaceKind` + protocol field (RED → GREEN)

- [x] 1.1 Add a test asserting `SurfaceKind` has exactly the members
      `NETWORK` and `LOCAL`, and that `Surface` carries a
      `kind: ClassVar[SurfaceKind]` field. Confirm it FAILS today
      (no `SurfaceKind`, no `kind` on the Protocol).
- [x] 1.2 Add `SurfaceKind(enum.Enum)` and the `kind: ClassVar[SurfaceKind]`
      field to the `Surface` Protocol in
      `packages/dispatch/surface.py`. Keep the module substrate-free
      (stdlib `enum` only — cold-start invariant).
- [x] 1.3 Add a test asserting `McpSurface.kind == SurfaceKind.NETWORK`
      and `ApiSurface.kind == SurfaceKind.NETWORK`. RED, then declare the
      `kind` ClassVar on both bundled surfaces. GREEN.

## 2. `CliSurface` satisfies the protocol (RED → GREEN)

- [x] 2.1 Add a test: `isinstance(CliSurface(), Surface)` is `True`,
      `CliSurface().name == "cli"`, `CliSurface.kind == SurfaceKind.LOCAL`.
      Confirm RED (no `CliSurface` yet).
- [x] 2.2 Add `CliSurface` (`name = "cli"`, `kind = LOCAL`, empty
      `reserved_types` / `substrate_dep_markers`) with `bind` and
      `install_di_bridge`. `bind` delegates to the existing builder body
      (the private `_register_*` helpers + `register_serve`/`register_code`).
      `install_di_bridge` is a structural no-op (CLI resolves DI
      per-invocation). GREEN.

## 3. `CliSurface.bind` owns the Typer build (RED → GREEN)

- [x] 3.1 Add a test: `CliSurface().bind(runtime)` returns a
      `click.Command` whose subcommands include the router slug,
      `schema`, `list-tools`, and `serve` — mirroring what
      `build_full_cli` produced. Confirm RED (bind not wired yet).
- [x] 3.2 Move the `build_full_cli` body into `CliSurface.bind` (call the
      shared module-level helpers). Keep `build_full_cli` as a thin
      delegating shim OR switch `a2kit.run` to call `bind` directly —
      whichever keeps the entry point non-breaking. GREEN.
- [x] 3.3 Add a parity test: assemble the CLI via `CliSurface().bind`
      and assert the command tree (subcommand names, tool subcommands per
      router) equals what the pre-change builder produced for the same
      App. GREEN.
- [x] 3.4 Add a test: with `A2KIT_TOOLS` set to a subset, the
      `bind`-assembled CLI registers only the selected tools — the
      tool-selection seam survives the move. GREEN.

## 4. Fold in the vendored-click shim (RED → GREEN)

- [x] 4.1 Add a test: an App with `cli_extras` (Click `add_cli(...)`
      commands) assembles via `CliSurface().bind` and every extra is
      attached via the root command's `add_command` capability —
      regardless of which click distribution typer vendors. Confirm it
      exercises the duck-typed attach path, not an `isinstance` check.
- [x] 4.2 Add a test: a root command exposing no callable `add_command`
      with extras to attach makes `bind` raise a clear `TypeError`
      naming the missing capability (no silent drop). RED, then ensure
      the guard lives inside `bind`.
- [x] 4.3 Move the Wave 0 `add_command` guard (`builder.py:594-608`)
      into `CliSurface.bind` so it lives in exactly one place. Verify no
      duplicate of the guard remains elsewhere. GREEN.

## 5. `App.cli` accessor (RED → GREEN)

- [x] 5.1 Add a test: `app.cli` returns a `CliSurface`, a second access
      returns the same instance (idempotent). Confirm RED (no `cli`
      property).
- [x] 5.2 Add the `App.cli` lazy property (`importlib`-load `CliSurface`),
      with a `_cli` backing slot alongside `_api` / `_mcp` in `__init__`,
      mirroring the `api` / `mcp` shape. GREEN.
- [x] 5.3 Add a cold-start test: after `import a2kit`, reaching the
      `App.cli` property body is the only path that pulls `typer`;
      `import a2kit` alone leaves `typer` absent from `sys.modules`.
      GREEN.

## 6. serve-topology (GREEN)

- [x] 6.1 Confirm (or add) a test that the default
      `runtime.surfaces.names()` is still `("mcp", "api")` — the LOCAL
      CLI surface does NOT join the network mount set. GREEN.
- [x] 6.2 Confirm the top-level CLI entry point (`a2kit.run`) is built
      via `CliSurface().bind(runtime)` and that `CliSurface.kind ==
      LOCAL` keeps it out of the parent ASGI app. GREEN.

## 7. Verify (GREEN)

- [x] 7.1 New tests from §1–§6 pass.
- [x] 7.2 Full existing CLI suite stays green — assembled CLI behavior,
      tool names, flags, and output shapes are byte-for-byte unchanged.
- [x] 7.3 Full suite green, output pristine; `import a2kit` cold-start
      unchanged (no `typer` / `fastmcp` pulled).

## 8. Close out

- [x] 8.1 lint / `ty check src/` / a2kit-static / ruff gates green on
      all touched files.
- [x] 8.2 Confirm the vendored-click shim exists in exactly one place
      (`CliSurface.bind`); no stray copy in the builder.
- [x] 8.3 Forward-compat seam: Wave 2 (`native-tree-homomorphism`,
      `surfaces-projection-axis`, `router-class-auto-collect`) can now
      treat MCP / HTTP / CLI uniformly through `bind(...)`. Note the
      `CliConfig.layout` door is left open (identity stays structured on
      the descriptor) but is out of scope here.
