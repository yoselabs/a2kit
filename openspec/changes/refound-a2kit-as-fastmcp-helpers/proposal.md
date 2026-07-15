## Direction update (2026-07-15)

The **destination of the surviving substrate is the shelf** (`yoselabs/shelf`,
promotion-not-publication), **not** FastMCP upstream. a2kit **dissolves**; it does
not re-found as a FastMCP-extras helper library — a fresh 3.x major still absorbing
framework territory would eat a helper package the way it ate the framework. Its
worthy, substrate-indifferent parts promote to the shelf when a second consumer
pulls them; its MCP-shaped glue stays **inline in each consumer** until real
variation reveals its shape. **a2kay is the driving pilot**: see a2kay's
`sunset-a2kit-dependency` change, which decomposes a2kay's a2kit footprint
(shelf / reuse / inline / drop / delete) and sequences the strangler migration.
The extractability invariant below is superseded by the shelf's promotion
doctrine (DEEP·STABLE·WINS, promote-on-2nd-consumer, no consumer import). The rest
of this proposal is the original framework-retirement rationale, still valid.

## Why

a2kit is built **on** FastMCP, and its headline deltas — multi-transport
(one verb → MCP + HTTP + CLI), code mode, tool-failure responses — are now
shipped natively by FastMCP 3.x (`transforms=[CodeMode()]` on Monty; native
tool-failure; stdio/HTTP/WS; `fastmcp generate-cli`). The bottleneck is the
**maintenance treadmill, and it is proportional to a2kit's surface *overlap*
with FastMCP**: every FastMCP release that lands a feature a2kit also built
forces a delete-and-adopt cycle. `a2kit.App` (the one public type, ADR 0019)
is the structural anchor of that overlap — every surface composes through it,
so a FastMCP change cascades framework-wide and no single a2kit capability can
ever be lifted out and proposed upstream.

ADR 0032 records the decision: stop being a framework, become a set of
à-la-carte, independently-extractable helpers over FastMCP. This change adopts
the **architecture and the governing invariant** that make that possible. It
does not itself delete `App` or extract the helpers — that is sequenced,
migration-first, as follow-on changes (see Impact + tasks), because the
real helper signatures emerge from porting a real server, not from speculation.

## What Changes

- **Adopt the à-la-carte helper architecture as a2kit's shape.** The target is a
  bag of independently-importable helpers over FastMCP — `a2kit.tsv` (typed-TSV
  result type + serializer, the one piece that genuinely needs a decorator),
  `a2kit.errors` (unified error envelope), `a2kit.rest` (optional verb→REST
  projection), `a2kit.cli` (optional verb→CLI adapter), `a2kit.lint` (static
  analyzer, zero runtime coupling) — replacing the `App`-rooted framework.
- **Establish the extractability invariant as the governing constraint.** Every
  a2kit helper depends only on `fastmcp` + `pydantic` + stdlib — never on a
  shared a2kit core, `App`, DI container, or config. Any helper must be liftable
  into FastMCP as *copy one file + open one issue*. This invariant is the
  fitness function that keeps the treadmill bounded and makes a2kit a
  one-helper→one-upstream-PR contribution pipeline.
- **Invert the consumer dependency.** Consumer servers depend on FastMCP
  directly and add a2kit helpers à la carte; a2kit is an optional add-on, not the
  composition root.
- **Sequence the execution migration-first (follow-on changes).** Port one
  representative server to plain FastMCP, write missing helpers inline, let real
  usage fix each helper's FastMCP-native signature, then extract the proven
  helpers and delete the framework. Each removal/extraction is its own spec delta
  in a follow-on change — not in this umbrella.

## Capabilities

### New Capabilities

- `fastmcp-helper-architecture`: a2kit is a set of independently-importable
  helpers over FastMCP, each depending only on `fastmcp` + `pydantic` + stdlib,
  with no shared a2kit core. The extractability invariant (any helper liftable
  upstream as copy-one-file + open-one-issue) is enforced as an architectural
  fitness function, and the consumer dependency points at FastMCP directly.

### Modified Capabilities

- None in this umbrella change. The `App`-bearing capabilities
  (`core-composition`, `app-lifecycle`, `surfaces-projection`,
  `multi-surface-authoring`, `cli-surface`, `http-surface`,
  `code-mode-sandbox-runtime`, `code-execution`, `typed-error-contract`,
  `verb-decorators`) are **MODIFIED/REMOVED by the sequenced follow-on changes**,
  not here. This change establishes the target architecture and the invariant
  the follow-ons must satisfy.

## Impact

- **Code (this change):** none. This is an architecture-adoption + invariant +
  ADR-linkage change; the code lands in follow-on changes.
- **Decisions:** delivers ADR 0032. On ADR 0032 acceptance, supersedes ADR 0028
  (unified-surface) and ADR 0019 (app-runtime split); deprioritizes ADR 0031
  (MCP Apps → thin `ui://` surface only — rich UI is a JS-bundler/TS concern).
- **Follow-on changes (sequenced, migration-first):** (1) port one server to
  plain FastMCP + inline helpers; (2) extract proven helpers into FastMCP-native
  modules; (3) delete redundant surfaces FastMCP now owns (code mode,
  tool-failure wrapping, transport plumbing, CLI-as-framework); (4) retire
  `a2kit.App` and the framework spine (the breaking one — supersedes 0028/0019,
  rewrites `tests/surface/` snapshots); (5) per-helper upstream-gap backlog →
  FastMCP contribution pipeline.
- **Consumers (eventual):** servers migrate from `a2kit.App` to plain FastMCP +
  helpers. Breaking, delivered over the follow-on sequence; each change carries
  its CHANGELOG migration row (§1, the sole channel).
- **Out of scope:** the full README rewrite to the "FastMCP-extras sandbox"
  positioning (deferred until the helper code lands; a Direction banner pointing
  to ADR 0032 is in place now). Rich MCP Apps UI (ceded to TS/JS).
