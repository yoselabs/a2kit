# Design — remove-legacy-expose-visibility

## Context

`@a2kit.read/write/list_` accept two surface-placement input paths today:

- **New:** `surfaces=` (tuple of names → LISTED, or dict of states) → stored as
  the resolved matrix in `extras.surfaces`.
- **Legacy:** `expose=` (tuple) + `visibility=` (`"all"`/`"cli"`/`"hidden"`) →
  stored raw, resolved lazily via `_surfaces._resolve_legacy` in `matrix_for`.

Both normalize to `extras.expose` (the mounted-surface tuple every adapter
reads). The legacy path works **silently** — the §1 anti-pattern. This change
deletes the legacy input path; the normalized `extras.expose` field stays.

## Decisions

### D1. Drop the Router/App `visibility` ClassVar default entirely (no replacement)

`Router` carries `visibility: ClassVar[str] = "all"` (precedence: per-tool
`visibility=` → Router class attr → `"all"`); `app.py` defaults app-level verbs
to `"all"`. The ClassVar existed only to make a *whole* router CLI-only in one
line (3 tests use `visibility = "cli"`).

**Decision: drop it, no `surfaces` ClassVar replacement.** The default for an
omitted `surfaces=` is already LISTED on every surface — a verb is "available on
all surfaces" by default, which is the sensible baseline. A Router-level default
only adds a second placement mechanism for the rare "restrict the whole router"
case; that case is expressed per-verb with `surfaces=(...)`. Fewer surfaces, one
placement axis (§2 no-redundancy). Removing the `visibility` ClassVar also
removes its application loops in `routers.py` (`meta.extras.visibility =
type(self).visibility`) and `app.py` (`= "all"`). The 3 class-level tests move to
per-verb `surfaces=("cli",)` on each restricted verb.

### D2. `AK211` (`A2K-SURFACE-EXPLICIT`) prescribes `surfaces=`, not `visibility=`

The rule fires on credential-named tools (`*_login`, `*_credential`, …) that do
not pin their surface placement, so secrets don't default onto the network. It
currently checks for a `visibility=` kwarg. Rewrite it to check for `surfaces=`
(the credential tool SHOULD declare an explicit `surfaces=` — e.g.
`surfaces=("cli",)` for operator-only). Same intent, new vocabulary. Code stays
`AK211`.

### D3. Semantic mapping for the test migration

Derived verbatim from the soon-deleted `_resolve_legacy`
(`registered = ("mcp","api","cli")`):

| Legacy authoring | `surfaces=` equivalent |
|---|---|
| no kwargs / `expose=("mcp","api")` (+ default `visibility="all"`) | omit `surfaces=` (default LISTED on mcp/api/cli) |
| `expose=("mcp",)` | `surfaces=("mcp","cli")` |
| `expose=("api",)` | `surfaces=("api","cli")` |
| `expose=("mcp","api")` explicitly | omit, or `surfaces=("mcp","api","cli")` |
| `visibility="cli"` (expose ignored) | `surfaces=("cli",)` |
| `visibility="hidden"` (expose ignored) | `surfaces={"cli":"unlisted"}` |
| class-level `visibility = "cli"` on a Router | class-level `surfaces = ("cli",)` |

Rationale for the CLI-presence rows: legacy `visibility="all"` always mounted
the verb on the CLI ("god-view") in addition to `expose`, so `expose=("mcp",)`
→ mcp **and** cli LISTED. `surfaces=("mcp",)` alone would drop CLI (every
unlisted surface defaults ABSENT under `_resolve_explicit`), so the faithful
translation is `("mcp","cli")`. Migrating tests must preserve intent, not
transliterate the tuple.

### D4. No tombstone hint — plain removal

Per the user directive and §1, `expose=` / `visibility=` are removed outright,
not turned into hinted tombstones. They fall through to the decorator's normal
signature → `TypeError: read() got an unexpected keyword argument 'expose'`,
caught statically by `ty` and at runtime on decoration. The migration recipe
lives in the CHANGELOG mapping table, not in a per-kwarg hint. (This is the
sunset rule applied immediately: the consumer is migrating now, so the hint
window is zero.)

## Risks / Trade-offs

- **a2web breaks until it migrates.** Intended. a2web pulls v0.42.1 and the
  migration agent fixes every `expose=`/`visibility=` site using the D3 table.
  The break is loud (ty + lint + runtime), never silent.
- **Mis-translating CLI presence.** The `expose=("x",)` → `("x","cli")` rows are
  the trap; a blind `expose→surfaces` rename would silently drop CLI mounting.
  Mitigated by the D3 table and by tests that assert per-surface mount state.
- **Router `surfaces` ClassVar is new public surface.** Small, additive,
  mirrors the removed `visibility` ClassVar; covered by migrating the 3
  class-level tests + a new precedence test.
- **Scope discipline.** Only `expose=`/`visibility=` are removed here. The other
  audit shims (`SURFACE_REGISTRY` proxy, `AmbientContextMissing`,
  `LEGACY_CODE_ALIASES`) are explicitly out of scope — each is a separate
  horizon and a separate change.
