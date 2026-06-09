# Tasks — surfaces-projection-axis

BDD-first / TDD red → green. The new axis gets failing tests proving the
three-state matrix and the tuple/dict spelling resolve correctly, and
proving the old kwargs are gone, before the implementation lands. This is
Wave 2 and BREAKING — co-ships with `native-tree-homomorphism`,
`router-class-auto-collect`, `app-as-peer-root`.

## 1. Resolution semantics (RED)

- [x] 1.1 Test: a verb with `surfaces=("mcp","cli")` resolves to LISTED
      on `mcp` and `cli`, ABSENT on `api`. Confirm RED (no `surfaces=`
      kwarg exists yet).
- [x] 1.2 Test: a verb with `surfaces={"cli": "unlisted"}` resolves to
      UNLISTED on `cli`, ABSENT on `mcp` and `api`. Confirm RED.
- [x] 1.3 Test: a verb with **no** `surfaces=` resolves to LISTED on
      every registered surface. Confirm RED.
- [x] 1.4 Test: a dict with an explicit `"listed"`/`"absent"` value
      resolves to that exact state; unlisted keys default to ABSENT.

## 2. Old axes removed (RED)

- [x] 2.1 Test: `@a2kit.read(expose=("mcp",))` raises `TypeError` whose
      message names `surfaces=` and the mapping. Confirm RED (today it is
      accepted).
- [x] 2.2 Test: `@a2kit.write(visibility="cli")` raises `TypeError` whose
      message gives the mechanical rewrite `surfaces=("cli",)`. Confirm
      RED.
- [x] 2.3 Test: `@a2kit.read(visibility="hidden")` raises `TypeError`
      pointing at `surfaces={<surface>: "unlisted"}`. Confirm RED.

## 3. Descriptor carries the resolved matrix (RED)

- [x] 3.1 Test: `app.tools()[i].surfaces` is a `Mapping` with one entry
      per registered surface, each value ∈ `{"absent","listed","unlisted"}`,
      fully resolved (no `None`). Confirm RED.
- [x] 3.2 Test: `descriptor.surfaces` is immutable (mutating raises
      `TypeError`). Confirm RED.
- [x] 3.3 Test: `ToolDescriptor` no longer exposes `expose`. Confirm RED.

## 4. Surfaces honor the matrix (RED)

- [x] 4.1 Test: a `surfaces=("cli",)` verb is NOT mounted on HTTP (no
      `POST /api/<name>`) and NOT registered on MCP — only on the CLI.
- [x] 4.2 Test: a `surfaces={"api": "unlisted"}` verb IS callable as
      `POST /api/<name>` but is `include_in_schema=False` (absent from
      OpenAPI). Confirm RED.
- [x] 4.3 Test: parity — for a mixed-state app, the set mounted on each
      surface equals `{verb : state(verb, surface) ∈ {listed, unlisted}}`
      and the advertised set equals `{verb : state == listed}`.

## 5. Implement the axis (GREEN)

- [x] 5.1 Replace `expose=`/`visibility=` with `surfaces=` on the verb
      decorators (`src/a2kit/_verbs.py`); add a `resolve_surfaces(...)`
      helper that maps tuple/dict/omitted → the full matrix over the live
      surface registry (reuses the Wave-0 registry seam).
- [x] 5.2 Remove the old kwargs and add the migration-hint `TypeError`
      branches (`src/a2kit/_verb_validators.py`).
- [x] 5.3 Materialize the resolved matrix onto `ToolDescriptor`
      (`src/a2kit/tool.py`); drop the `expose` field.
- [x] 5.4 Re-express `_http_mountable` against the matrix and add the
      `advertise`/`include_in_schema` facet
      (`src/a2kit/packages/http/build.py`); mirror on MCP
      (`packages/mcp/server.py`) and the CLI surface.

## 6. Migration shim + deprecation (GREEN)

- [x] 6.1 Add a one-minor-version decoration-time shim that recognizes a
      legacy `(expose, visibility)` pair, maps it to the new matrix, and
      emits a `DeprecationWarning` naming the `surfaces=` rewrite. Gated so
      the canonical path is `surfaces=` only.
- [x] 6.2 Test: the shim maps each row of the `design.md` migration table
      to the correct matrix and warns once. (When the shim is dropped at
      the next minor, these convert to the §2 `TypeError` tests.)
- [x] 6.3 Deprecation note: record in the change + CHANGELOG that
      `expose=`/`visibility=`/`ToolDescriptor.expose` are removed
      (BREAKING), the shim is transitional, and `@cli()` is retired before
      build. Cross-link the co-shipping Wave-2 changes.

## 7. Verify (GREEN)

- [x] 7.1 §1–§4 tests pass.
- [x] 7.2 Full suite green, output pristine.
- [x] 7.3 lint / `ty check src/` / a2kit-static / ruff gates green on all
      touched files.

## 8. Close out

- [x] 8.1 Confirm co-ship: this change lands together with
      `native-tree-homomorphism`, `router-class-auto-collect`,
      `app-as-peer-root` under one migration table; the matrix's `cli`
      state assumes Wave 1 (`cli-as-surface`) already shipped.
- [x] 8.2 `openspec validate surfaces-projection-axis --strict` passes.
