## Why

Today a verb's surface placement is governed by **two overlapping axes**:

- `expose: tuple[str, ...]` (default `("mcp", "api")`) — which network
  surfaces the verb is *mounted* on.
- `visibility: Literal["hidden", "cli", "all"]` — an orthogonal
  all/cli/hidden tier that controls advertisement *and* (on MCP/CLI)
  mounting.

They overlap at the edges (`expose=()` ≈ `visibility="cli"`), each only
covers part of the truth, and the third concept once proposed —
`@cli()` for operator commands — would have bolted a *fourth* spelling
onto the same idea. The redundancy is exactly what the downstream
consumer (a2kay) kept tripping on (friction #2, #5 in ADR 0028): there
is no single place that answers "where does this verb appear, and is it
advertised?"

ADR 0028 (decision 2) resolves this to **one axis, `surfaces`**, with a
three-state matrix per surface — `ABSENT | LISTED | UNLISTED` — that
subsumes `expose`, `visibility`, and the never-built `@cli` idea. This
change introduces that axis and its resolution semantics, and rewires
the two axes that today read placement (`verb-decorators`,
`tool-descriptors`) onto it.

This is **Wave 2** of the surface-architecture delivery and is
**BREAKING** (`expose=`/`visibility=` are removed). It co-ships with
`native-tree-homomorphism`, `router-class-auto-collect`, and
`app-as-peer-root` — together they are one breaking surface (the new
axis + the flat names + the authoring shape).

## What Changes

- **NEW axis `surfaces=`** on the verb decorators, replacing both
  `expose=` and `visibility=`. Spelling (resolved, ADR 0028 open-call
  "UNLISTED spelling"):
  - **tuple shorthand** — `surfaces=("mcp", "cli")` ⇒ LISTED on the
    named surfaces, ABSENT everywhere else (the common all-listed case).
  - **dict escape** — `surfaces={"cli": "unlisted"}` ⇒ the named surface
    is UNLISTED (mounted + callable, hidden from listings/help), all
    others ABSENT (the rare present-but-hidden case).
  - **default** (no `surfaces=`) ⇒ LISTED on every registered surface.
- **Three-state matrix** resolved per `(verb, surface)`:
  - `ABSENT` — not projected/mounted at all (was: surface ∉ `expose`).
  - `LISTED` — projected + advertised in listings/help (was:
    `visibility="all"`).
  - `UNLISTED` — projected + callable but hidden from listings/help
    (was: `visibility="hidden"`).
- **Migration map** from the old pair to the new value (full table in
  `design.md`):
  - `expose=("mcp","api"), visibility="all"` → `surfaces=("mcp","api","cli")` (all LISTED, or simply omit `surfaces=`).
  - `visibility="cli"` → `surfaces=("cli",)` (LISTED on cli, ABSENT on network).
  - `visibility="hidden"` → `surfaces={<surface>: "unlisted"}` (UNLISTED).
- **`@cli()` is retired** as a distinct concept before it is ever built:
  an operator command is a normal verb with `surfaces=("cli",)`; the verb
  still carries read/write semantics.
- **Wave 0 forward-seam honored.** `fix-http-visibility-leak`'s
  `_http_mountable(desc)` predicate (today: "expose ∋ api AND visibility
  == all") becomes "honor the `surfaces` matrix": HTTP mounts iff the
  resolved state for `"api"` is LISTED or UNLISTED, and advertises in the
  OpenAPI schema iff LISTED.

## Capabilities

### Added Capabilities

- `surfaces-projection` — the single projection axis: the three-state
  `ABSENT | LISTED | UNLISTED` matrix, the tuple/dict spelling, default
  resolution, and per-surface rendering semantics (mount vs advertise).

### Modified Capabilities

- `verb-decorators` — the `surfaces=` kwarg replaces `expose=` and
  `visibility=` on `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`. The
  old kwargs are removed and raise a migration-hint `TypeError`.
- `tool-descriptors` — the `ToolDescriptor` carries the resolved
  `surfaces` matrix (a `Mapping[str, Literal["absent","listed","unlisted"]]`)
  in place of the `expose` tuple; surfaces read placement from the matrix.

## Impact

- **BREAKING.** `expose=` and `visibility=` are removed from the public
  verb-decorator surface. Downstream packages (a2atlassian, a2db, a2web,
  a2kay) MUST migrate every decorated verb to `surfaces=`. The
  removed-kwargs raise a `TypeError` whose message names the new kwarg
  and the mechanical mapping, so the break is loud, not silent.
- **Migration is mechanical** (see `design.md` table). The dominant case
  (all-network + cli, advertised) is "delete `expose=`/`visibility=`";
  cli-only and hidden cases each have a one-line rewrite.
- `ToolDescriptor.expose` is removed; consumers reading it migrate to the
  resolved `surfaces` matrix. The Wave-0 `_http_mountable` predicate is
  re-expressed against the matrix.
- Affected source (build phase — out of scope for this artifact change,
  delivered in the co-shipping changes): `src/a2kit/_verbs.py`,
  `src/a2kit/_verb_validators.py`, `src/a2kit/tool.py`,
  `src/a2kit/packages/dispatch/`, `src/a2kit/packages/http/build.py`,
  `src/a2kit/packages/mcp/server.py`, the CLI surface.
- Co-ships with `native-tree-homomorphism`, `router-class-auto-collect`,
  `app-as-peer-root` (Wave 2) — they are one breaking surface and land
  together with a single migration table.

## Non-goals

- **Not** the flat canonical names / native-tree mount mechanics — that
  is `native-tree-homomorphism` (co-shipping). This change owns *which
  surfaces a verb appears on and whether it is advertised*, not *what it
  is named there*.
- **Not** the router/app authoring-shape change (`tools=` removal,
  `@a2kit`-marked auto-collect) — that is `router-class-auto-collect`.
- **Not** a new surface kind or transport — `surfaces` is open to any
  registered surface name, but registering new surfaces is out of scope.
- **Not** the offline `validate_composition` check — Wave 3.
- **Not** re-litigating the semantic-flag vocabulary (`idempotent`,
  `open_world`, `destructive`, `title`) — those are unchanged (ADR 0003).
