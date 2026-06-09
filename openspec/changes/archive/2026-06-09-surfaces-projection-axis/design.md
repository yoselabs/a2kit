# Design — surfaces-projection-axis

> Wave 2, BREAKING. Decision record: [ADR 0028](../../../docs/adr/0028-unified-surface-architecture.md)
> (decision 2 + the resolved "UNLISTED spelling" open call).
> Model: [`docs/SURFACE_ARCHITECTURE.md`](../../../docs/SURFACE_ARCHITECTURE.md) §3.

## The three-state matrix

A verb's placement is one fact: for each registered surface, the verb is
in exactly one of three states.

```
   projection(verb, surface) ∈ { ABSENT, LISTED, UNLISTED }

   ABSENT     not mounted at all              (was: surface ∉ expose)
   LISTED     mounted + advertised            (was: visibility="all")
   UNLISTED   mounted + callable, hidden       (was: visibility="hidden")
```

Two render facets fall out of the state, one per surface implementation:

| state    | mounted (callable)? | advertised (listing/help/schema)? |
|----------|---------------------|-----------------------------------|
| ABSENT   | no                  | no                                |
| LISTED   | yes                 | yes                               |
| UNLISTED | yes                 | no                                |

Every native surface can express all three faithfully (MCP hidden-meta,
Typer `--help` hide, FastAPI `include_in_schema=False`), so UNLISTED is
real, not faked.

## Spelling — one knob, tuple shorthand + dict escape

The author never writes the full matrix. Two spellings cover every case
(ADR 0028 resolved "UNLISTED spelling"):

```
   surfaces=("mcp", "cli")          tuple shorthand → LISTED on named, ABSENT elsewhere
   surfaces={"cli": "unlisted"}     dict escape     → named state explicit, ABSENT elsewhere
   (omitted)                        default         → LISTED on every registered surface
```

- A **tuple** is the common case: "appear and be advertised on these
  surfaces." Any surface not in the tuple is ABSENT.
- A **dict** is the escape for the rare present-but-hidden case. Keys are
  surface names, values are `"listed"` | `"unlisted"`. Any surface not a
  key is ABSENT. (`"absent"` may be written explicitly but is the
  no-op default.)
- **Omitting** `surfaces=` means LISTED everywhere — the friendly default
  matching today's `expose=("mcp","api")` + `visibility="all"` plus the
  CLI (now a peer surface).

A tuple and a dict are mutually exclusive forms of the same kwarg; the
common path stays a tuple, the dict is reached for only when a surface
must be UNLISTED.

## Migration map — old (expose, visibility) → new `surfaces=`

Surface names assumed registered: `mcp`, `api`, `cli`. Today's
`expose` default is `("mcp", "api")` and `visibility` default is `"all"`.

| old `expose` | old `visibility` | meaning today | new `surfaces=` |
|---|---|---|---|
| `("mcp","api")` (default) | `"all"` (default) | mounted + advertised on network; CLI god-view | `("mcp","api","cli")` — or **omit `surfaces=`** (LISTED everywhere) |
| `("mcp","api")` | `"hidden"` | mounted on network, absent from `--help`, skipped by MCP | `{"cli": "unlisted"}` (present-but-hidden; pick the surface(s) it must remain callable on) |
| `("mcp","api")` | `"cli"` | network mount but CLI-only intent (the overlap that leaked) | `("cli",)` |
| `("mcp",)` | `"all"` | MCP only, advertised | `("mcp",)` |
| `("api",)` | `"all"` | HTTP only, advertised | `("api",)` |
| `()` | (any) | rejected today (empty expose) | n/a — author chooses a non-empty `surfaces=` |
| (any) | `"cli"` | CLI-only operator surface | `("cli",)` |
| (any) | `"hidden"` | mounted but unadvertised | `{<surface>: "unlisted"}` |
| n/a | n/a | once-proposed `@cli()` operator command | `surfaces=("cli",)` on a normal `@read`/`@write` verb (never built; retired) |

Resolution precedence inside the decorator:

```
   1. surfaces= omitted              → LISTED on every registered surface
   2. surfaces= is a tuple of names  → LISTED on each named, ABSENT on the rest
   3. surfaces= is a dict            → state per key, ABSENT on unlisted keys
```

`visibility="cli"` is the load-bearing migration: it was honored by MCP
and CLI but **leaked onto HTTP** (Wave-0 `fix-http-visibility-leak`
patched the leak in the *old* vocabulary). Here it becomes
`surfaces=("cli",)` — ABSENT on every network surface by construction, so
the leak is impossible, not merely patched.

## Why one axis beats two

- **No overlap.** `expose=()` ≈ `visibility="cli"` was two ways to say
  "not on the network." The matrix has exactly one representation per
  intent.
- **Advertisement and mounting are separable but co-located.** Today
  `visibility` mixed "is it mounted" (on MCP/CLI) with "is it
  advertised"; `expose` only meant "is it mounted" (network). The matrix
  splits mount vs advertise *cleanly* (LISTED vs UNLISTED vs ABSENT)
  while keeping them under one kwarg.
- **One key for the audit log.** Placement and the canonical name are the
  two halves of "what is this call"; one axis means one resolver to test
  and one rule to teach.
- **`@cli()` never needs to exist.** An operator command is just
  `surfaces=("cli",)` — no fourth spelling. The verb keeps its read/write
  semantics (readOnlyHint / destructiveHint); `surfaces` carries only
  placement.

## Descriptor shape

`ToolDescriptor` drops `expose: tuple[str, ...]` and gains the resolved
matrix:

```
   surfaces: Mapping[str, Literal["absent", "listed", "unlisted"]]
```

It is **fully resolved at materialization** (every registered surface has
a state — no `None`/inherit left to read), immutable
(`types.MappingProxyType`), and is the single field every surface reads
to decide mount + advertise. The Wave-0 `_http_mountable(desc)` predicate
becomes:

```
   mount(desc, "api")     = desc.surfaces["api"] in {"listed", "unlisted"}
   advertise(desc, "api") = desc.surfaces["api"] == "listed"
```

and the symmetric pair for `mcp` and `cli`.

## Co-ship dependency (Wave 2)

This change is one of four that form a single breaking surface and land
together with one migration table:

- **`surfaces-projection-axis`** (this) — *which* surfaces + *advertised?*
- **`native-tree-homomorphism`** — *what is it named there* (flat
  `slug_leaf`, `canonical_name_override`, native mount/include/add_typer).
- **`router-class-auto-collect`** — *how it is authored* (`tools=` tuple
  removed; `@a2kit`-marked methods auto-collected).
- **`app-as-peer-root`** — app-level typed verbs (bare names, top-level
  commands).

They co-ship because a consumer migrating one without the others has a
half-broken surface (e.g. a new `surfaces=` axis but no place for an
app-level verb to land, or a renamed tool whose placement is undefined).
Wave 1 (`cli-as-surface`) must precede all four — the matrix's `cli`
state is meaningful only once the CLI is a real registered surface.

## Deprecation / compatibility

The break is loud, not silent. Removed `expose=`/`visibility=` kwargs
raise a `TypeError` at decoration time naming the new kwarg and the
mechanical mapping (e.g. `visibility="cli"` → `surfaces=("cli",)`). A
thin migration shim (one decoration-time interception that maps a
recognized old pair to the new matrix and emits a `DeprecationWarning`)
MAY ship for one minor version to ease the downstream migration window,
but the canonical surface is `surfaces=` only and the shim is removed at
the next minor. The descriptor's `expose` field is removed outright (it
was internal projection state, not authoring surface).
