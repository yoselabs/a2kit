# Tasks — replace `surfaces` with `visibility`

## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint` + `make test`. Record test count.
- [ ] 0.2 Confirm `prune-dead-decorator-surface` has landed
      (removes `tags=` to avoid kwarg-shape conflicts during this work).
- [ ] 0.3 Grep downstream repos (a2web, a2db, a2atlassian, fox) for
      `surfaces=Surface.` and `connections_cli(`. Inventory call sites
      for the migration note.

## 1. Add `visibility` kwarg + meta field

- [ ] 1.1 In `src/a2kit/tool.py`, define module-level
      `Visibility = Literal["hidden", "cli", "all"]`.
- [ ] 1.2 Add `visibility: Visibility | None = None` to `read()`,
      `write()`, `list_()`, `tool()` signatures.
- [ ] 1.3 In `src/a2kit/metadata.py`, add
      `visibility: str | None = None` to `A2KitMetaExtras` (string
      since pydantic stores Literal as str at runtime).
- [ ] 1.4 In `_stamp`, plumb the kwarg into the extras.

## 2. Add `Router.visibility` class attr

- [ ] 2.1 In `src/a2kit/routers.py`, add
      `visibility: ClassVar[Visibility] = "all"` to `Router`.
- [ ] 2.2 In `Router.__init__`, after the `_stamp`-time meta is
      set, resolve the effective visibility per tool:
      `tool meta visibility (if not None) else router.visibility`.
      Stamp the resolved string onto `meta.extras.visibility`.
- [ ] 2.3 Test: a router with `visibility="cli"` and a tool with no
      kwarg → tool's effective visibility is `"cli"`.
- [ ] 2.4 Test: same router with a tool that has
      `visibility="all"` → tool's effective visibility is `"all"`.

## 3. CLI builder integration

- [ ] 3.1 In `src/a2kit/packages/cli/builder.py`, read
      `meta.extras.visibility` (default `"all"`).
- [ ] 3.2 Remove the `Surface.CLI not in surfaces: continue` branch.
- [ ] 3.3 When registering each tool's Click command, pass
      `hidden=(visibility == "hidden")`.
- [ ] 3.4 Test: `<app> --help` lists `"cli"` and `"all"` tools, omits
      `"hidden"` tools.
- [ ] 3.5 Test: `<app> ops force_unlock` runs successfully even though
      it was hidden from `--help`.

## 4. MCP server integration

- [ ] 4.1 In `src/a2kit/packages/mcp/server.py`, replace the
      `Surface.MCP not in tool_surfaces` branch with
      `visibility in ("hidden", "cli")` skip.
- [ ] 4.2 Test via `build_mcp_server`: a tool with `visibility="cli"`
      is not in the registered tool list.
- [ ] 4.3 Test: a tool with `visibility="all"` is registered.
- [ ] 4.4 Confirm `_meta.health` (visibility="all") still registers
      and is still hidden via the `_meta` tag-filter path.

## 5. Privatize `connections_cli`

- [ ] 5.1 In `src/a2kit/packages/connections/__init__.py`, remove
      `connections_cli` from `__all__`.
- [ ] 5.2 Update `install_connections` to internally build the
      Click group and call `app.add_cli(...)` itself. Signature
      stays `install_connections(app: App, *conn_types) -> App`.
- [ ] 5.3 Update `examples/tracker/server.py` to drop the explicit
      `app.add_cli(connections_cli(...))` line.
- [ ] 5.4 Mark `connections_cli` as deprecated in its module docstring
      (still callable, but no longer exported).
- [ ] 5.5 Test: `install_connections(app, TrackerConn)` alone produces
      a working CLI group at `<app> connections login ...`.

## 6. Delete `Surface`

- [ ] 6.1 Remove `Surface` from `src/a2kit/__init__.py` `_LAZY_ATTRS`
      and `__all__`.
- [ ] 6.2 Delete `src/a2kit/surface.py`.
- [ ] 6.3 Remove `surfaces=` kwarg from all four verbs in
      `src/a2kit/tool.py`.
- [ ] 6.4 Remove `surfaces` field from `A2KitMetaExtras`.
- [ ] 6.5 Update `tests/test_meta_extras_typed.py` and any other
      tests that reference `Surface` / `surfaces=`.

## 7. Lint rule update

- [ ] 7.1 In `src/a2kit/packages/lint/rules/surface.py`, replace
      the `surfaces=Surface.CLI` suggestion text with
      `visibility="cli"`. Rename the rule file if appropriate
      (e.g. `visibility.py`).
- [ ] 7.2 Add a NEW lint rule: any decorator call site with
      `surfaces=` argument raises a hard error pointing at the
      migration. (Catches stragglers in downstream consumers
      during the migration window.)
- [ ] 7.3 Test the lint rule fires on a fixture decorated with
      `surfaces=Surface.CLI`.

## 8. Schema + introspection

- [ ] 8.1 In `src/a2kit/schema.py` and any consumer of
      `meta.extras`, swap `surfaces` → `visibility` keys in
      output dicts.
- [ ] 8.2 Update snapshot fixtures.

## 9. Verify

- [ ] 9.1 `make lint` clean.
- [ ] 9.2 `make test` — all green.
- [ ] 9.3 `import a2kit; a2kit.Surface` raises `AttributeError`.
- [ ] 9.4 Examples app (tracker) runs end-to-end on both CLI and MCP.
- [ ] 9.5 Manual: `<tracker> connections login --help` works (was
      `cli` tier); `<tracker> --help` lists connections group.

## 10. Release notes + downstream

- [ ] 10.1 CHANGELOG entry under "Breaking" with migration table.
- [ ] 10.2 Notify downstream maintainers (a2web, a2db, a2atlassian)
      with the surfaces→visibility table and the connections_cli
      privatization.
- [ ] 10.3 Update `docs/adr/` if any ADR references `Surface`.
