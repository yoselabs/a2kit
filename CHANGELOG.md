# Changelog

## 0.46.0 — 2026-06-28

### Added — `McpConfig.code_mode` declares the code-execution default (`add-code-mode-config-default`)

`code_mode` becomes a per-server-**shape** knob an App can declare once, the
same category as `McpConfig.instructions` / `structured_output`. New field
`McpConfig.code_mode: bool = True`, settable via `A2KIT_MCP__CODE_MODE` (env
beats code, ADR 0022). The framework default stays `True`, so a2db / a2atlassian
are untouched; a few-tool / lean-payload server (a2web) declares
`code_mode=False` once instead of repeating a CLI flag in every client mount.

- `build_mcp_server`'s `code_mode` is now tri-state `bool | None` (default
  `None`): `None` consults `config.mcp.code_mode`; an explicit `True`/`False`
  wins. Resolution order end-to-end: explicit CLI flag → `config.mcp.code_mode`
  (env → code) → built-in `True`.
- The `a2kit code` subcommand stays hard `code_mode=True` (invoking the sandbox
  is the explicit point of that command).

### Changed — `serve` code-mode override is now a bidirectional pair (BREAKING)

The one-directional `serve --code-mode-off` flag is **replaced** by an absolute
`--code-mode / --no-code-mode` pair (`Optional[bool]`, default unspecified):
`--code-mode` forces on, `--no-code-mode` forces off, neither defers to config.
A flag means the same thing on every server (absolute, not relative to the
configured default) and can force-on a config-off server. The old
`--code-mode-off` spelling is removed outright (no shim, §1); migrate to
`--no-code-mode` or set `config.mcp.code_mode=False`.

## 0.45.0 — 2026-06-20

### Added — On-serve background services + `ServeContext` (`add-serve-services`, ADR 0030)

An `App` can register **on-serve services** via the `serve_services` ClassVar —
coroutine functions `async def (ctx: a2kit.ServeContext) -> None` that `serve`
runs as concurrent tasks for the whole serve lifetime, sharing the one runtime
(DI root + `SINGLETON` store). They start eagerly at serve start and **only**
under `serve` — never on a CLI verb. Each receives a `ServeContext` carrying the
bound `--internal-uds` path and the transport. Unblocks a2kay's in-serve job
scheduler (`a2kay-job-scheduler`).

- New Tier-1 export `a2kit.ServeContext` (`internal_uds: str | None`, `transport`).
- `AppRuntime.serve_services` carries the registered tuple; an App with none is a
  no-op (unchanged behavior).

### Changed — `serve` collapsed to one supervised engine (internal)

The three divergent `serve_process` paths (bare stdio, bare http, spoke) are
unified into one engine: it runs the public listener (+ optional spoke) + any
registered services under a single `async with runtime:`, supervised by an
`asyncio.wait(FIRST_COMPLETED)` loop with asymmetric shutdown — a listener
exiting ends serve, any task raising tears it down, a service finishing cleanly
is a non-event (not `asyncio.TaskGroup`, not a flat `gather`: both hang on a
never-returning service). Public `serve` behavior is unchanged; the private
`_serve_with_spoke` was removed (no shim, §1).

## 0.44.0 — 2026-06-17

### Added — Internal spoke: first-party jobs call verbs over a private UDS (`add-internal-spoke`, ADR 0029)

`serve --internal-uds PATH` adds a co-resident **spoke** listener — a private
Unix-domain-socket endpoint (created `0600`, off-host-unreachable) that runs in
parallel with the public listener and shares the one runtime (one DI root
container, one `SINGLETON` store). First-party sandboxed jobs reach the
single-writer core over it without traversing the public network edge auth.

- New `a2kit.TokenAuth(resolve=...)` (`target="internal"`): validates a lease
  token **per request** against a consumer-owned live set — instant revocation,
  no fixed TTL (survives day-long jobs). a2kit ships the mechanism; the runner
  owns the lease table.
- New `a2kit.spoke.client(socket_path, token)` → `invoke(name, **kwargs)`: the
  supported client; carries no catalog of its own (reaches the API surface's
  projected verbs by canonical name).

### Changed — `serve --transport=http` now multiplexes MCP + API (BREAKING)

The wired `serve` previously served **MCP only** over http (a `serve-topology`
spec violation). It now runs the multiplex parent: MCP under `/mcp` **and** the
REST surface under `/api`. Narrow to one with `--select 'surface=mcp'` /
`--select 'surface=api'`. The `--compact` / `--tools` / code-mode knobs now
thread into the multiplex MCP build. stdio is unchanged (MCP only).

### Removed — orphaned serve command + redundant auth helper (BREAKING)

| Removed surface | Now raises | Replacement |
|---|---|---|
| `a2kit.packages.mcp.cli` / `build_serve_command` | `ImportError` / `AttributeError` | the wired Typer `serve` (now the canonical multiplex); narrow with `--select` |
| `a2kit.packages.auth.build_api_key_middleware` | `ImportError` / `AttributeError` | `APIKeyAuth(...).build_middleware()` |

`auth.AuthTarget` is opened from `Literal["api", "mcp"]` to an open `str` so
consumer/internal surface names (e.g. `"internal"`) can be auth targets;
`AuthSpec` now requires `build_middleware()` (the substrate mount is generic —
no `isinstance` chain).

## 0.43.0 — 2026-06-11

### Changed — Purged all backward-compat machinery: tombstones, aliases, migration hints (BREAKING)

`AGENTS.md` §1 is rewritten ("No backward compatibility, no migration hints").
A removed surface now raises the **language-default** error
(`AttributeError` / `TypeError` / `ImportError`) and nothing more: no alias, no
`DeprecationWarning`, no tombstone, **no embedded migration hint**. The
migration recipe lives in exactly one place — this CHANGELOG. The lone
carve-out is a deletion that would otherwise *silently misbehave* (a
load-bearing invariant), which keeps a terse present-tense guard.

This release deletes every remaining instance of that machinery. Behavioral
note: the tombstoned names below were already non-functional; what changes is
that they now raise the **plain** error instead of a hinted one (and the DI /
`TestClient` names change from `TypeError` to `AttributeError`).

**Removed tombstones** (old name → raises plain error; use the replacement):

| Removed surface | Now raises | Replacement |
|---|---|---|
| `App.add_router(r)` | `AttributeError` | compose declaratively: `class Kay(a2kit.App): routers = (R, ...)`, or `a2kit.testing.app_of(name, R())` in tests |
| `a2kit.App(...)` direct construction | `TypeError` ("App is abstract") | subclass `a2kit.App` (or `app_of(...)` in tests) — message no longer cites ADR/version |
| `Container.register(T, f)` | `AttributeError` | `Container.provide(T, f)` |
| `Container.register_singleton(T, f)` | `AttributeError` | `Container.provide(T, f, scope=Scope.SINGLETON)` |
| `Container.resolve(T)` / `aresolve(T)` | `AttributeError` | `await Container.get(T)` |
| `Container.has(T)` | `AttributeError` | `Container.has_provider(T)` |
| `Container.has_async_singleton` / `has_any_async_singletons` | `AttributeError` | no replacement (sync/async factories no longer distinguished) |
| `TestClient.call(...)` | `AttributeError` | `TestClient.invoke(...)` |
| `TestClient.override(T, fake)` | `AttributeError` | re-build: `app_of(name, ...).provide(T, fake)` (last-write-wins), then a fresh `TestClient` |

**Removed silent aliases** (these were still WORKING — removing them is a
behavior change):

| Removed | Effect | Replacement |
|---|---|---|
| `LEGACY_CODE_ALIASES` + `normalize_code` (lint) | old `# noqa: A2K-LAYER` / `A2K014` and `[tool.a2kit.lint] disabled=["A2K014"]` no longer resolve | use the new codes (`AK###` / `AKR###` / `RG###`); e.g. `A2K-LAYER`→`AK200`, `A2K014`→`AK014`, `A2KR001`→`AKR001`, `REGO-NAME-COLLISION`→`RG002` |
| `_REGO_LEGACY_ALIASES` (rego extractor) | old `# noqa: REGO-BODY-DUP` no longer recognized as a rego rule | spell rego suppressions `# noqa: RG001 -- <reason>` |
| `a2kit.exceptions.AmbientContextMissing` | the deprecation-shim exception is gone | catch `a2kit.packages.context.request_scope.RequestScopeMissing` (a `LookupError`); the `MODE_*` constants no longer exist |
| `a2kit._lazy_module.lazy_attr(removed=…)` plumbing | dead `removed=` param / `RemovedHints` type / `_REMOVED` branch deleted | n/a (was unused) |

**Other:** stale `SURFACE_REGISTRY`-proxy doc references (the proxy itself was
already gone) are scrubbed; readers use `current_registry()` / the active
`SurfaceRegistry`. New `a2kit.packages.lint.rego.REGO_RULE_CODES` (the RG rule
set, sourced from the bundled `.rego` policies) is the canonical RG-code source.

## 0.42.1 — 2026-06-11

### Changed — Removed the legacy `expose=` / `visibility=` kwargs outright (BREAKING)

v0.42.0 kept `@a2kit.read/write/list_(expose=…, visibility=…)` working as a
**silent** backward-compat shim (mapped forward to `surfaces=` with no warning).
That is the exact drift-hiding `AGENTS.md` §1 forbids ("graceful migration paths
hide drift from consumer read paths"), so the kwargs — and the Router-level
`visibility` ClassVar default — are now **removed entirely**. There is no shim,
no `DeprecationWarning`, no hinted tombstone: passing either kwarg raises the
language-default `TypeError: read() got an unexpected keyword argument 'expose'`
(caught statically by type checkers, at decoration time at runtime). `surfaces=`
is the sole surface-placement axis.

**A verb is available on all surfaces by default.** Omitting `surfaces=` is
LISTED on `mcp` / `api` / `cli` — only opt *out* per-verb. There is no
Router-level surface default (the `visibility` ClassVar is gone); a whole
operator router that was CLI-only now spells `surfaces=("cli",)` on each verb.

**Migration recipe.** The default surfaces are `("mcp","api","cli")`; legacy
`visibility="all"` also always mounted the CLI ("god-view"), so faithful
rewrites preserve CLI presence — a blind `expose→surfaces` rename silently drops
the CLI mount:

| Old | New |
|---|---|
| `expose=("mcp","api")`, `visibility="all"`, or nothing | omit `surfaces=` (default LISTED on mcp/api/cli) |
| `expose=("mcp",)` | `surfaces=("mcp","cli")` (CLI preserved) |
| `expose=("api",)` | `surfaces=("api","cli")` |
| `visibility="cli"` | `surfaces=("cli",)` |
| `visibility="hidden"` | `surfaces={"cli": "unlisted"}` |
| `class Foo(Router): visibility = "cli"` | per-verb `surfaces=("cli",)` (no Router-level default) |

The `AK211` (`A2K-SURFACE-EXPLICIT`) lint rule now prescribes an explicit
`surfaces=` on credential-named tools (was `visibility=`); the `A2K-SUBSTRATE-DEP`
rule reads `surfaces=` to decide MCP-exposure. The `A2KitMetaExtras.visibility`
field and the `a2kit.tool.Visibility` type are removed; `extras.expose` /
`ToolDescriptor.expose` (the derived mounted-surfaces tuple) are unchanged.

## 0.42.0 — 2026-06-10

### Changed — ADR 0028 unified surface: one typed verb projects to MCP/HTTP/CLI; App is authored by subclassing (BREAKING)

The headline surface rewrite. A tool is now authored once as a typed verb
and **projected** onto every surface (MCP / HTTP / CLI) from one
definition, and the `App` is authored by **subclassing** rather than
imperative composition. This is the largest break since v0.33 — read the
migration table before upgrading.

**App is now a subclass, not an imperatively-composed instance
(app-as-peer-root).** Author by subclassing `a2kit.App` with class
attributes; positional `a2kit.App("name")` construction and the public
`App.add_router(...)` verb are **removed** (both raise with a `routers=`
hint). App-level verbs (`@app.read`-decorated methods on the subclass)
render BARE (no slug prefix).

```python
# before
app = a2kit.App("kay")
app.add_router(EntityRouter(get_store))
app.add_router(OntologyRouter())
a2kit.run(app)

# after
class Kay(a2kit.App):
    name = "kay"
    routers = (EntityRouter, OntologyRouter)   # Router *classes*, not instances
    providers = (get_store,)                    # was add_router-time provide()

Kay().serve()        # or a2kit.run(Kay()) / build_mcp_server(Kay())
```

**Routers auto-collect their verbs (router-class-auto-collect).** The
`tools = (...)` tuple is **removed**; any method decorated with
`@a2kit.read` / `@a2kit.write` / `@a2kit.list_` is collected via
`__init_subclass__` (marker-walk, not a `dir()` walk). Drop the tuple.

**Canonical tool names are now flat `{slug}_{leaf}`
(native-tree-homomorphism).** A verb `search` on a Router with
`slug = "jira"` registers on MCP/HTTP as `jira_search` (flat), not
`jira.search` or a mounted prefix. This flat name is the single
call-log / audit key and is identical on every surface; it fixed the
**silent MCP tool-name collisions across routers**. The CLI still renders
nested (`app jira search`). Pin a verbatim name with
`canonical_name_override="..."` (used as-is, slug never re-applied). A new
Tier-2 backstop `a2kit.runtime.validate_composition(app)` asserts global
canonical-name uniqueness offline (also runs inside `build()`), failing
loud and naming both offending verbs.

**`surfaces=` projection axis replaced `expose=` / `visibility=`.** A
verb's surface matrix is now `@a2kit.read(surfaces=...)` with
`{absent, listed, unlisted}` semantics. In v0.42.0 the old `expose=` /
`visibility=` pair still worked as a **silent** compat shim (no warning);
it is **removed outright in v0.42.1** — migrate to `surfaces=`.

**Test authoring: `a2kit.testing.app_of(name, *RouterClasses, **kw)`.**
Returns an anonymous `App` subclass instance for fixtures and throwaway
apps — the replacement for `App(...) + add_router(...)` in tests.

**Migration (consumer-facing):**

| Old | New |
|---|---|
| `app = a2kit.App("n")` + `app.add_router(Foo())` | `class MyApp(a2kit.App): name = "n"; routers = (Foo,)` |
| `a2kit.run(app)` / `build_mcp_server(app)` | `MyApp().serve()` / `a2kit.run(MyApp())` / `build_mcp_server(MyApp())` |
| `class Foo(Router): tools = (x, y)` | drop `tools=`; `@a2kit.read/write/list_` methods auto-collect |
| `@a2kit.read(expose=("mcp", "api"))` / `visibility=` | `@a2kit.read(surfaces=...)` (silent compat in v0.42.0; removed in v0.42.1) |
| MCP tool name `jira.search` / mounted prefix | flat `jira_search` (`{slug}_{leaf}`); pin with `canonical_name_override=` |
| test: build an `App` + `add_router(...)` | `a2kit.testing.app_of("n", FooRouter, BarRouter)` |

**Also in this wave:** per-surface ctx identity — `a2kit.log.current_surface()`
(`"mcp"`|`"api"`|`"cli"`) and `current_surface_client_id()` readable inside
dispatch; `McpConfig.instructions` threaded into the FastMCP server
(server-level instructions); the CLI is now a first-class `Surface`
(`app.cli`); Wave 0 fixes — CLI vendored-click guard (typer ≥ 0.26) and an
HTTP `visibility`-leak fix. See ADR 0028.

### Changed — Lint codes are ruff-`noqa`-grammar-safe: `AK###` / `AKR###` / `RG###` (BREAKING for suppressions)

a2kit lint codes were renamed so a2kit and ruff can co-suppress on one
line: `A2K###` / `A2K-*` → `AK###` (static) / `AKR###` (runtime),
`REGO-*` → `RG###` (rego), all matching `^[A-Z]+[0-9]+$`. Existing
`# noqa: A2K-*` / bare-`A2K###` comments still resolve through a
transitional `LEGACY_CODE_ALIASES` table (`normalize_code`), so nothing
breaks immediately — but migrate suppressions to the new spellings
(anchors: `AK014` SLOC, `AK200` layer, `AK210` metadata-private,
`AKR001`, `RG002` name-collision). The alias table sunsets once no legacy
`# noqa` comments remain.

### Changed — Tombstone sunset: settled migration hints swept (prune-stale-tombstones)

`AGENTS.md` §1 gains a **sunset clause**: a migration-hint tombstone is a
transition aid, not a permanent surface. It is kept only until the live
downstream consumer has migrated past the removal (the migration
horizon), then deleted — the swept name raises the language-default
`AttributeError` / `TypeError` (still loud, no alias, no transitional
period, just no bespoke hint).

The first sweep removes ~10 settled tombstones (v0.23–~v0.38, all past the
horizon). The removed surfaces stay removed; only their *bespoke* hint
strings go. The migration recipes remain in git history and the original
removal's CHANGELOG row:

- `@a2kit.tool` (v0.33) → `a2kit.tool` now raises a plain `AttributeError`.
  Use `@a2kit.read` / `@a2kit.write` / `@a2kit.list_`.
- `App(lifespan=)` / `App(health_tool=)` (v0.35), `App(debug=)` (ADR 0022)
  → now the generic unexpected-kwarg `TypeError` (names the kwarg + the
  CHANGELOG), not a per-kwarg hint.
- `Router.lifespan` classmethod (v0.35) → no longer special-cased
  (implement `__aenter__`/`__aexit__`); `app.provide(teardown=)` (v0.36)
  → generic unexpected-kwarg `TypeError`.
- `App.debug` / `app.debug` → plain `AttributeError`; read `app.config.debug`.
- `Substrate` Literal (`a2kit.packages.dispatch.substrate`) → simply absent.
- `a2kit.packages.cli.context` tombstone module → deleted; import the
  relocated context types from `a2kit.packages.context`.
- `TOONSnapshotExtension` (v0.23) → already gone; doc reference pruned.

**Kept** (in-flight, a2web will hit them when it migrates): positional
`a2kit.App(...)` + `App.add_router` (ADR 0028), the refound-log surface,
the v0.40 `TestClient` renames.

### Changed — log refounded on stdlib `logging`; one surface `a2kit.log` (BREAKING)

The bespoke log (Logging / Data / Diagnostics) channel is retired and
re-founded on Python's stdlib `logging`. There is now exactly **one
author concept: `a2kit.log`** — the four level methods (`debug` / `info`
/ `warning` / `error`), each accepting a message + fields OR a typed
instance. The MCP wire still streams live, mid-call (inline `await
ctx.log()` — not regressed). A durable, queryable **call access-log** is
added: a transport-neutral dispatch-boundary stage auto-captures one
span-shaped record per tool call (`call_id` + args/result/timing/
principal) on a dedicated, non-streaming `a2kit.calls` logger written to
opt-in JSONL with content-addressed body sidecars.

**Removed (no aliases, clean break):**

- `a2kit.log.event()`, `a2kit.log.report()`, the `@reports(T)` decorator,
  `EventRegistry` + `emit_typed`, and the loose `a2kit.log.log()` verb.
  The typed-instance ergonomic survives: `a2kit.log.info(instance)`.
- `app.log` / `_AppLog`, `App.set_log(...)`, `app.log_reports` /
  `app.log_events`, and the CLI `--no-reports` / `--no-events` flags.
- `a2kit.logging.LogRecord` / `logging.Handler` (→ stdlib `logging.LogRecord` /
  `logging.Handler`), `ReportTypeNotDeclared` / `ReportTypeMismatch`, and
  the 147-LOC `the removed report-type lint rule` lint rule.

**Migration:**

| Old | New |
|---|---|
| `a2kit.log` (module) | `a2kit.log` |
| `a2kit.log.event(x)` / `app.log.events.emit_typed(x)` | `a2kit.log.info(x)` |
| `a2kit.log.report(x)` | `a2kit.log.info(x)` (or `a2kit.log.debug(x)`) |
| `a2kit.log.info/warning/error/debug` | `a2kit.log.info/warning/error/debug` |
| `LogConfig` / `A2KIT_LOG__*` / `app.config.log` | `LogConfig` / `A2KIT_LOG__*` / `app.config.log` |
| `app.log.add_sink(s)` | `app.log.add_handler(h)` (stdlib `logging.Handler`) |
| `App.set_log(...)` / `--no-events` | `A2KIT_LOG__ENABLED=false` (kill-switch) |
| `bind_call_scope(...)` (test SPI) | `bind_call_scope(...)` |

The durable call-log is opt-in: `A2KIT_LOG__CALL_LOG=on` (off by
default). structlog was evaluated and **rejected for core** (80ms+
import on the hot path violates the ADR 0020 cold-start guarantee); it
remains available to consumers for their own app-logging (ADR 0022). See
ADR 0027.

## 0.41.1 — 2026-05-28

(`v0.41.0` tag was placed on the v0.40.1 commit by mistake earlier the
same day; this is the actual release of the lint-bundle work.)

### Changed — Rego lint bundle moves inside `a2kit.packages.lint`

The Rego policy bundle (5 `.rego` files) + the AST fact extractor
(`extract_facts.py`) ship INSIDE the package at
`a2kit/packages/lint/_bundle/`. `a2kit lint rego` defaults to the
packaged bundle — consumers no longer vendor ~1000 LOC of policy
infrastructure to use it. The per-project `policies/data.json`
(allowlist with reasons) is the only file a consumer ships;
`run_rego_policies` auto-discovers it from CWD.

Migration: delete `policies/*.rego` and `scripts/extract_facts.py` from
your repo. Keep `policies/data.json`. Continue invoking
`uv run a2kit lint rego src/ pyproject.toml`.

`--policies-dir`, `--extract-script`, and `--data` flags override the
defaults when a consumer needs to fork the bundle or point at a
non-standard allowlist.

Implementation detail: OPA's `--bundle` + `--data` flag combo strips
the data namespace when both are present, so the wrapper merges
packaged policies + project data.json into a single temp bundle dir
before invoking opa eval. Verified manually 2026-05-28.

## 0.40.1 — 2026-05-28

### Changed — `prune_empty` marker → `PruneEmpty` base class (breaking, same-day)

a2web validation surfaced a cascade gap: the v0.40.0 `prune_empty()`
`ConfigDict` marker only fired from `dump_model_for_wire` on top-level
models, so empty fields on nested children (e.g. `AskExtraction` inside
`AskResponse`) were never pruned. Switched to a pydantic-native base
class — pydantic uses each model's own `@model_serializer` for nested
fields, so cascade is automatic.

Migration: replace
`class M(BaseModel): model_config = ConfigDict(**prune_empty())`
with `class M(PruneEmpty): ...`. Removed exports:
`prune_empty`, `model_wants_prune`, `PRUNE_EMPTY_KEY`. Added export:
`PruneEmpty` (top-level `a2kit.packages.formatter.PruneEmpty`).

`dump_model_for_wire(model)` is now a thin `model.model_dump(mode="json")`
wrapper, kept as the substrate seam for future wire-shaping.

Pydantic-native alternative noted: classes whose only "empty" values are
`None` can use `model_dump(exclude_none=True)` directly — no a2kit
dependency needed. `PruneEmpty` is the substrate convenience for the
broader `None`/`""`/`[]`/`{}` semantic.

## 0.40.0 — 2026-05-28

### Features — a2web-handoff-prep (ergonomic substrate fixes)

Three small additive features driven by a2web's accumulated v0.40-v0.41
wish list. Each lets consumers delete workaround code; none breaks the
existing surface. Constitution Article VI (Magic Budget) check: 2 new
consumer-facing concepts. PASS.

- **`a2kit.formatter.prune_empty()` marker** — opt-in pruning of empty
  fields (`None` / `""` / `[]` / `{}`) from the JSON wire payload. Set
  via `model_config = ConfigDict(**prune_empty())` on a return type.
  Zero-valued types (`0`, `False`, `Decimal(0)`) are KEPT — they carry
  information. JSON schema is unchanged (pruning is wire-only).
  Removes a2web's per-model `_prune_wire` workaround (~90 LOC).
- **Runtime tool selection** — `A2KIT_TOOLS=<comma-list>` env var +
  `serve --tools=<comma-list>` CLI flag. Filters the descriptor set
  before MCP server registration and CLI subcommand registration.
  When both are set, the intersection wins. Cannot re-enable tools
  filtered out at compile time by `visibility="hidden"`. Unknown
  names fail closed with a clear error listing valid names. Removes
  a2web's `ask_only` flag + constructor-time router-tools rebuild.
- **`a2kit.Lazy` + `a2kit.logging.LogRecord` top-level re-exports** — both
  graduate from `a2kit.packages.di.Lazy` / `a2kit.packages.log.logging.LogRecord`
  to the top-level surface. The internal paths still work
  (back-compat). `a2kit.packages.*` is now documented as private
  scaffolding (stdlib `_thread` convention).

Substrate refusal applied (Constitution Article V): the v0.41
`a2kit.desc()` sugar wish is **refused** — Article VI's "pydantic is
sacred" clause forbids shorthand that hides a `pydantic.Field`. The
8-12 lines of `Annotated[T, pydantic.Field(description=...)]` ceremony
is the price of staying pythonic.

a2web's downstream cleanup (deleting `_prune_wire`, `ask_only`) ships
separately in a2web's next change.

### Tooling — Cross-surface policy bundles (`actionlint` + Rego on workflows + pyproject)

`make lint` now polices GitHub Actions workflow files and
`pyproject.toml` runtime dependencies, on top of the existing Python
AST policies (`adopt-rego-policy-layer`, 2026-05-27). Two additions:

- **`actionlint`** adopted as a native binary, version-pinned in
  Makefile (`ACTIONLINT_VERSION := 1.7.12`), validated by
  `make actionlint-check`. Wired into `make lint` ahead of the Rego
  layer (parser/correctness gate, fast-fail).
- **`policies/github_actions.rego`** — three rules: REGO-GHA-PIN-SHA
  (third-party `uses:` must be pinned to 40-char SHA),
  REGO-GHA-PERMISSIONS (workflow must declare top-level
  `permissions:`), REGO-GHA-VENDOR-ALLOW (vendor must be on
  `policies/data.json` allowlist).
- **`policies/pyproject.rego`** — REGO-PYPROJECT-UPPER-BOUND on
  `[project.dependencies]` (`<X.Y` or `~=X.Y` required;
  `optional-dependencies` and `[build-system]` exempt).

`scripts/extract_facts.py` grows two top-level collections —
`workflows` (with pre-computed `has_pinned_sha` + `vendor` per step)
and `pyproject` (with pre-computed `has_upper_bound` per dep). New
`--repo-root` flag scopes the YAML/TOML collectors (defaults to cwd).

Repo cleanups landed in the same commit:

- `.github/workflows/ci.yml` gains top-level `permissions: contents: read`.
- `pyproject.toml` runtime deps `anyio`, `click`, `fastapi`, `tomli-w`,
  `uvicorn` gain upper bounds.

ADR 0026 records the cross-surface design (`actionlint` stays a binary;
two policy files split per-surface; allowlists carry required
`reason`). Cross-ref: `BACKLOG.md` entry `policy-bundles-cross-surface`
drained.

### Refactor (internal) — HTTP folds `DISPATCH_PIPELINE` (substrate-pipeline-bridge contract)

The HTTP adapter now folds the transport-neutral `DISPATCH_PIPELINE` per
projection tool and per `@app.api.<method>` route, the same way the CLI
and MCP adapters already did (ADR 0019). The hand-rolled
`_apply_authorize_gate` deletes; `AuthorizeGateStage` from the pipeline
runs uniformly across every substrate. A new
`packages/http/_error_render_stage.py` (`HttpErrorRenderStage`) reads
the rendered envelope from the `_render_state` side channel populated
by `ErrorEnvelopeStage` and returns a `JSONResponse` — symmetric to
`packages/mcp/_wrappers.py::McpErrorRenderStage` and
`packages/cli/runtime.py::CliErrorRenderStage`.
`_install_typed_error_handlers` shrinks to a defensive fallback for
`AppError` paths that bypass the pipeline (rare) and non-AppError
exceptions (quarantine → `UnexpectedDefect`). The substrate-side
canonical `http_status_for(exc)` helper moves from `build.py` into
`_error_render_stage.py`; build.py no longer carries its own
`_KIND_HTTP_STATUS` table.

Closes audit smells **S11** (HTTP missing typed-render-stage pattern)
and **S13** (`AuthorizeGateStage` duplicated on HTTP path).

The contract between substrate adapters and the pipeline is documented
as **two named ContextVars**: `request_scope` (inbound typed seeds —
today `Principal`; tomorrow possibly `RequestId`, `Tenant`) and
`_render_state` (outbound rendered envelopes). The contract has its own
capability spec (`openspec/specs/substrate-pipeline-bridge/spec.md`),
reference doc (`docs/dev/substrate-pipeline-bridge.md`), and ADR
(0025). A capability test suite under
`tests/capabilities/substrate_pipeline_bridge/` asserts every
registered substrate honours both sides of the bridge; a future
substrate added without wiring the seams fails CI.

**Behavioural delta: zero.** A pre-refactor wire-snapshot suite
(`tests/packages/http/test_http_error_envelope_snapshot.py`, 8 cases
covering every `AppError` subclass currently emitted) asserts byte-
equivalence of every HTTP error response; all 8 hold after the
refactor. An `authorize=` callable resolving Container-known
dependencies behaved identically on HTTP and MCP before and after (both
routed through the same `_run_authorize_gate(authorize, container)`
helper); the parity test
`tests/packages/http/test_authorize_di_parity.py` pins this.

S7 (DecoratorSurface extracted too shallow) was originally bundled
into scope and dropped as unrelated to the bridge work — different
concern (decorator-factory ergonomics), revisit independently.

### Refactor (internal) — `A2KitMetaExtras` field allowlist sync

The `A2K-EXTRA-NAMESPACE` lint rule's `_TYPED_EXTRAS_FIELDS` allowlist
gained `visibility`, `timeout_seconds`, `expose`, `authorize` — all
declared on `a2kit.metadata.A2KitMetaExtras` but missing from the
rule's mirror. Pre-existing drift surfaced by the new HTTP synthetic-
meta construction site.

### Feature — Open Policy Agent (Rego) as architectural-policy substrate

New second lint tier, distinct from `a2kit lint static`: `a2kit lint
rego` runs OPA-based policies over AST facts extracted from `src/`.
Lands two starter policies:

- `REGO-BODY-DUP` — cross-file function body duplication using a
  normalized AST hash (identifier + literal names stubbed). Catches
  the wire-format-drift class of bug (R6) and same-shape-different-name
  collisions (R1) that token-based clone detectors miss.
- `REGO-NAME-COLLISION` — cross-file `_`-prefixed (non-dunder)
  function name reuse outside the per-policy allowlist.

Policies live in `policies/*.rego` with `policies/data.json` holding
the allowlist (each entry requires a non-empty `reason`). Suppression
grammar: `# noqa: REGO-* -- <reason>` (separator ` -- `, free-text
reason after; REGO-* rules require the reason — stricter than
A2K-*). `scripts/extract_facts.py` is the fact substrate (curated AST
projection, deterministic JSON output). OPA pinned in `Makefile` via
`OPA_VERSION` + `make opa-check`. See ADR 0024 + `docs/dev/rego-toolchain.md`.

Worked-example fixes in the same change:

- **R6** — log wire-format duplication across `packages/log/wire.py`
  and `packages/context/stderr.py` collapses to canonical
  `a2kit._log_wire` foundational module (new entry in
  `FOUNDATIONAL_CORE_MODULES`).
- **R1** — `async def _call` × 2 in `packages/dispatch/` collapses to
  `packages/dispatch/_invoke.py`.
- **R2** — `resolve_hints` lifted to canonical in
  `packages/di/_hints.py`; `a2kit.signature` imports through the
  package front door.
- **R7** — three `_is_basemodel` runtime variants collapse to
  canonical `is_basemodel(ann) -> type[BaseModel] | None` in
  `packages/formatter/inference.py`; cli/codemode import through the
  formatter front door.
- **R8** — `_validate_key` lifted to canonical
  `packages/connections/_validation.py`; config/store import directly.
- **R9** — verb-decorator detectors collapse to
  `detect.is_a2kit_verb_decorator`; AST `_is_basemodel_base` lifts to
  new `packages/lint/rules/_ast_helpers.py`.

Remaining `policies/data.json` allowlist is 7 entries (1 body_dup,
6 name_collision), all genuine intentional convergences with
explanatory `reason` fields — no "scheduled for follow-up" debt.

### Refactor (internal) — Structural-audit residue drain

Drains the remaining mechanical duplications from the 2026-05-27 audit
that the Rego layer doesn't trip (either out of scan scope or
shape-not-body duplication). All purely internal:

- **R3** — `_edit_distance` lifted to `packages/lint/_distance.py`;
  `scripts/find_similar.py` imports it.
- **R4** — `_list_tool_names` promoted to public `list_tool_names` in
  `packages/lint/runtime.py`; script imports the canonical one.
- **R5** — `_import_target` lifted to `packages/lint/_import.py`;
  the Click variant in `packages/lint/cli.py` wraps it for
  `BadParameter`.
- **R10** — five hand-rolled lazy `__getattr__` loaders
  (`a2kit/__init__.py`, `packages/otel|http|mcp|auth/__init__.py`)
  consolidate onto `a2kit._lazy_module.lazy_attr` / `lazy_dir` (new
  foundational module). The remaining two audit hits at
  `packages/cli/context.py` + `packages/dispatch/substrate.py` are
  migration-hint tombstones — a separate pattern, not folded in here.
- **R11** — `_build_mcp_mount_lifespan` + `_build_standalone_lifespan`
  collapse to `_build_mcp_lifespan(*, own_app_lifecycle)` in
  `packages/mcp/server.py`.
- **R12** — `encode_page_tsv` (typed) and `encode_page_tsv_dict`
  (after-FastMCP) share `assemble_page_envelope`; both entry points
  retained — they differ in column-source semantics (model_fields vs
  row-derived).
- **R13** — `ApiSurface` + `McpSurface` drop 3 inline
  lazy-import-then-frozenset helpers and call the canonical
  `fastapi_reserved` / `fastmcp_reserved` / new `fastapi_dep_markers`
  from `a2kit.packages.dispatch` (the helpers were already exposed; the
  surfaces just hadn't consumed them). New `_FASTAPI_DEP_MARKER_SPECS`
  in `dispatch/substrate.py` mirrors the markers spec.

Capability test `test_surfaces_are_passive` updated to allow
`__getattr__ = lazy_attr(...)` / `__dir__ = lazy_dir(...)` assignment-
with-Call (PEP 562 hook binding is semantically equivalent to inline
`def`). No runtime behaviour change.

### Removed — jscpd

`.jscpd.json`, `package.json`, `pnpm-lock.yaml`, and the entire Node
toolchain are deleted. Calibration on 2026-05-27 showed `body_dup.rego`
at the normalized-AST-hash level catches a strict superset of what
jscpd catches at any tuning, with no false positives.

### Feature — `A2K-NO-DICT-STR-ANY` lint rule

- New static-lint rule flags `dict[str, Any]` (and `Dict[str, Any]`)
  annotations on fields of `@dataclass` / `@dataclass(frozen=True)` /
  `pydantic.BaseModel` subclasses under `src/`. Goal is *deliberate*
  `Any` use, not eradication: legitimate sites (wire envelopes,
  third-party kwarg pass-throughs) acknowledge the looseness with
  `# noqa: A2K-NO-DICT-STR-ANY -- <why>`. Out of scope: function
  parameter annotations and `Mapping[str, Any]`.
- `parse_noqa` gained a `-- reason` suffix grammar
  (`# noqa: A2K001 -- why`). The reason after ` -- ` is ignored for
  code matching but documents intent inline.

### Refactor (internal) — CLI builder drops `_a2kit_short_help` callback side-channel

- `_build_tool_callback` now returns `(callback, short_help)` instead
  of stashing the short-help string on `callback._a2kit_short_help`.
  Same shape as the `_render_state` side-channel removal in
  `error-envelope-side-channel`: producer + sole consumer are in the
  same module, so a tuple return is the natural carrier. Drops one
  `ty: ignore[unresolved-attribute]` + one `noqa: SLF001`. The
  remaining `callback.__signature__` assignment is the standard
  `inspect` protocol hook Typer reads, not a side-channel.

### Feature — `A2K-SURFACE-REGISTRY` lint rule + MANIFESTs on built-in surfaces

- New static-lint rule `A2K-SURFACE-REGISTRY`: a class subclassing
  `DecoratorSurface[...]` MUST be accompanied by a module-level
  `MANIFEST = PluginManifest(...)` constant. Without it, the surface
  is invisible to `load_surface()` discovery.
- `McpSurface` and `ApiSurface` each ship a `MANIFEST` constant
  alongside the class — the built-in surfaces now satisfy the same
  discovery contract `adopt-plugin-manifests` introduced for auth
  providers.

### Breaking (internal) — Deprecation shims deleted; context↔log cycle broken

Per the 2026-05-27 cleanup sweep:

- `packages/dispatch/_principal_bridge.py` deleted. The
  `set_request_principal` / `current_request_principal` /
  `current_request_principal_seeds` / `reset_request_principal`
  named API is gone. Use `a2kit.packages.context.request_scope`
  (`publish` / `get` / `try_get` / `reset`) directly.
- `Container.call_scope(scoped_seeds=...)` keyword removed.
  Use `framework_seeds=` (the rename landed in
  `generalise-context-bridges`).
- `packages/dispatch.SURFACE_REGISTRY` module-level proxy deleted.
  The per-runtime `runtime.surfaces` registry is the only canonical
  access path; internal callers without a runtime in hand use
  `a2kit.packages.dispatch.surface.current_registry()`.
- `a2kit._surface_names` kernel module deleted (it served the
  decoration-time `expose=` validation that moved to build time).
- `runtime.build(app)` now always composes a default surface set when
  `surfaces=` is omitted (via the layer-exempt facade), so
  `runtime.surfaces` is never None and `expose=` validation always
  runs against the canonical registry.
- The context↔log lazy-import cycle is broken: `context.stderr`
  inlines a private copy of `format_condensed_line` (with a parity test
  pinning byte-identical output), so `context` no longer imports
  from `log`. The `# noqa: A2K-LAYER` GRANDFATHERED markers on
  both legs are gone.
- Specs updated to the post-shim API: `principal-bridge` now points
  at `request-scope` as the canonical home; `tool-authorization`,
  `dispatch-pipeline`, and `serve-topology` rewritten.

### Feature — Built-in log operator sinks + parallel fan-out

Per `the log-handler fan-out work` (2026-05-27):

- New `a2kit.packages.log.sinks` subpackage with four built-in
  operator sinks: `stderr_pretty_sink`, `stderr_json_sink`,
  `otel_sink`, and `live_sink` (with `make_live_sink(...)` for
  custom event-prefix filters + heartbeat).
- Operator-sink fan-out now runs in parallel via
  `asyncio.gather(..., return_exceptions=True)`. Per-sink failures
  are logged at WARN under `a2kit.log.sink_failed` and dropped,
  isolating the producer + sibling sinks + the wire path. Replaces
  the previous sequential `try / except` per sink.
- `LogConfig` gains 5 knobs: `stderr_sink` (none | pretty | json,
  default none), `otel_sink` (auto | on | off, default auto),
  `live_sink` (off | on, default off), `live_heartbeat_seconds`,
  `live_event_prefixes`. All available via `A2KIT_LOG__*` env.
- The `auto` OTel heuristic registers the sink iff the
  `opentelemetry` SDK is importable AND at least one
  `OTEL_EXPORTER_*` env var is set — avoids the surprise of "I
  imported the SDK for an unrelated reason and now my log output
  disappears."
- App boot reads `LogConfig` and registers enabled built-in sinks
  BEFORE any user-added sink (documented order: built-ins, then
  user-added in registration order).
- No breaking change: default config preserves v0.x behaviour;
  `app.log.add_sink(...)` keeps working; `logging.LogRecord` shape and
  wire path are unchanged.
- New capability spec `log-handlers` ADDED; `log-level-threshold`
  MODIFIED to clarify the single-threshold-before-fan-out invariant;
  `otel-adapter` MODIFIED with the drain-on-missing-SDK contract.

### Internal — Plugin-manifest extension shape (pilot: API-key auth)

Per `adopt-plugin-manifests` (2026-05-27):

- New private framework module `a2kit.packages._plugin` ported from
  a2web (ADR-0001 Pattern 2): `PluginManifest[T]` + `Unavailable`
  sentinel + `load_surface()` / `load_surface_sorted()` reflection.
  Single declarative shape collapsing registration,
  capability-aware configuration delivery, and unavailability handling.
- Pilot surface migrated: API-key auth providers under
  `packages/auth/_providers/api_key.py` declares a `MANIFEST`. The
  factory returns `Unavailable("no api keys configured")` when no
  keys are present, so the provider never lands in the registry on
  an unconfigured deploy.
- `a2kit.packages.auth.discover_api_key_providers(context)` is the
  new lazy entry that wraps `load_surface(...)`. Imperative
  `App.auth(APIKeyAuth(...))` registration continues to work.
- Manifest modules SHALL be side-effect-free at import time; a new
  architecture test walks each manifest module's AST and rejects
  top-level calls (other than `PluginManifest(...)`).
- New capability spec `plugin-manifest` ADDED; `surface-protocol`
  MODIFIED with the forward-looking "new Surface implementations
  register via MANIFEST" requirement.
- Remaining surfaces (connections, future auth providers, log sinks,
  code-mode tools, `expose=` validation) migrate in follow-up changes.

### Internal — Single typed request-scope bridge (`request_scope`)

Per `generalise-context-bridges` (2026-05-27):

- New `a2kit.packages.context.request_scope` (also re-exported at
  `a2kit.packages.dispatch.request_scope`) — single typed
  substrate→dispatch bridge with `publish(*values)` / `get(T)` /
  `try_get(T)` / `all_seeds()` / `reset(token)` and a typed
  `RequestScopeMissing(T)` failure mode.
- Three pre-existing per-type ContextVar bridges collapsed into this
  one shape: the `Principal` bridge (`_request_principal`), the
  FastAPI per-request `Container` bridge (`_a2kit_request_scope`), and
  the log ambient bridge (`_CallScope`). All readers and writers now
  route through `request_scope`.
- `Container.call_scope` accepts `framework_seeds=` (new) sourced from
  `request_scope.all_seeds()`. The prior `scoped_seeds=` keyword is a
  deprecation-shim alias emitting `DeprecationWarning` for one release.
- `a2kit.packages.dispatch._principal_bridge` (the
  `set_request_principal` / `current_request_principal_seeds` /
  `reset_request_principal` named API) is now a deprecation-shim
  wrapper around `request_scope.publish` / `get` / `reset`. Each
  function emits `DeprecationWarning`. New code SHOULD use
  `request_scope` directly.
- `AmbientContextMissing` is now a deprecation-shim subclass whose
  no-dispatch path chains from `RequestScopeMissing(_CallScope)` via
  `__cause__`.
- The FastAPI Depends bridge keeps reading from the DI-package-local
  `_a2kit_request_scope` ContextVar (the http middleware dual-writes
  to both bridges) to preserve `di-container-package`'s
  standalone-shippability invariant.
- New capability spec `request-scope` ADDED; `dispatch-pipeline`
  MODIFIED with the framework_seeds rename + stages-read-via-scope
  requirement.
- Adding a new request-scoped type (TenantId, TraceContext, RequestId)
  is now two lines (one `publish` at the substrate seam, one `get` at
  the reader) — zero new ContextVars, zero new bridge modules.

### Internal — Error envelope render state moved to an explicit side channel

Per `error-envelope-side-channel` (2026-05-27):

- `ErrorEnvelopeStage` no longer mutates `AppError` instances with
  `rendered_prose` / `rendered_envelope_dict` attributes. Render output
  now lives on a per-call side channel under
  `a2kit.packages.dispatch._render_state` (`RenderedError`,
  `set_rendered_error`, `get_rendered_error`, `open_render_state`,
  `close_render_state`, re-exported from `a2kit.packages.dispatch`).
- `McpErrorRenderStage` and `CliErrorRenderStage` retrieve prose +
  envelope via `get_rendered_error(exc)` instead of untyped `getattr`.
- The MCP `_pending_typed_envelope` ContextVar (a second side channel
  between `McpErrorRenderStage` and `TypedErrorEnvelopeMiddleware`) is
  retired; both readers use the unified `_render_state` slot.
- Removes the two `# ty: ignore[unresolved-attribute]` comments in
  `packages/dispatch/envelope.py`.
- No change to wire envelope shape, prose format, or CLI exit codes.

### Breaking (internal API) — Surfaces are passive; composition is explicit

Per `bootstrap-surfaces-explicit` (2026-05-26):

- Importing `a2kit.packages.mcp` / `a2kit.packages.http` no longer
  mutates any module-level registry. The self-registration blocks at
  `mcp/__init__.py:15-16` and `http/__init__.py:37-38` are deleted.
- `a2kit.compose_default_surfaces()` is the facade entry that composes
  the bundled `McpSurface` + `ApiSurface` pair and binds them as the
  active registry. `a2kit.run(app)` calls it automatically.
- `runtime.build(app, surfaces=registry)` accepts an explicit
  `SurfaceRegistry`. When omitted, validation is skipped (the legacy
  decoration-time validation no longer covers it).
- `expose=` surface-name validation moved from decoration time to
  build time. The decorator captures `expose=` unchanged; build walks
  every descriptor and raises `TypeError` listing the composed
  surfaces when an unknown name is seen.
- `SURFACE_REGISTRY` is a deprecation-shim proxy that routes through
  the active registry. `SURFACE_REGISTRY.register_surface(...)` emits
  `DeprecationWarning` pointing at `runtime.build(surfaces=...)`.
- New lint-clean public symbol `a2kit.compose_default_surfaces` (tier 1).
- New capability spec `serve-topology` ADDED; `surface-protocol`
  MODIFIED with the "surfaces are passive" requirement.

Consumer-visible test surface: if you test decoration-time `TypeError`
for unknown surfaces, switch to asserting at `runtime.build(app,
surfaces=...)` instead.

### Breaking (internal API) — Principal bridge consolidated

The per-request Principal contextvar moved out of L0
`a2kit.packages.context` into a private dispatch-layer module:
`a2kit.packages.dispatch._principal_bridge`. The raw ContextVar is
module-private; substrate adapters publish via the named writer API
`set_request_principal` / `reset_request_principal` and dispatch stages
read via `current_request_principal`. All three are re-exported from
`a2kit.packages.dispatch` for substrate-package consumers.

`_a2kit_request_principal` is no longer importable from
`a2kit.packages.context`. If you imported it directly, switch to the
named bridge API.

`auth.testing.authenticated_as` was removed — it wrapped two lines of
contextvar set/reset around the writer API. Replace with either an
inline `set_request_principal` / `reset_request_principal` block, or
the DI override pattern when an `App` is in hand
(`app.container().provide(Principal, lambda: fake)`).

### Breaking (internal API) — explicit per-call DI seeding

`Container.seed_scoped(type_, value)` is the new explicit way to
publish a typed instance on a per-call (child) container. Substrate
adapters that need to inject a SCOPED instance for one dispatch use
this; the previous implicit "values placed in `wire_kwargs` become
SCOPED providers by `type(value)`" side effect of `Container.call_scope`
is removed.

`Container.call_scope` gains a `scoped_seeds: dict[type, Any] | None`
kwarg — equivalent to calling `seed_scoped` for each entry before
`pre_hook` runs. Used by `_lift_principal_into_scope` and
`DispatchHookStage._wrapped`.

`pre_hook` signature widens from `(fn, wire_kwargs)` to
`(fn, wire_kwargs, seed)`. The third argument is a callable
`(type_: type, value: Any) -> None` that publishes typed instances on
the per-call DI child. Existing hooks must accept the third argument;
hooks that relied on the implicit wire-by-type loop must call
`seed(T, instance)` explicitly. Migration: every in-repo consumer was
migrated in this change.

### Internal — dispatch stages no longer read the Principal contextvar

Dispatch stages (`DispatchHookStage`, `AuthorizeGateStage`,
`CallScopeStage`) MUST resolve `Principal` via the per-call DI scope.
The substrate's `_a2kit_request_principal` contextvar is now read in
exactly one place: `a2kit.packages.dispatch._principal_scope`, which
seeds Principal into the per-call wire kwargs. Stage source is
grep-clean; new code in the dispatch pipeline that needs Principal
must accept it as a typed DI dependency. Tool authors and `authorize=`
callables continue to receive `Principal` by type annotation —
no consumer-side change.

### Breaking — `App.debug` attribute removed; sub-configs DI-resolvable

`App.debug` is gone. The shortcut duplicated `app.config.debug` and
fragmented the access path; ADR 0022 designates `A2kitConfig` as the
single config surface. Reading `app.debug` now raises `AttributeError`
with a migration hint.

| Pre v0.40 | Post v0.40 |
|-----------|------------|
| `app.debug` | `app.config.debug` (consumer side) |
| `app.debug` inside a subsystem | `def factory(cfg: A2kitConfig): ...` resolves via DI |
| `runtime.debug` | `runtime.config.debug` |

Added (additive on top of ADR 0022):

- `A2kitConfig`, `LogConfig`, `McpConfig`, `HttpConfig`, and `CliConfig`
  are registered as singleton DI providers on every `App`. Subsystems
  declare a typed parameter (`def factory(log: LogConfig): ...`) instead
  of walking `app.config.log.<field>`. Per-test overrides use the
  standard `app.provide(LogConfig, fake)` pattern (ADR 0006
  last-write-wins).
- `CallScopeStage` captures `LogConfig` once at wrap time (per-tool,
  per-runtime) and reads the threshold from the captured value. The
  previous per-call attribute walk on `spec.app.config.log.level` is
  retired.

Internal: `mcp/server.py` and `http/build.py` now read
`runtime.config.<sub>.<field>` directly off the typed root instead of
defensive `getattr` chains; `AppRuntime` no longer carries a `debug`
field.

### Breaking — log level threshold; default silences `debug()` calls

Adds a level-threshold filter for log emissions, configurable via
`A2kitConfig.log.level` (env: `A2KIT_LOG__LEVEL`). The default is
`info`, which means existing `debug()` calls **no longer reach any
sink, ctx.log, or stderr**. To restore prior behaviour set
`A2KIT_LOG__LEVEL=debug` (or `trace` to also see internal dispatch
traces).

Other breaks bundled into this change:

- The legacy `A2KIT_LOG__ENABLED=false` kill-switch env var is removed. It
  collided with the new `A2KIT_LOG__*` namespace (pydantic-settings
  parses `A2KIT_LOG` as JSON for the nested model). Replacement:
  `A2KIT_LOG__ENABLED=false` (orthogonal to `level` — a hard off).
- `event(name, **fields)` and `report(payload)` gain a keyword-only
  `level` parameter (default `"info"`). Calling them positionally is
  unaffected. Hand-rolled subclasses or wrappers that proxy these
  signatures need to thread `level` through.
- `a2kit.log.log()`'s `__level` literal widens to include `"trace"`
  alongside the existing `debug | info | warning | error`. Callers
  using `log("trace", ...)` now have a valid level below `debug`.

Added:

- `A2kitConfig.log.level: Literal["trace","debug","info","warning","error"]`
  (default `info`). Env: `A2KIT_LOG__LEVEL`.
- `A2kitConfig.log.enabled: bool` (default `True`). Env: `A2KIT_LOG__ENABLED`.
- `a2kit.log.LOG_LEVEL_NUMBER` — numeric rank map (`trace=10`, `debug=20`,
  `info=30`, `warning=40`, `error=50`) exposed for sink authors and tests.
- `a2kit.log.LogLevel` — re-export of the level Literal alias.
- README config table rows for `A2KIT_LOG__LEVEL` and `A2KIT_LOG__ENABLED`.
- AGENTS.md provider-chain block lists log as a worked example, with the
  "if every emission is the same level, the level isn't doing work" smell.

### Breaking — `App(debug=...)` kwarg removed (ADR 0022 worked example)

Debug is a consumer-owned concern per ADR 0022 (provider-chain config
model). The kwarg locked consumers out of disabling debug at deploy
time, which is the anti-pattern ADR 0022 forbids.

Set debug via env `A2KIT_DEBUG=true` or via the new
`A2kitConfig(debug=True)` instance passed to `App(name, config=...)`.

The `App.debug` *attribute* is preserved (it proxies `app.config.debug`),
so external code reading `app.debug` keeps working. Only the *write API*
(the kwarg) is gone. Loud failure: passing `debug=` raises `TypeError`
with a migration hint.

Bundled with this:

- `A2kitConfig.debug: bool = False` added as a top-level field.
- README gains `## Configuration` documenting the precedence chain
  (env > .env > kwarg > default), the `A2KIT_<SUBSYSTEM>__<KNOB>`
  convention, and worked examples (`A2KIT_DEBUG` +
  `A2KIT_MCP__STRUCTURED_OUTPUT`).
- AGENTS.md gains "Provider-chain configuration" pattern block.
- ANTIPATTERNS.md gains entry #29 — hard-coding consumer concerns in
  `App()` construction.
- `operational-contracts` spec scenarios reworded from `App(debug=True)`
  to `app.config.debug == True` (behavior unchanged).

### Added — CLI `--json` flag (end-to-end machine channel)

Every per-tool CLI subcommand gains `--json`. Success emits compact
`model_dump()` JSON to stdout; error emits the typed envelope to stdout
in the same shape as MCP `structuredContent.error` and the HTTP body.
Stderr stays silent in both. Exit code is kind-mapped per sysexits.h.
Mutually exclusive with `--format` — passing both raises `BadParameter`.

Closes the prose-only-on-error asymmetry that made CLI the odd transport.
Now `a2kit <subcmd> <tool> --json | jq` works end-to-end.

Implementation: `_cli_json_mode` ContextVar set per-invocation;
`CliErrorRenderStage` reads it on the error path; `invoke_tool_sync_raw`
is the success-path sibling that bypasses the formatter pipeline. Carried
over from a2effect-foundation task 16.3 (deferred at the time).

### Added — multiplexed `serve --transport=http`

`serve --transport=http` is now a multiplexed server: one process, one
port, an a2kit-owned parent ASGI app that mounts each surface as an
independent sub-app — the MCP streamable-HTTP surface under `/mcp`, a
minimal REST surface (health route + OpenAPI document) under `/api`.

- New `serve` flags `--mcp-only` / `--rest-only` select a single
  surface; mutually exclusive, both default off (= all surfaces on).
  `--rest-only` requires `--transport=http`.
- The `App` lifecycle is owned by the parent app — a single `async
  with app:` spans the process; each mount carries only its
  transport-scoped lifespan.
- uvicorn becomes a runtime dependency, imported only on the
  `serve --transport=http` path (never at `import a2kit`).

**BREAKING (wire path).** Under `--transport=http` the MCP endpoint
moves from the FastMCP default root to `/mcp`. HTTP MCP clients must
target `http://host:port/mcp`. Local stdio `serve` is unchanged.

### Removed — dead surface (BREAKING)

Seven minor releases of fast pre-1.0 iteration left dead weight in
`src/a2kit/`. This change removes it and the things carried solely to
support it:

- **`a2kit.packages.select`** — the entire CEL-filtering package
  (~218 SLOC) is deleted. It had zero callers and was never wired to
  any CLI or MCP flag. The `cel-python` runtime dependency, which
  existed only for this package, is dropped from `pyproject.toml`.
- **`App.tool_descriptors()`** — removed. It was a deprecated alias
  for `App.tools()` with zero callers; `App.tools()` is the single
  tool-introspection API.
- **`ListViewMode` / `Local` / `Passthrough`** — the formatter enum
  and its module-level aliases are removed from
  `a2kit.packages.formatter`. They were defined and re-exported with
  no consumer.
- The `InvalidFilterExpression` exception (CEL-filter-specific) is
  removed from `a2kit.exceptions`.

Non-breaking internal cleanup also lands: the `lint.run_runtime` /
`lint.run_static` bare aliases collapse to `run_runtime_checks` /
`run_static_rules`; the unread `ToolBuildSpec.descriptor` field and
four discarded `StderrToolContext.__init__` compat parameters are
removed; the orphaned `codemode.run_code` import tombstone is deleted
(the `codemode` package never shipped that path). See ADR 0017 area /
the `remove-dead-surface` change.

### Changed — one public `App`, finishers seal (BREAKING)

`a2kit.App` is the single public type — the mutable composition surface
and the runtime in one. It is constructed directly, wired with the
composition verbs (`add_router`, `add_cli`, `add_mcp_middleware`,
`provide`, `health_check`), and handed to a finisher (`a2kit.run`,
`build_mcp_server`, `a2kit.testing.client`). The finisher seals the App
internally — validates the DI provider graph, locks the container —
before running, serving, or testing. There is no public `build()` and
no separate runtime type. See ADR 0017 (supersedes ADR 0016).

**Breaking.** The short-lived `a2kit.AppBuilder` split (also unreleased)
collapses back to one type:

| before                                     | after                             |
|--------------------------------------------|-----------------------------------|
| `builder = a2kit.AppBuilder("svc")`        | `app = a2kit.App("svc")`          |
| `builder.add_router(r)` / `provide` / ...  | `app.add_router(r)` / ...         |
| `app = builder.build()`                    | (drop the line — a finisher seals)|
| `install_connections(builder, ConnT)`      | `install_connections(app, ConnT)` |

`a2kit.AppBuilder` no longer exists; the public `build()` is removed. A
composition verb after a finisher has sealed the App raises `TypeError`.
The pytest fixture in `a2kit.packages.testing` is named `app` and yields
a fresh `a2kit.App("test")`.

The DI test-override seam is **removed**: `TestClient.override(T, fake)`,
`Container._override` / `_snapshot` / `_restore`, and
`App._test_override_owner` no longer exist. Test overrides are re-build —
construct a fresh `a2kit.App` and `provide` the fake last
(last-write-wins). `TestClient.override` raises a migration hint. This
reconciles the code with ADR 0006, whose Y-statement always said there
is no override after the container seals. `Container.seal()` is the seal
point; the finishers reach it via the internal `App._seal()`.

### Changed — shared dispatch pipeline

The per-tool dispatch concerns are now a single transport-neutral
pipeline. `a2kit.packages.dispatch` holds `DISPATCH_PIPELINE` — six
`DispatchStage` objects (timeout, enrichers, router-lazy-enter,
dispatch-hook + DI, log ambient, error-capture) — and both the CLI and
MCP adapters fold the same tuple. The package imports no `fastmcp`, so
the CLI cold path is unaffected.

Previously each transport carried its own copy of these five concerns;
the two had already drifted (two timeout mechanisms) and the CLI was
missing router-lazy-enter entirely. **Bug fix:** a router carrying
`__aenter__` now enters on first CLI dispatch, matching MCP.

Error handling is split into a neutral capture stage (exception ->
`CapturedError`) and a per-transport render stage — `ToolError` JSON for
MCP, an `error:` stderr line plus non-zero exit for the CLI. Internal
refactor; tool-author-facing behaviour is unchanged apart from the
router-lifecycle fix.

### Changed — import-graph acyclicity

The `src/a2kit/` import graph is now a directed acyclic graph. Three
package cycles — `cli ↔ mcp`, `mcp ↔ codemode`, and the
`TYPE_CHECKING`-only `app ↔ health` — were broken structurally
(relocation and parameter inversion), not by deferring imports into
function bodies. `mcp/_wrappers.py` is now typed against the real
`App` / `Router` types instead of `Any`.

**Breaking.** Three internal import paths moved; each old path raises
with a migration hint:

| before                                                      | after                                                                                       |
|-------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| `from a2kit.packages.cli.context import StderrToolContext`   | `from a2kit.packages.context import StderrToolContext` (transport-neutral, not CLI-specific) |
| `from a2kit.packages.codemode import run_code`               | `run_code` is CLI-owned (`a2kit.packages.cli`); the CLI `code` subcommand calls it directly  |
| `run_checks(app)`                                           | `run_checks(registry, resolver, *, version=...)` — takes a `Resolver`, never an `App`        |

`StderrToolContext` and `MCPOnlyError` are behaviourally unchanged —
only their home package moved.

### Added — bundled code-execution surface

a2kit MCP servers now expose a sandboxed code-execution surface by
default — FastMCP's `experimental` `CodeMode`, adopted via the new
`A2kitCodeMode` transform (`a2kit.packages.codemode`). `list_tools`
collapses to three meta-tools (`search`, `get_schema`, `execute`);
agent-authored Python runs in a Monty sandbox where
`call_tool(name, params)` reaches every permitted tool, carrying
a2kit's per-call connection scope and DI unchanged. The same surface
is exposed on the CLI as a global `code` subcommand — registered only
when the `a2kit[code-mode]` extra is installed, so a lean CLI install
carries no sandbox dependency.

Capability-gated: tools flagged `destructive` are absent from the
sandbox catalog unless the operator passes
`--code-mode-allow-destructive`; the agent cannot self-grant. Never
exposed on the (future) REST surface. The Monty runtime
(`pydantic-monty`) is a lazy optional dependency — install with
`a2kit[code-mode]`; `import a2kit` never pays for it.

See ADR 0013, `docs/VISION.md`, and `docs/SPIKE_CODE_EXEC_DI.md`.

**Breaking.** Code execution is default-on, and installing it
collapses the listed tool catalog. Consumers that enumerate
`list_tools` see only `search` / `get_schema` / `execute` until they
adopt code mode or opt out. Real tools stay callable by name.

Migration table:

| before                                       | after                                                       |
|----------------------------------------------|-------------------------------------------------------------|
| `build_mcp_server(app)` lists the full catalog | pass `build_mcp_server(app, code_mode=False)` to keep it listed |
| `serve` exposes every tool in `list_tools`   | `serve --code-mode-off` disables the code-execution surface  |
| sandbox must reach `destructive` tools       | `serve --code-mode-allow-destructive` (operator-side grant)  |

### Changed — consumer-aware format routing

Rendering is now a function of `(value, consumer)` — the new `render`
seam in `a2kit.packages.formatter`, with consumer profiles `llm`
(compress: TSV / page-tsv), `code` (structured dataclasses for the
sandbox), and `machine` (plain JSON). The `code_mode` build flag fixes
the consumer at `build_mcp_server` time — no runtime sniffing.

The MCP surface now format-routes tool results, closing a gap where it
shipped raw JSON while the CLI compressed: a tabular result is emitted
as TSV / page-tsv in the MCP `content` channel, with the equivalent
JSON in `structuredContent` (spec-aligned per MCP SEP-1624). A new
`build_encoding_plan` additionally compresses flat-array fields nested
inside a `BaseModel` envelope, not just top-level lists / `Page`.

Code mode gains a real sandbox runtime: `call_tool` marshals results
into the monty sandbox as dataclasses (attribute access —
`page.items[0].title`), the `A2kitSandboxProvider` type-checks
LLM-authored code against stubs generated from the tool descriptors
before executing it (retrying once via sampling on a type error), and
the `execute` output is rendered for the LLM by value-driven
inference. See ADR 0014 and `docs/SPIKE_CODEMODE_MARSHALLING.md`.

**Breaking.** The MCP `content` shape changes: a tabular tool result
that previously arrived as raw JSON in `content` now arrives as TSV /
page-tsv. MCP clients that parsed `content` as JSON must read
`structuredContent` (the equivalent JSON, unchanged) or parse the
compressed form.

Migration table:

| before                                          | after                                                          |
|-------------------------------------------------|----------------------------------------------------------------|
| parse a tabular result's `content` as JSON      | read `structuredContent`, or parse the TSV / page-tsv `content` |
| a non-conformant client mishandles dual channels | `serve --compact` drops `structuredContent`, leaving `content` only |

### Changed — tidy: format-routing review follow-ups

Internal cleanup following a `/simplify` review of the consumer-aware
format-routing work:

- The dead `format_hint="toon"` `ValueError` guard in `format_response`
  is removed — the `FormatHint` type (`auto` / `json` / `tsv` /
  `page-tsv`) already forbids the value, so no type-checked caller could
  reach it. TOON is now fully retired from code and specs.
- `A2kitCodeMode` caches the per-`execute` catalog → stubs → dataclass
  registry derivation, keyed on the resolved tool-name set, instead of
  rebuilding it on every `execute` call.
- `FormatHint` / `FormatName` move to a leaf module
  (`a2kit.packages.formatter.formats`); both are still re-exported from
  `a2kit.packages.formatter` unchanged. `Rendered.format` and
  `Response.format` are now typed `FormatName`, not bare `str`.
- New lint rule `A2K-PKG-INIT-IMPORT`: a submodule may not import from
  its own package's `__init__`, preventing the latent import cycle the
  leaf-module move above resolves.

No API change for type-checked callers; no dependency change.

## v0.39.3 — 2026-05-19

Patch release addressing a2web round-11 feedback. One additive
testing helper plus a small doctrine refinement. No behaviour
changes outside the new fixture; no wire-format changes.

### Added — `a2kit.testing.ambient_for_tests_autouse`

Pre-decorated autouse peer of `a2kit.testing.ambient_for_tests`.
Consumers wanting project-wide ambient binding now write a single
`from a2kit.testing import ambient_for_tests_autouse` in
`conftest.py` instead of the three-line `__wrapped__` re-export
pattern. Both flavors share defaults (`events_enabled=False`,
`reports_enabled=False`, `ctx=null_context()`); the only difference
is the framework-level `autouse=True` decoration. Decision rule:
project-wide binding → `_autouse`; per-test opt-in → bare fixture.
The historical `__wrapped__` re-export remains valid and is
documented in `OPERATIONAL_CONTRACTS.md` for consumers already on
it. Addresses a2web `A2KIT_FEEDBACK_v0.39.md` Note 1.

### Changed — `CONSUMER_FEEDBACK_DOCTRINE.md` names the misdiagnosis taxonomy

Under C3, a short "Known misdiagnosis shapes" subsection names
**Shape A3** ("right primitive, wrong use case") and **Shape E**
("correct design mistaken for accidental ceremony") so future
filings can pattern-match against recurring patterns. The filing
template's misdiagnosis self-check gains an optional one-line shape
hint. No substantive rule change — the F2 / C2 worked examples that
landed in v0.39.2 already covered the substance; this round just
names the patterns.

### Declined

- a2web round-11 Carry-over C (canonical surface promotion of
  `a2kit.Lazy` / `a2kit.logging.LogRecord`) and Carry-over D
  (`pydantic.Field` description sugar) remain parked in
  `A2KIT_WISHES_DEFERRED.md` entries 7 and 8 — no fresh signal
  this round.

## v0.39.2 — 2026-05-18

Docs, examples, and CI-coverage release. No a2kit source changes, no
behaviour changes, no wire-format changes. Patch release.

### Added — three ADRs locking the MCP auth boundary

- **ADR 0010** (proposed): authentication is an MCP-mode concern
  only; the CLI never authenticates. a2kit core, the CLI transport,
  and tool bodies stay auth-agnostic. Recorded consequence: AI
  agents that only speak remote MCP (ChatGPT custom connectors,
  Claude web, Gemini web, hosted Desktop variants) cannot reach
  CLI-only operations — the answer is to lift the operation as an
  MCP verb, not retrofit auth into the CLI.
- **ADR 0011** (proposed): prescribed FastMCP auth recipe.
  `GoogleProvider` with Fernet-wrapped filesystem `py-key-value`
  store, a stable `jwt_signing_key` from env, a `StaticTokenVerifier`
  bearer escape hatch, Streamable HTTP transport, and a GCP "Testing"
  consent screen for beta gating. Self-hosted-OIDC sub-recipe
  documented as the named deviation. Encodes the pitfalls (in-memory
  storage, missing `jwt_signing_key`, Testing-mode 7-day token expiry,
  DCR-incompatible clients).
- **ADR 0012** (proposed): MCP deployment topology — one OAuth app
  per server, no gateway. Records why current MCP gateway projects
  (MetaMCP, mcp-context-forge, MCPJungle, et al.) are not ready for
  the "one Google login fronts N MCPs" use case without operating a
  real IdP, and names the Authelia-in-front-of-Google anti-pattern.
  Re-evaluation triggers: server count > 3, gateway-ecosystem
  maturity, or a multi-tenant use case landing.

### Added — remote-MCP-access pattern doc

`docs/patterns/remote-mcp-access.md` documents the canonical shape
for an a2kit-based remote MCP serving web-only AI clients with
Google auth: per-user `UserSession` via per-call DI, workspace dirs
named by `sha256(email)[:16]` (raw email never in the path, `_email`
forensics file written on first creation), and a four-category
liftability rubric (lift / lift-with-care / don't-lift / never-lift)
for deciding which operations belong in a remote MCP at all.
Composes existing a2kit primitives only — no new framework code.

### Added — `examples/mcp_google_auth/` lintable reference

End-to-end implementation of the ADR 0011 recipe and the pattern
doc. Three verbs (`whoami`, `note_write`, `note_read`) over per-user
workspace directories, two composition roots (CLI for local dev,
MCP for production), and a smoke test that exercises the per-user
workspace contract through a2kit's in-process test client. Runs in
~1 second. `make example-smoke` and the CI workflow now run the
smoke test on every commit, so a2kit-side changes that break the
recipe fail at the framework boundary before reaching downstream
consumers. Google-mode dependencies (`py-key-value-aio[disk]`,
`cryptography`) live in the new `examples-mcp-google-auth` optional
group; bearer-only mode (used by the smoke test) needs neither.

### Added — `make example-smoke` and CI step

`make example-smoke` runs the example's smoke suite with a default
`WORKSPACE_ROOT` of `/tmp/a2kit-example-smoke`. The GitHub Actions
workflow invokes it alongside `pytest`. The example is also covered
by `make lint` (ruff, ty, a2kit lint static) and `make typecheck`.

## v0.39.1 — 2026-05-18

Documentation and governance work. No code changes, no behaviour
changes, no wire-format changes. Patch release.

### Added — deterministic ADR pipeline

ADRs now carry YAML frontmatter validated against
`docs/adr/schema.json` (status enum, dates, supersession, tags,
deciders). `docs/adr/INDEX.md` is auto-generated by
`scripts/adr_index.py` from that frontmatter and is the agent-loadable
entry point for the decision log (id + status + title + tags +
Y-statement, ~hundreds of tokens total). Pre-commit blocks any commit
where frontmatter is invalid or the INDEX is stale. The pipeline
is thin orchestration over `python-frontmatter`, `jsonschema`, and
`jinja2`; no bespoke YAML or markdown parsing. See ADR 0007 for the
system design rationale.

### Added — consumer feedback doctrine

`docs/CONSUMER_FEEDBACK_DOCTRINE.md` documents F1-F5 (framework
rules) and C1-C4 (consumer rules) for triaging feedback filings and
re-validating capabilities on adoption. CHANGELOG entries and ADRs
are the framework's primary response media; no per-round response
files in the framework repo. Adopted by ADR 0005. The
`docs/feedback-responses/` directory introduced in v0.38 has been
removed.

### Added — new ADRs

- **ADR 0004**: Package layout — tiered surfaces by audience size
  (a2kit.* / a2kit.<domain> / a2kit.packages.*). Citable when
  declining "promote X to top-level" filings.
- **ADR 0005**: Adopt framework⇄consumer feedback doctrine.
  Citable when declining filings that ignore the misdiagnosis
  self-check (C3) or that ask for per-round response logs.
- **ADR 0006**: No dedicated `app.override(T, fake)` test seam.
  Backfill — the rationale for composition-root re-registration as
  the canonical test override path.
- **ADR 0007**: ADR system design — frontmatter, auto-INDEX, no
  static site. Records the *why* behind the ADR pipeline this
  release ships.
- **ADR 0008**: `Lazy[T]` for conditional dependencies, not
  `await app.resolve(T)`. Backfill — the rationale for declarative
  conditional-dependency declaration via signature.
- **ADR 0009**: `per_call=True` resource scoping over explicit
  `async with` in tool body. Backfill — the rationale for uniform
  DI-managed lifecycle across resource scopes.

### Added — AGENTS.md + slim CLAUDE.md

`AGENTS.md` at the repo root carries all tool-agnostic agent
conventions (core principles, patterns, anti-patterns, workflow,
architecture strategy, project state hooks). Loaded automatically
by Claude Code, Cursor, Codex, Aider, and other AGENTS.md-aware
coding agents. `CLAUDE.md` slimmed to a Claude-specific overlay
(auto-memory hygiene, loading-priority guidance). If the two files
disagree on tool-agnostic rules, AGENTS.md is canonical.

### Added — pre-commit framework + markdown lint

`pre-commit` is now a dev dep and `make bootstrap` installs the
hooks. `pymarkdownlnt` lints `docs/`, `CHANGELOG.md`, `README.md`,
and `AGENTS.md` / `CLAUDE.md`; config in `.pymarkdown.json`. New
Makefile targets: `make adr-index`, `make adr-check`,
`make markdown-lint`.

### Added — BACKLOG.md

Active queue of deferred work, each item parked with its trigger
condition. Replaces ad-hoc tracking. Historical design notes remain
in `todo.md`; shipped work in this CHANGELOG and `docs/adr/INDEX.md`.

### Removed — `docs/feedback-responses/`

The per-round response log introduced in v0.38 has been removed.
Per ADR 0005 / doctrine F1, framework responses live in this
CHANGELOG (for shipped capabilities), in ADRs (for class-declines),
or in the originating conversation (for one-off declines). The
framework repo no longer mirrors any one consumer's round cadence.

## v0.39.0 — 2026-05-16

Round-10 a2web feedback wave: six frictions shipped + one
architectural cleanup. The headline is **ambient `ctx` is now
non-None inside any framework dispatch** (drop the `del ctx`
ceremony) and **`a2kit.ToolContext` is now an a2kit-owned
Protocol** (the implicit `fastmcp.Context` contract is now
explicit). Three testing helpers (`a2kit.testing.lazy`,
`ambient_for_tests`, `resolve`) delete consumer `conftest.py`
boilerplate. `Lazy[T]` recognition extended from tool params
to factory params (spec drift closed). The `@app.health_check`
resource-entry contract is now pinned in `OPERATIONAL_CONTRACTS`.

### Changed — `a2kit.ToolContext` is now a Protocol

`a2kit.ToolContext` is no longer a lazy re-export of `fastmcp.Context`; it
is an a2kit-owned `@runtime_checkable typing.Protocol` declared in
`a2kit._context_protocol`. The Protocol names the cross-transport contract
(log family, `report_progress`, `request_id`, `client_id`, `elicit`,
state-store methods); concrete implementations satisfy it structurally —
`fastmcp.Context` under MCP, `StderrToolContext` under CLI, future
transports plug in without subclassing.

Identity change: `a2kit.ToolContext is fastmcp.Context` is now `False`
(previously `True`). Consumer code annotating `ctx: a2kit.ToolContext`
continues to work unchanged — both impls satisfy the Protocol. Tools
needing MCP-only methods (`sample`, `list_resources`, `send_notification`)
should annotate `ctx: fastmcp.Context` directly.

The MCP wrapper rewrites the ctx parameter annotation in the generated
signature/annotations to `fastmcp.Context` before FastMCP schema
generation (pydantic cannot schema-generate Protocols). Cold-start
budget preserved — the Protocol lives in a2kit; bare `import a2kit`
still leaves `fastmcp` absent from `sys.modules`.

Companion: `bind_call_scope(ctx=...)` parameter is now typed
`ToolContext` (was `Any`). Static type checkers reject
`bind_call_scope(ctx=None)`; the runtime Mode B raise remains a
defense-in-depth backstop for code paths that bypass typing.
`StderrToolContext` now exposes `request_id` (per-instance UUID4 hex)
and `client_id` (`None` on CLI) so it structurally conforms to the
Protocol.

### Changed — log primitives work without `ctx` in tool signature

Closes a2web round-10 Friction B. The MCP wrapper now synthesizes a
`_a2kit_ctx` parameter into the rewritten signature for every tool
whose body does not declare `ctx`, so FastMCP injects ctx
unconditionally and a2kit extracts it for ambient binding. The CLI
runtime mirrors the change: `StderrToolContext()` is synthesized for
ambient binding even when the tool body doesn't declare ctx. Result:
**ambient `ctx` is non-None inside any framework dispatch**, and log
primitives no longer raise `AmbientContextMissing.MODE_MISSING_CTX_PARAM`
from a dispatched tool body.

Consumers can drop `ctx: a2kit.ToolContext` parameters from tools
that didn't actually use ctx in the body. The `del ctx` ceremony
is gone.

`MODE_MISSING_CTX_PARAM` constant is retained for backward
compatibility but is now unreachable from framework code paths. The
raise still fires for external misuse: manually entering
`bind_call_scope(ctx=None)` and then calling an log primitive
preserves the loud-fail (this is the only documented misuse path).

Why this aligns with log: log = Log-Driven Development. The primary
audience for log output is a post-hoc reader (an AI agent diagnosing
what happened from structured logs), not a live wire observer. Sink
emission is the core value; wire emission is the secondary live-UX
nicety. Gating sink emission on wire-side availability was incidental
complexity; removing that gate aligns behavior with intent.

Companion: `_wrap_with_dispatch_hook` now preserves the original
function's return annotation in the rewritten signature
(`__signature__.return_annotation` + `__annotations__["return"]`).
Previously this was set only on `__annotations__`, which the
PEP 362 path skips when `__signature__` is present — masked by the
prior early-exit for tools without DI injectables; surfaced now that
the wrapper runs for ctx-synthesis even on those tools.

### Added — `a2kit.testing` helpers

Three helpers ship to delete boilerplate every consumer's
`conftest.py` reinvents (per a2web round-10 feedback Friction A1,
A2, and A3):

- `a2kit.testing.lazy(value)` — wrap a pre-built fake into the
  `Lazy[T] = Callable[[], Awaitable[T]]` shape used at the tool
  seam. One-liner factory; thunk yields the original value by
  identity on every call. Useful for injecting fakes through DI
  override into tools that declare `browser: Lazy[BrowserPool]`
  etc.
- `a2kit.testing.ambient_for_tests` — pytest fixture that
  establishes an log ambient with events + reports disabled so
  tests calling orchestrator or phase functions directly
  (bypassing `TestClient.invoke`) don't trip
  `AmbientContextMissing`. Opt-in (not autouse-by-default);
  consumers wanting project-wide ambient re-export under
  `autouse=True` in their own `conftest.py`. Preserves the
  loud-by-default contract outside opt-in tests.
- `a2kit.testing.resolve(app, T)` — async sibling of `peek`. Runs
  the full DI resolution chain on the app's container: builds T
  via the registered factory, chain-resolves constructor params,
  enters `__aenter__`, records cleanup on the appropriate scope's
  stack. Subsequent calls return cached instances per scope.
  Call inside `async with app:` or
  `async with a2kit.testing.client(app):` so cleanups have a
  scope. Collapses consumer-side `make_default_state(...)` helpers
  to a one-liner.

Consumers of the prior hand-rolled patterns (e.g. a2web's
`conftest.py` lines 34-45, 48-68, and 71-79) can delete those
helpers.

### Clarified — `@app.health_check` kwargs enter resources

The health-probe path has always routed kwargs through the v0.36
DI resolver (`Container.resolve_params` → `_construct` →
`_enter_lifecycle`), entering resources via `__aenter__`. The
contract lived only in the `_run_one_check` docstring; it now ships
as `OPERATIONAL_CONTRACTS.md` Q-HealthChecks with a pinning test
(`tests/test_health_check_resource_entry.py`).

No behaviour change. Consumers calling
`await sqlite._ensure()` (or any other internal "ready" method)
inside a health-check body can drop those calls — the resource is
already entered.

Important nuance: for singleton resources (the default), enter fires
exactly once across the app's lifetime and exit fires at app
shutdown, NOT per probe. The probe receives a ready resource; it
isn't necessarily the call that entered it.

(Per a2web round-10 feedback Friction F. No new API surface —
`Resource.warm_up()` was considered and rejected as redundant with
the existing `__aenter__` contract.)

### Fixed — `Lazy[T]` honored in factory parameters

`di-conditional-injection` spec promised `Lazy[T]` recognition for
**both** tool and factory parameters; the implementation only
honored tool dispatch (`Container.resolve_params`). Factories
declaring `Lazy[T]` raised `UnresolvableType` at first resolution.
This release closes the drift:

- `Container._construct_kwargs` now recognises `Lazy[T]` and
  injects the same deferred closure as the tool-dispatch path.
- The scope-graph validator (`Container._validate_scope_graph`)
  gains a mirror guard rejecting SINGLETON factories that declare
  `Lazy[per-call-T]` parameters — the captured closure would
  resolve per-call types on root and silently break per-call
  semantics. Error raised at `async with app:` with a migration
  hint pointing at the two valid alternatives (move inner to
  app-scope, or make the outer factory per-call).

Enables aggregates like `AppState` to carry `Lazy[BrowserPool]`
fields built via DI; tool signatures collapse from three
injectables (`state`, `browser_pool`, `llm_extractor`) to one
(`state`). Per a2web round-10 feedback Friction E.

## v0.38.0 — 2026-05-15

The pre-v0.36 DI surface on `Container` is retired. The new path
(`provide` / `get` / `dispatch` / `has_provider`) — shipped in v0.36
and routed through production dispatch in v0.37 — is now the only
non-erroring path. Legacy methods raise `TypeError` with migration
hints; container state is unified on the v0.36+ shape.

### Breaking — legacy DI methods raise `TypeError`

| Removed                                   | Replacement                                                                                          |
|-------------------------------------------|------------------------------------------------------------------------------------------------------|
| `Container.register(T, factory)`          | `Container.provide(T, factory)`                                                                      |
| `Container.register_singleton(T, factory)`| `Container.provide(T, factory, scope=Scope.SINGLETON)`                                               |
| `Container.resolve(T)` (sync)             | `await Container.get(T)` (async; honors `__aenter__` and cleanup)                                    |
| `Container.aresolve(T)`                   | `await Container.get(T)`                                                                             |
| `Container.has(T)`                        | `Container.has_provider(T)`                                                                          |
| `Container.has_async_singleton(T)`        | (removed; `provide(scope=SINGLETON)` accepts both sync and async factories)                          |
| `Container.has_any_async_singletons()`    | (removed; async vs sync factories are not distinguished at registration)                             |

### Internal

- `_async_factories` / `_async_singleton_locks` / `_UNRESOLVED` sentinel
  removed from `Container`. `_singletons` is now the canonical app-scope
  cache: absent key = not yet built (lazy first-use).
- `_resolve_factory_kwargs` / `_aresolve_factory_kwargs` deleted.
- `a2kit.testing.peek` switches from the retired sync `resolve` to
  driving `Container.get` via `asyncio.run` (sync context) or reading
  the app-scope cache (inside a running loop).

## v0.37.0 — 2026-05-15

Production dispatch sites (MCP transport + CLI runtime) now route every
tool call through `Container.dispatch` — so per-call scope and `Lazy[T]`
land on the real wire, not just direct-API use. The dispatch hook
contract narrows to wire-side resolution only.

### Breaking — dispatch hook contract narrowed

| Removed                                       | Replacement                                                                  |
|-----------------------------------------------|------------------------------------------------------------------------------|
| `a2kit.tool.identity_dispatch_hook`           | No-op default — when no hook is installed, `Container.dispatch` runs without a `pre_hook` argument |
| Hook returns full DI-resolved kwargs          | Hook returns wire-side resolved kwargs only (e.g. `connection: str` → typed `ConnectionConfig` instance). Framework runs `Container.resolve_params` after the hook on its output |
| `app._dispatch_hook → container.apply_kwargs` | `app._resolver.dispatch(fn, kwargs, pre_hook=hook)` opens a per-call child container, calls the hook, runs DI (`Lazy[T]` aware), unwinds per-call cleanup on exit |
| `app._dispatch_hook` returning a dict from a sync apps without connections | All dispatch now async — one child container per call. The sync fast-path is removed |

Apps that defined a custom dispatch hook returning DI-resolved kwargs
MUST split the work: the hook does wire-side conversion only, and the
framework's `Container.dispatch` runs DI after on the hook's output.

### Breaking — connection-coupled providers default to per-call

| Before                                               | After                                                                       |
|------------------------------------------------------|-----------------------------------------------------------------------------|
| `install_connections(app, Cfg)` + `app.provide(Store)` | `install_connections(app, Cfg)` + `app.provide(Store, per_call=True)` if `Store.__init__` takes `Cfg` (or any other per-call type) — the scope-graph validator rejects app-scope factories depending on per-call types |

Connection configs are inherently per-call (each dispatch can target a
different connection), so `install_connection_dispatch` now registers
them as `Scope.SCOPED` stub providers. Stores that take a connection
config as a parameter inherit per-call semantics.

### New — `Container.dispatch` grows `pre_hook` parameter

`Container.dispatch(fn, wire_kwargs, *, pre_hook=None)` is the per-call
dispatch async context manager. The `pre_hook` (sync or async) runs
before DI to convert wire kwargs into typed values; wire-resolved
typed instances are seeded as SCOPED providers on the per-call child
container so chain resolution from any factory finds them. Used by
both `mcp/server.py::_wrap_with_dispatch_hook` and
`cli/runtime.py::_invoke_tool_in_process`.

### New — `Lazy[T]` is now wire-aware

`wire_input_params` filters `Lazy[T]` annotations out of the wire
surface — MCP schema gen no longer tries to JSON-schematize a
`Callable[[], Awaitable[T]]`. Tools declaring `Lazy[T]` work
transparently on real MCP and CLI transports.

---

## v0.36.0 — 2026-05-15

DI is rebuilt as a standalone-shippable container with lazy first-use,
per-call scope, and `Lazy[T]` for conditional injection. The `singleton`
surface retires; `provide` is the single registration API.

### Breaking — DI registration surface unified on `provide`

| Removed                                | Replacement                                                                 |
|----------------------------------------|-----------------------------------------------------------------------------|
| `app.singleton(...)`                   | `app.provide(...)` — same three call shapes plus `per_call=True` opt-in     |
| `app.has_singleton(T)`                 | `app.has_provider(T)`                                                       |
| `app.singletons()`                     | `app.providers()`                                                           |
| Eager singleton entry at `async with app:` | Lazy first-use: resources enter on first `Container.get(T)` (i.e. first dispatch that needs them) |
| `aclose` / `close` cleanup auto-detection | Single-protocol convention: only `__aenter__`/`__aexit__` is honored. Wrap `aclose`/`close` resources in a class with `__aenter__`/`__aexit__` or use `@asynccontextmanager` |
| Topological-order singleton entry      | Insertion-order via the per-scope cleanup stack; LIFO unwind                |
| `_ensure()` lazy-init pattern          | Register the resource with `app.provide(T)`; its `__aenter__` enters lazily on first resolution |
| `ctx.get(T)` service-locator           | Declare `Lazy[T]` as a tool param; deferred resolution without the antipattern |

Each removed method raises `TypeError` with the migration recipe
embedded; no aliases, no `DeprecationWarning`, no transitional period.

### New — `Lazy[T]` for conditional dependency injection

`a2kit.packages.di.Lazy[T]` is `Callable[[], Awaitable[T]]`. A parameter typed
`Lazy[T]` receives a zero-arg async closure that, when awaited,
resolves `T` through the current scope's resolver and records cleanup.
Never awaited = `T` is never constructed and its `__aenter__` never
runs. Solves the "five-resource tool only uses one" problem without
service-locator antipatterns.

### New — per-call scope via `per_call=True`

`app.provide(T, factory, per_call=True)` opts a registration into the
per-call scope: a fresh instance is built per dispatch, cached within
that one call only, and cleaned up at call exit. Default
`per_call=False` is app-scope.

### New — standalone-shippable DI package

`src/a2kit/packages/di/` is now self-contained (zero `from a2kit.*`
imports outside the package) and exposes `Scope`, `Resolver` protocol,
`Container`, `CleanupStack` ready for extraction to a standalone PyPI
package. `App._resolver` is typed as the `Resolver` protocol so
consumer code only sees the four-method surface (`get`, `provide`,
`child`, `aclose`).

### New — `Container.dispatch(fn, wire_kwargs)` helper

Async context manager for the per-call dispatch path: opens a child
resolver, calls `resolve_params(fn)` (Lazy[T]-aware), yields merged
kwargs, unwinds per-call cleanup on exit with exception preservation.
Production wiring into MCP transport and CLI runtime ships with the
a2web migration.

### New — `pydantic_settings.BaseSettings` auto-resolution

A tool parameter typed as a `BaseSettings` subclass auto-resolves
without explicit `provide()` registration — the container duck-types
the subclass check (no `pydantic_settings` import inside the container
module) and zero-arg-constructs at first use, picking up env values
via pydantic's standard machinery.

---

## v0.35.0 — 2026-05-14

This release combines the never-tagged v0.34 wave (MCP wire-error
envelope + ctx-binding fix + coordinated audit-loud-failure changes)
with the v0.35 lifecycle consolidation. The two waves shipped together
because v0.34 never got cut as its own tag.

### Breaking — lifecycle consolidated on the async-CM protocol (v0.35)

Three overlapping lifecycle surfaces collapse into one. The App is now
its own async context manager; `async with app:` is the canonical
entry point.

| Removed                                          | Replacement                                                |
|--------------------------------------------------|------------------------------------------------------------|
| `a2kit.App(..., lifespan=cm)`                    | Marker singleton with `__aenter__`/`__aexit__`, OR move imperative work into `main()` before `async with app:`. |
| `Router.lifespan` classmethod                    | Implement `__aenter__` / `__aexit__` on the Router subclass. Enters lazily on first dispatch of any of its tools. |
| `app.singleton(..., teardown=fn)`                | Move cleanup onto the resource itself via `__aexit__`, `aclose`, or `close` — framework auto-detects (first match wins). |
| `app.lifespan_cm()`                              | `async with app:` |
| `app.has_lifespan()`                             | Removed — `async with app:` is always safe to enter. |
| `app.warm_async_singletons()`                    | Removed — every registered singleton resolves and enters during `App.__aenter__`. |
| `app.teardown_failures` attribute                | Removed — singleton/router `__aexit__` failures log at `a2kit.lifecycle` ERROR. |
| `a2kit.lifespan.compose(...)` + entire module    | Removed — composition is internal `AsyncExitStack`. |

Each removed kwarg raises `TypeError` with the migration recipe
embedded; no aliases, no `DeprecationWarning`, no transitional period.

`app.singleton(...)` accepts three call shapes:

```python
app.singleton(SomeClass)                    # type = class itself
app.singleton(factory)                      # type from return annotation
app.singleton(BaseClass, factory)           # explicit base-type override
```

`App` construction stays pure (no async work, no resource entry) — use
that for wiring-only tests. `async with app:` is the only entry point.

### Behaviour — singleton entry order is now DI-topological

Singletons enter in topological order over the DI sub-graph restricted
to the registered set; registration order is the tiebreaker between
unrelated singletons. Previously singletons entered strictly in
registration order.

| Before                                                 | Now                                                          |
|--------------------------------------------------------|--------------------------------------------------------------|
| `app.singleton(Repo); app.singleton(DB)` → Repo enters first | `DB` enters first (Repo depends on DB via its factory)  |
| Registration order strictly preserved                  | Registration order kept ONLY between unrelated singletons    |

If a test asserts singleton entry order, switch the assertion to
DI-topological order. Apps that already registered dependencies before
their dependents see no change.

---

### v0.34-wave changes (folded into v0.35.0; never tagged separately)

This wave closes the v0.32 MCP production blocker (a2web v0.6.0
went down on every `mcp__a2web__fetch` call) and pays down the
test-coverage debt that let it slip past release validation. Eight
coordinated changes land together; the wire-error envelope and the
ctx-binding fix are mutually load-bearing.

### Breaking — MCP wire-error envelope is now a2kit-owned

When a tool body or wrapper raises, the wire now returns a
`ToolError(json)` whose payload carries the original exception's
class name, message, and (under `App(debug=True)`) traceback:

```json
{"class": "ValueError", "message": "bad arg", "traceback": "..."}
```

Previously the wire collapsed to the bare string `"Error calling
tool 'X'"` regardless of `debug=`, because the guarantee was
outsourced to FastMCP's `mask_error_details` which shifted across
minor versions. Consumers parsing the envelope must now JSON-decode
the `ToolError` text. `FastMCPError` subclasses (incl. user-raised
`ToolError`) re-raise unchanged.

### Fixed — MCP dispatch stripped `ctx` from the wrapped signature

Any tool that declared **both** a container-resolved param (`state:
T`) and `ctx: a2kit.ToolContext` failed 100% of MCP calls with
`TypeError: <fn>() missing 1 required keyword-only argument: 'ctx'`.
CLI was unaffected. The wrapper chain (`_wrap_with_dispatch_hook`)
now re-appends the `ctx` Parameter to the rewritten signature, and
a decoration-time invariant (`A2KitContextBindingBroken`) catches
future regressions before wheels ship.

### Changed — in-process test client now drives real fastmcp.Client

`a2kit.testing.client.TestClient` is rebuilt on
`fastmcp.Client(transport=build_mcp_server(app))`. It exercises the
production wrapper chain on every invoke, so any ctx-shape
divergence between `StderrToolContext` and `fastmcp.Context` fails
in test. The ctx-binding bug above slipped past the v0.32 test suite
because the legacy client subclassed the CLI stub and bypassed the
dispatch hook entirely.

Behavioural changes for test authors:

- `client.invoke(...)` returns FastMCP-marshaled types (field-equal,
  identity-different from user-declared classes). Compare field-wise
  or via `model_dump()`.
- Tool exceptions surface as `fastmcp.exceptions.ToolError`; parse
  the JSON envelope for class + message.
- log internal extra-keys are prefixed with `a2kit_` on the wire
  (`a2kit_kind`, `a2kit_name`, `a2kit_payload`, `a2kit_elapsed_ms`,
  `a2kit_type`) to dodge Python `LogRecord` reserved-attribute
  collisions. The `TestClient` un-prefixes them when populating
  `client.events` / `client.reports` / `client.logs`, so capture
  shape is unchanged.

### Added — App-construction validation of `Router.tools` completeness

`App.add_router(router)` now walks `vars(cls)` for `@a2kit.*`-tagged
callables and set-diffs against the `tools = (...)` tuple. A
decorated-but-unlisted method raises
`A2KitDecoratedMethodNotInTools` at App construction (not at
deploy, not at first call). Closes the v0.31 CHANGELOG promise of a
static lint rule — caught here is cheaper than a plugin and runs in
every dev `python -m app` boot.

### Added — per-tool `timeout=` on `@a2kit.read/write/list_`

```python
@a2kit.read(timeout="60s")
async def fetch(*, url: str) -> dict: ...
```

Framework-owned `anyio.fail_after` wraps the tool body, slotted
outside the log scope (so teardown `event()` calls don't race the
deadline) and inside the dispatcher's lifecycle unwind (so resource
cleanup still runs). Parses `int`/`float`/`"60s"`/`"500ms"`/`"5m"`.
Surfaces on `A2KitMetaExtras.timeout_seconds` for callers and
annotation consumers.

### Added — `App.singleton(T, factory, *, teardown=fn)`

Framework-owned, topologically-ordered teardown for singleton
resources. Dependents tear down before their providers; teardown
failures are logged and recorded on `App.teardown_failures: list[(type,
Exception)]` without halting the rest. Composes after any user /
Router `lifespan` finally-blocks, so user code still runs first.
Replaces the hand-rolled `for closer in (...): try: await closer()
except: pass` pattern that silently swallowed errors in every
consumer.

### Changed — Context method signatures narrowed across the 13-method drift

`StderrToolContext` was the looser shape on `read_resource`, `elicit`,
`sample` / `sample_step`, `get_prompt`, `list_resources` /
`list_prompts` / `list_roots`, `send_notification`. All thirteen now
mirror `fastmcp.Context` exactly (modulo `self`); `read_resource`
returns a duck-typed `_StubResourceResult` so consumers reading
`.content` work on both transports. `send_log_message` is removed
from the stub (not in `fastmcp.Context`). New
`A2KitInvalidContextAnnotation` rejects `ctx: ToolContext | None`
declarations at decoration time — the dispatcher always binds.

### Breaking — `ctx.info/warning/error/debug` no longer accept arbitrary `**fields`

The four `fastmcp.Context` logging methods are narrowed to fastmcp's
exact signature `(message, logger_name=None, extra=None)` on the CLI
stub. Calls of the shape `await ctx.info("msg", batch=2)` now raise
`TypeError` on both transports. The kwarg form previously appeared to
work on CLI while crashing under MCP (a real client serialised the
unknown kwarg into `LogRecord` constructor args).

Field-bearing structured logging now lives on `a2kit.log.*` as a third
sibling alongside `event` and `report`:

```python
# before
await ctx.info("starting", batch=2)

# after
import a2kit
await a2kit.log.info(ctx, "starting", batch=2)
```

`a2kit.log.log(ctx, level, msg_or_instance, **fields)` plus the
`info` / `warning` / `error` / `debug` convenience aliases accept both
string and dataclass/pydantic instance forms (the same shape as
`a2kit.log.event`). They round-trip identically on MCP (delivered as
`notifications/message` with structured `extra`) and CLI (rendered as
`[ +s.mmm INFO    ] msg k=v`). The `--no-events` flag and
`A2KIT_LOG__ENABLED=false` env var gate all three primitives.

Migration recipe:
`s/await ctx\.(info|warning|error|debug)\("([^"]*)", ([^=)]+=.*)\)/await a2kit.log.\1(ctx, "\2", \3)/`
catches the documented call shapes. `ctx.info("plain")` and
`ctx.info("msg", extra={...})` continue to work unchanged.

## 0.33.0 — Prettification: footguns + dead surface + README rescue — 2026-05-13

Tightens the v0.32 consumption interface before the next wave of consumer
migrations (a2atlassian, a2db). Every change follows the "loud failure
with embedded migration hint" convention. The five footgun guards, four
dead-surface removals, one collapse, and the README-drift CI gate land
together as a single coordinated breaking release.

Migration table:

| before                                          | after                                          |
|-------------------------------------------------|------------------------------------------------|
| `@a2kit.tool(...)`                              | `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` per semantics |
| `@a2kit.read/write/list_(name="x")`             | rename the method — auto-derived from `fn.__name__` |
| `@a2kit.read(idempotent=...)`                   | drop — reads are spec-idempotent (raises `TypeError`) |
| `@a2kit.list_(idempotent=...)`                  | drop — list is read-shaped (raises `TypeError`) |
| `@a2kit.list_(destructive=...)`                 | drop — list is read-shaped (already raised) |
| `@a2kit.list_(...)` on `-> dict` etc.           | annotate `-> list[T]` (raises `TypeError` at decoration) |
| `@a2kit.list_(page_size=0)` or `<=0`            | use a positive integer or omit (raises `ValueError`) |
| `@a2kit.write(annotations=..., idempotent=...)` | pick one path (raises `TypeError` on conflict) |
| `@app.singleton(T)` (decorator form)            | `app.singleton(T, factory)` method-call form  |
| `from a2kit.tool import tool`                   | `from a2kit.tool import read` / `write` / `list_` |
| `app.tool_descriptors()`                        | `app.tools()` (now returns `list[ToolDescriptor]`) |
| `app.tools()` returning callables               | `[d.fn for d in app.tools()]`                  |
| `App(health_tool=True)` + checks                | drop the flag — `@app.health_check` auto-installs the tool |

### Fixed — `<app> health` crashed on fresh non-dev installs

`a2kit.packages.cli.builder._register_health` imported
`a2kit.packages.testing.client`, which transitively imported `pytest`.
Any consumer installing the app via `pipx` / `uv tool install` / `uvx`
hit `ModuleNotFoundError: pytest` on first invocation of
`<app> health`. The CLI health subcommand now calls
`a2kit.packages.health.run_checks(app)` directly under the App's
`lifespan_cm()` — no test client, no pytest import. Defense in depth:
`packages.testing.fixtures` also guards the pytest import so the testing
package itself stays importable without pytest installed (fixtures
degrade to plain callables when pytest is absent).

### Breaking — `@a2kit.tool` removed

Zero consumer usage. Choose `@a2kit.read` (read-shaped), `@a2kit.write`
(write-shaped), or `@a2kit.list_` (list-shaped). Accessing `a2kit.tool`
on a fresh `import a2kit` raises `AttributeError` with the migration hint
embedded.

### Breaking — `name=` removed from public verb decorators

Tool name derives from `fn.__name__` automatically; the rare custom-name
case is handled by the framework-internal `_read_internal` helper used
only for `_meta.health`. Calling `@a2kit.read(name="x")` (or `write` /
`list_`) raises `TypeError`.

### Breaking — `@app.singleton(T)` decorator form removed

Method-call form `app.singleton(T, factory)` is the only path. When
`factory` is omitted, the type itself is the factory (class-as-factory
semantics, same as `app.provide(T)`). Frees the signature for the
upcoming `teardown=` parameter.

### Breaking — `app.tools()` returns `list[ToolDescriptor]`

Collapses the previous two-accessor split (`tools()` for callables vs.
`tool_descriptors()` for descriptors) into one. `app.tool_descriptors()`
remains as a one-line alias in v0.33 for soft migration; removed in a
later minor. Consumers that wanted callables: `[d.fn for d in app.tools()]`.

### Breaking — MCP-spec-derived constraints enforced

- `@a2kit.read(idempotent=...)` and `@a2kit.list_(idempotent=...)` →
  `TypeError`. Per MCP spec, `idempotentHint` is meaningful only when
  `readOnlyHint=false`; reads are spec-idempotent by definition. Mirror
  of the existing `destructive=` rejection.
- `@a2kit.list_(destructive=...)` → `TypeError` (was already true on
  `@read`; symmetric on `@list_` now).
- `@a2kit.list_` requires a `list[T]` / `tuple[T,...]` / `set[T]` /
  `frozenset[T]` return annotation at decoration time. Non-collection
  returns raise `TypeError` with the actual annotation in the message.
  Bare `list` (no type parameter) decorates but emits a
  `RuntimeWarning` (selectable-field derivation will be empty).
- `@a2kit.list_(page_size=0)` (or `<= 0`) → `ValueError` at decoration.
- `annotations=ToolAnnotations(...)` mixed with any flag kwarg
  (`idempotent`, `open_world`, `destructive`, `title`) → `TypeError`.
  No silent winner; pick one path.

### Changed — `@app.health_check` auto-enables the health tool

First `@app.health_check` call auto-installs the `_meta.health`
synthetic router (idempotent — subsequent calls just register checks).
`App(health_tool=True)` remains accepted (no-op when checks are also
registered) for apps that want the tool present with zero checks.

### Changed — `AmbientContextMissing` message split

Two distinct failure modes get distinct messages (same exception class):

- **Mode A** — primitive called with no active dispatch (ContextVar
  unset): "called outside an active tool dispatch" (existing wording).
- **Mode B** — primitive called from a tool body whose signature omits
  `ctx: a2kit.ToolContext`: "called from a tool body that did not
  declare `ctx: a2kit.ToolContext` as a parameter; add the parameter to
  the tool signature, or remove the log call."

`AmbientContextMissing.mode` exposes
`MODE_NO_DISPATCH` / `MODE_MISSING_CTX_PARAM` for programmatic checks.

### Added — README ↔ live-code parity CI gate

New `tests/test_readme_symbol_drift.py` parses `README.md` and asserts
every claimed public symbol (`a2kit.X`, `@a2kit.X`, `App.X`,
`Router.X`, submodule paths) resolves on the live module surface.
Wired into `make lint`. Initial run flagged ~10 stale references to
the v0.31-removed `@app.on_startup` / `@app.on_shutdown` decorators
and the never-shipped `Surface` Flag enum; all corrected in this pass.

### README

Substantial rewrite: removed phantom `@app.on_startup` /
`@app.on_shutdown` (use `App(lifespan=cm)`), removed the `Surface` enum
claim (the code shape is `visibility: Literal["hidden", "cli", "all"]`),
removed `@a2kit.tool` references, simplified the verb-decorator kwarg
tables to reflect the v0.33 surface, spelled out the **log** acronym
("Logging / Data / Diagnostics") at first mention, documented the
default connection-store path (`~/.config/a2kit/connections/` or
`$A2KIT_CONFIG_HOME`), noted the `list_` trailing-underscore convention.

---

## 0.32.0 — Typer CLI + consumption-interface audit — 2026-05-13

A coordinated breaking bundle: the Typer CLI rewrite plus the five-change
consumption-interface audit (Q1-Q5 + ADR 0003). Consumers migrate once
across the whole surface rather than per-change.

Migration table (alphabetical):

| before                                | after                                  |
|---------------------------------------|----------------------------------------|
| `@a2kit.read/write/list_/tool(tags={...})` | drop — no replacement              |
| `@a2kit.read/write/list_/tool(surfaces=Surface.CLI)` | `visibility="cli"`       |
| `@a2kit.read/write/list_/tool(surfaces=Surface.ALL)` | drop (default)            |
| `@a2kit.read/write/list_/tool(surfaces=Surface.MCP)` | no replacement (was unused) |
| `App(name, debug=True)`               | unchanged (kept — has live readers)    |
| `body: SomeBaseModel` flattened flags | `--body '<json>'` single flag         |
| `from a2kit import A2KitMeta`         | `from a2kit.metadata import A2KitMeta` |
| `from a2kit import RouterRegistry`    | `from a2kit.routers import RouterRegistry` |
| `from a2kit import UNRESOLVED`        | `from a2kit.app import UNRESOLVED`     |
| `from a2kit import Cap, capabilities` | removed — no replacement               |
| `from a2kit import Surface`           | removed — `visibility` literal type    |
| `from a2kit import ToolCallContamination` (+ 4 siblings) | `from a2kit.exceptions import ...` (A2KitError stays at top-level) |
| `from a2kit.log import logging.LogRecord, logging.Handler` | `from a2kit.packages.log import ...` |
| `install_connections(app, T); app.add_cli(connections_cli(T))` | `install_connections(app, T)` (one call) |

### Added — `visibility` tier on every verb decorator + `Router.visibility`

Three-tier transport-routing kwarg (`"hidden"` / `"cli"` / `"all"`) plus
matching `Router.visibility` class attribute. Per-tool kwarg overrides
Router default. Replaces the `Surface` Flag enum, which modelled CLI and
MCP symmetrically when the threat model is asymmetric (CLI is
operator-facing and always-on; MCP/API/GraphQL are agent-facing and the
gated surface).

CLI builder maps `visibility="hidden"` to Click's native `hidden=True`.
MCP server skips both `"hidden"` and `"cli"` tiers. Lint rule
`A2K-SURFACE-EXPLICIT` updated to suggest `visibility="cli"` for
credential-named tools (`login`/`logout`/`rotate_key`/etc.).

### Added — `@a2kit.list_` parameter parity

`@a2kit.list_` now accepts `idempotent`, `open_world`, `title`, and
`visibility` like the other three verb decorators. Asymmetry was
historical. `destructive=True` raises `TypeError` on `@list_` and
`@read` alike (both are read-shaped).

### Added — ADR 0003: semantic-flag vocabulary

`docs/adr/0003-semantic-flag-vocabulary.md` locks the framing that
emerged from the consumption-interface audit: `idempotent`,
`open_world`, `destructive`, `title` are transport-neutral tool
semantics, not MCP escape hatches. Each flag MUST have a meaningful
read on at least two transports; adding a new flag requires an ADR
superseding 0003.

### Changed — connections plugin: one-call wiring

`install_connections(app, *conn_types)` now installs the dispatch hook,
registers the wire scope, AND adds the `connections` Click subcommand
group in a single call. The standalone `connections_cli` factory is
still importable from `a2kit.packages.connections.cli` but is no longer
exported from the package's public surface.

### Changed — `@a2kit.read/write/list_/tool(tags={...})` removed

Author-set decorator tags had zero live users across `src/`, `tests/`,
`examples/`, and the four downstream consumer repos. Framework
auto-stamped verb tags (`"read"` / `"write"` / `"list"`) are preserved
— readers in MCP server and OTEL middleware unaffected.

### Removed — `a2kit.Cap` + `a2kit.capabilities` + A2K009/A2K012 lint rules

Capability registry was aspirational surface with no live consumer.
Lint rules A2K009 (raw built-in capability strings) and A2K012 (raw
custom capability strings) existed solely to enforce discipline on
top of `tags=` — moot now that tags is gone.

### Removed — `a2kit.Surface` `Flag` enum + `surfaces=` decorator kwarg

Superseded by `visibility` tier (see Added section above). The Surface
flag is deleted entirely; `src/a2kit/surface.py` removed.

### Changed — top-level `a2kit.*` namespace trimmed to 95% authoring surface

22 names → 10 names. Demoted symbols stay in their owning modules:
`A2KitMeta`, `RouterRegistry`, `UNRESOLVED`, four non-umbrella exception
subclasses, and the log sink-author types `logging.LogRecord` / `logging.Handler`.
`A2KitError` (umbrella exception) and the live log primitives
(`event`/`report`/`log`/`info`/`warning`/`error`/`debug`/`EventRegistry`/
`format_condensed_line`/`bind_call_scope`) stay re-exported.

### Changed — CLI builder rewritten on top of Typer (breaking shape for body-model tools)

`src/a2kit/packages/cli/builder.py` no longer hand-rolls Click reflection.
Each tool function is registered through `typer.Typer.command()` with a
synthesized `__signature__` / `__annotations__` derived from the wire
params. The `FieldInfo.description` set via `pydantic.Field(...)` is
surfaced as `typer.Option(help=...)` through a small adapter at
`src/a2kit/packages/cli/_field_to_typer.py`. Net: roughly 250 LOC out of
the CLI package.

Tool-author surface is **unchanged**. The router decorator API, the
`tools = (...)` tuple, kwonly DI parameters, docstring-as-help, and the
`--format` / `--schema` / `--connection` / `--no-reports` / `--no-events`
flags all behave the same.

**Breaking shape — body-model parameters on the CLI.** A tool param typed
as `body: SomeBaseModel` is now exposed as a single JSON-string flag
`--body '<json>'` and decoded via `SomeBaseModel.model_validate_json`.
The previous flattened-flag-per-field UX is gone. In-repo blast radius
is zero — no in-repo tool ships this shape — but downstream callers
using a body model as a kwonly param must switch to the JSON-string
form. MCP wire shape unchanged.

`a2kit.packages.cli.schemas` has been removed; its `compute_schema`
moved to a new transport-neutral module `a2kit.schema` (lazy-imported
via `_LAZY_MODULES`, no `click` / `fastmcp` dependency). Public
re-export `a2kit.testing.compute_schema` is preserved. The CLI's
`<app> schema [tool]` subcommand is now a Typer command registered
directly on the root app.

`typer>=0.25,<1` is a new runtime dependency. `import a2kit` does not
trigger `import typer`; both are lazy.

See `docs/adr/0001-typer-cli.md` for the decision rationale.

## 0.31.0 — bundled breaking minor — 2026-05-13

A single release bundles four coordinated changes so consumers migrate
once, not four times. Coordinated proposals
`align-with-pydantic-and-stdlib`, `loud-degrade-everywhere`,
`explicit-router-surface`, and `lifespan-over-lifecycle-hooks` all ship
here.

### Changed (observability only) — WARN_ONCE on five swallowed sites

Five framework-internal introspection sites that previously swallowed
`Exception` silently now emit one WARN-level log line per offender per
process on first failure and proceed with the documented fallback.
Extends the `_WARN_ONCE` recipe shipped in
`src/a2kit/signature.py:resolve_hints` (round 5/6).

- **L1** `src/a2kit/packages/mcp/server.py:_wrap_with_dispatch_hook` —
  return-annotation copy onto the wrapper now WARNs once per
  `fn.__qualname__` on `get_type_hints` failure instead of using
  `contextlib.suppress(Exception)`. Fallback unchanged: the wrapped fn
  keeps its current annotation-less state, FastMCP's output schema for
  that tool is absent.
- **L2** `src/a2kit/tool.py:_resolve_return_annotation` — WARNs once
  per `fn.__qualname__` on `get_type_hints` failure instead of
  silently returning `None`. Fallback unchanged: returns `None`.
- **L3** `src/a2kit/tool.py:_derive_selectable_fields` — outer
  `get_type_hints` failure WARNs once per `fn.__qualname__` instead of
  silently returning `()`. The inner
  `with contextlib.suppress(Exception):` around the dataclass branch
  was verified dead by running the full test suite after removal
  (788 tests green, including the dataclass-fields regression test);
  the suppress is gone, the branch is unguarded.
- **L4** `src/a2kit/packages/mcp/listview.py:ListViewMiddleware` —
  both `except Exception: return result` sites now WARN once per
  composite key (`f"{tool_name}::get_tool"` for the registry lookup,
  `f"{tool_name}::project"` for the result-reconstruction site) via a
  single module-local `_WARN_ONCE: set[str]`. Fallback unchanged: the
  unprojected `result` is returned.
- **L5** `src/a2kit/packages/otel/middleware.py:_meta_a2kit` — WARNs
  once per `tool_name` on `server.get_tool` failure instead of
  silently returning `{}`. Fallback unchanged: span construction
  proceeds with only `a2kit.tool_name` set; `a2kit.verb`,
  `a2kit.router`, `a2kit.tags` are absent.

### Documentation

- `OPERATIONAL_CONTRACTS.md` gains a new Q9 section codifying the
  "fail-observable, not silent" policy for framework-internal
  introspection failures and indexing the six sites the policy covers
  today.

### Breaking — Param/MetaExtras/Container cache (`align-with-pydantic-and-stdlib`)

- **`a2kit.Param` removed.** The wrapper was a one-line forwarder to
  `pydantic.Field`. Use `Annotated[T, pydantic.Field(description="...")]`
  directly. Migration regex (positional form):
  `s/a2kit\.Param\(("[^"]+")\)/pydantic.Field(description=\1)/`.
  Keyword callers (`a2kit.Param(description="...", examples=[...])`)
  rewrite to `pydantic.Field(description=..., examples=[...])` —
  identity at the kwargs level. `description_of` (internal helper)
  moves to `a2kit._field_introspect`.
- **`A2KitMeta.extra: dict[str, Any]` → `A2KitMeta.extras: A2KitMetaExtras`.**
  The open-dict extension slot becomes a typed pydantic `BaseModel`
  with named fields (`report_type`, `report_schema`, `router_slug`,
  `surfaces`, `list_view`). Read and write through attribute access;
  the legacy `a2kit.<key>` string-key namespace is gone.
  Migration:
  `meta.extra.get("a2kit.report_type")` → `meta.extras.report_type`,
  `meta.extra["a2kit.router_slug"] = slug` → `meta.extras.router_slug = slug`,
  `meta.extra.get("a2kit.surfaces", Surface.ALL)` → `meta.extras.surfaces or Surface.ALL`.
  The wire-projection on `tool.meta["a2kit"]["extras"]` carries the
  same attribute names without the `a2kit.` prefix. The
  `_EXTRA_DROP_FROM_WIRE` constant and the `_ROUTER_SLUG_KEY` /
  `SURFACE_META_KEY` / `EXTRA_TYPE_KEY` / `EXTRA_SCHEMA_KEY` exports
  delete with the dict shape.

### Fixed

- **`Container._param_cache` keyed by `id(factory)` was a latent
  stale-cache bug** under CPython id recycling across nested test
  scopes (same hazard documented for tool-signature caching in
  `a2kit/signature.py`). Replaced with
  `weakref.WeakKeyDictionary[Factory, list[_ParamSpec]]` keyed on the
  live factory object. Internal-only; no migration.

### Breaking — explicit Router surface (`explicit-router-surface`)

The four contracts a Router exposes — `slug`, `tools`, `providers`,
`lifespan` — are now the closed discovery surface. The framework
reads what you wrote; it never invents what's missing.

- **`slug: ClassVar[str]` is required.** The auto-derivation rule
  (strip `Router` suffix, lowercase) is removed; `_derive_slug` is
  gone from `src/a2kit/routers.py`. Missing slug raises `TypeError`
  at `Router.__init__` time naming the subclass. The legacy `name`
  constructor arg / `name` class attribute no longer drives the
  slug; leave `name` off or treat it as a plain attribute.
  Migration: add `slug = "<derived>"` to every Router subclass.
- **`tools: ClassVar[tuple[Callable, ...]]` is required.** The
  `dir(self)` walk in `Router._collect_methods` is gone. Each
  Router lists every `@a2kit.read/write/list_/tool`-decorated
  method in a tuple placed AFTER the method definitions in the
  class body. `Router.__init__` iterates the tuple, binds each
  entry via `getattr(self, fn.__name__)`, and stamps router-slug
  on the bound method's `_a2kit` meta. Missing meta on a listed
  entry raises `TypeError`; a decorated-but-unlisted method
  silently does NOT register (a follow-up lint rule will flag this
  drift statically). The instance-method `Router.tools()` is
  renamed to `Router.bound_tools()`; `RouterRegistry.tools()` →
  `RouterRegistry.bound_tools()`. `App.tools()` is unchanged.
- **`@reports(T)` folded into verb kwargs.** The standalone
  `@a2kit.packages.mcp.reports.reports(T)` decorator is gone;
  `a2kit/packages/mcp/reports.py` is deleted. Use the
  `reports=T` kwarg on `@a2kit.read/write/list_/tool` directly.
  `stage_extra` and `PENDING_EXTRA_ATTR` are removed from
  `a2kit.metadata`; verb decorators write the typed extras
  (`report_type`, `report_schema`, `list_view`) directly on
  `A2KitMetaExtras`.
- **`Router.install(self, app)` hook removed.** The
  `getattr(router, "install", None)` call site in
  `App.add_router` is deleted. Routers expose contracts via
  `slug` / `tools` / `providers` / `lifespan` only; anything the
  hook did belongs in `providers` or `lifespan`.
- **`Router.on_startup` / `Router.on_shutdown` auto-bridge removed.**
  The `App.add_router` loop that scanned `cls.__dict__` for these
  method names and registered them as App lifecycle handlers is
  gone. Routers expose lifecycle via a single
  `@contextlib.asynccontextmanager async def lifespan(self):`
  method. `App.add_router(r)` composes `r.lifespan` into the App's
  top-level lifecycle so the pre-`yield` body runs at startup (in
  `add_router` order) and the post-`yield` body runs at shutdown
  (LIFO). Composition uses a small in-App `AsyncExitStack` bridge
  that the sibling `lifespan-over-lifecycle-hooks` proposal will
  replace with `a2kit.lifespan.compose`.

Migration (per Router subclass):

```python
class TasksRouter(a2kit.Router):
    slug = "tasks"
    providers = (TrackerStore,)
    enrichers = (tracker_404_enricher,)

    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task: ...

    @a2kit.write(reports=BatchReport)
    async def bulk_import(self, *, ctx: a2kit.ToolContext, ...) -> dict: ...

    @asynccontextmanager
    async def lifespan(self, *, store: TrackerStore):
        await store.open()
        try:
            yield
        finally:
            await store.close()

    tools = (get_task, bulk_import)
```

### Breaking — lifespan over lifecycle hooks (`lifespan-over-lifecycle-hooks`)

`@app.on_startup` / `@app.on_shutdown` are gone. The App accepts a
single `lifespan=` async-context-manager callable. FastMCP's `lifespan=`
slot is the canonical hook for this work; a2kit no longer maintains a
parallel handler registry.

- **`App(name, ..., lifespan=lifespan)`** accepts a callable returning
  an async context manager. Signature is fixed at exactly one
  positional parameter, the App instance:
  `async def lifespan(app: a2kit.App)`. The framework does NOT
  introspect the signature and does NOT auto-resolve typed kwargs.
  Resolve singletons inside the body via
  `await app.container().aresolve(T)`.
- **Sync `def` lifespans rejected at construction** with `TypeError`.
  Sync setup work goes inside the async body as plain statements.
- **`@app.on_startup` / `@app.on_shutdown` removed.** No shim.
- **`App.warm_async_singletons()`** is the explicit replacement for the
  implicit `@on_startup` warm-up of async-factory singletons. Call it
  from inside the lifespan body before `yield` when you want sync
  `container.resolve(T)` to see resolved values later.
- **`a2kit.lifespan.compose(*lifespans)`** composes multiple lifespans
  into one via `contextlib.AsyncExitStack`. Startup runs in declared
  order; shutdown unwinds LIFO. Each shutdown leg is shielded — an
  exception is logged at ERROR under `a2kit.lifecycle` with traceback
  and sibling legs continue to unwind.
- **`App.add_router(r)`** composes `r.lifespan` into the App's final
  lifespan via the same compose helper. The previous in-App
  `AsyncExitStack` bridge that the sibling `explicit-router-surface`
  shipped is now routed through `a2kit.lifespan.compose`.
- **FastMCP integration** — `build_mcp_server(app)` wraps
  `app.lifespan_cm()` in an adapter matching FastMCP's
  `lifespan(server)` slot. The adapter sets `server._a2kit_app = app`
  as a back-reference so middleware and other power-user code can
  recover the App from the FastMCP server.
- **Test client** — `a2kit.testing.client(app).__aenter__` enters
  `app.lifespan_cm()`; `__aexit__` exits it. Observable behaviour
  matches today; the underlying mechanism replaces `dispatch_startup` /
  `dispatch_shutdown`.
- **`dispatch_startup` / `dispatch_shutdown` removed** from
  `a2kit.app`. Public test harnesses that called them directly switch
  to `async with app.lifespan_cm():`.
- **Error message update** — `container.resolve(T)` on an unresolved
  async-factory singleton now directs callers to
  `await app.warm_async_singletons()` from the App's lifespan body
  (the message no longer mentions `@on_startup`).

Migration recipe (per call site):

```python
# Before
@app.on_startup
async def _open(state: AppState):
    await state.open()

@app.on_shutdown
async def _close(state: AppState):
    await state.close()

# After
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    state = await app.container().aresolve(AppState)
    await state.open()
    try:
        yield
    finally:
        await state.close()

app = a2kit.App("name", lifespan=lifespan)
```

For multi-component apps (App + several Router.lifespan
contributions), compose via:

```python
app_lifespan = a2kit.lifespan.compose(
    my_app_lifespan,
    router_a.lifespan,
    router_b.lifespan,
)
app = a2kit.App("name", lifespan=app_lifespan)
```

## 0.30.0 — drop docstring → param description auto-pull — 2026-05-12

### Removed

- **Google-style docstring → param description auto-pull** (shipped
  v0.29.0, refined v0.29.1). The regex-based `Args:` parser in
  `src/a2kit/_docstring.py` is deleted along with
  `_augment_annotations_from_docstring` in `src/a2kit/tool.py`.
  `_stamp` no longer mutates `fn.__annotations__` at decoration time.
- **`A2KitMeta.param_descriptions`** field (added v0.29.1) — was only
  populated from the now-removed parser.

### Migration

Tools that relied on docstring `Args:` blocks for parameter
descriptions must add explicit
`Annotated[T, a2kit.Param(description="...")]` or
`pydantic.Field(description="...")`. The v0.28 surface returns: those
two annotations are the only ways to attach parameter descriptions to
the MCP schema and CLI option help.

Tool-level descriptions (first docstring line + full body → MCP
description + CLI long-help) are unchanged.

## 0.29.1 — round-5/6 cleanup bundle — 2026-05-12

Two paired cleanups against round-5/6 contracts (no new features).

### Added

- `Container._override(type_, instance)` — test-seam method owning the
  three-attribute mutation (`_providers`, `_singletons`,
  `_async_factories`). `TestClient.override` delegates here, closing
  three `# noqa: SLF001` leaks.
- `A2KitMeta.param_descriptions: Mapping[str, str]` — Google-style
  `Args:` resolution is now stored on meta in addition to the existing
  `fn.__annotations__` mutation. Authoritative source for downstream
  middleware / introspection tooling.

### Changed

- log ctx binding is uniform across MCP / CLI / TestClient: none of
  them synthesize a fake context when a tool omits `ctx`. A no-ctx
  tool that calls `await a2kit.log.event(...)` raises
  `AmbientContextMissing` identically on every dispatcher (previously
  worked silently on CLI and TestClient).
- log shorthands (`a2kit.log.info/warning/error/debug`) surface their
  own name in `AmbientContextMissing` instead of the delegated-to
  `a2kit.log.log`.
- `_docstring.extract_param_descriptions` and the `get_type_hints`
  call in `_augment_annotations_from_docstring` log one WARN per
  qualname on parse / resolution failure (was silent
  `contextlib.suppress(Exception)`). Decoration still never raises.
- OPERATIONAL_CONTRACTS Q8 reworded: "active dispatch" is the
  conjunction of an `bind_call_scope` scope **and** a declared ctx
  param. Lazy singleton factories instantiated during dispatch may
  call log primitives (new paragraph + example).
- README testing section updated: `TestClient.override`,
  `call_wire`, async-singleton factories, ambient-log section,
  docstring-pull note. Migration bullet points at `TestClient.override`
  as the preferred test path.

## 0.29.0 — a2web round-5 + round-6 ergonomics — 2026-05-12

Five changes closing every open ergonomic gap from a2web feedback
rounds 5 and 6. Two are breaking; the rest are additive.

### Added

- **`app.singleton(T, async_factory)`** — singleton factories may now
  be `async def`. First resolution awaits via the new
  `container.aresolve` path; subsequent resolves return the cached
  instance synchronously. Concurrent first resolutions coalesce on a
  per-type `asyncio.Lock`. Replaces the hand-rolled double-checked-
  locking resource pattern (~80 LOC of boilerplate per a2web
  resource).
- **`TestClient.override(type_: type[T], fake: T)`** — type-safe DI
  override on the in-process test client. Snapshot/restore on the
  App's container; auto-cleans on `__aexit__` (normal or
  exceptional). Replaces ad-hoc `monkeypatch.setattr` patterns.
  Overlapping TestClient sessions on the same App raise
  `RuntimeError`.
- **`TestClient.call_wire(tool, **kwargs)`** — returns the
  formatter-encoded wire payload (JSON / TSV / page-tsv) instead of
  the Python value `invoke` returns. Reads the cached
  `descriptor.format_hint` so test-observed format and production
  wire format flip in lockstep when a tool's return annotation
  changes.
- **Docstring → param description auto-pull** — Google-style
  docstring `Args:` / `Arguments:` / `Parameters:` sections feed
  per-parameter descriptions into the tool's annotations at
  decoration time. Explicit `Annotated[T, a2kit.Param(...)]` /
  `pydantic.Field(...)` always wins. Numpy and Sphinx/reST formats
  are explicit non-goals.
- **`a2kit.exceptions.AmbientContextMissing`** — raised when an log
  primitive is called outside an active tool dispatch.

### Changed (breaking)

- **log primitives drop the `ctx` argument.** `a2kit.log.event`,
  `report`, `log`, `info`, `warning`, `error`, `debug`, and
  `EventRegistry.emit_typed` no longer accept `ctx`. They read it
  from the ambient `_CallScope` ContextVar bound by the dispatcher
  for the lifetime of one tool invocation. Migration: drop the
  first positional argument at every call site. Calling outside
  an active dispatch raises `AmbientContextMissing` — fail loud,
  no silent no-op fallback.
- **`bind_call_scope(...)`** now takes a required keyword
  `ctx=...` argument. Tests that exercise log primitives directly
  (without a full tool dispatch) wrap with this — same seam the
  framework uses internally.

### Documentation

- `OPERATIONAL_CONTRACTS.md` Q8: log primitives require an active
  tool dispatch.

## 0.28.1 — FastMCP 3 `_meta` disable fix — 2026-05-12

### Fixed

- **`build_mcp_server` no longer crashes on FastMCP ≥ 3.0.** The
  per-tool `tool.disable()` call site was removed in FastMCP 3 and
  raised `NotImplementedError` on every `App(health_tool=True)`
  serve. Replaced with a single post-loop
  `server.disable(tags={"_meta"})` using FastMCP 3's visibility
  transform API; the `_meta` tag is already stamped on every
  `_meta.*` tool, so future additions inherit the rule.

### Changed

- `_meta.*` tools are now also rejected at `build_mcp_server`
  time (not just at decoration), closing the metadata-mutation
  bypass.

### Documentation

- `OPERATIONAL_CONTRACTS.md` Q7: the `_meta.*` tool namespace
  contract (closed namespace, MCP-hidden / CLI-visible split,
  rejection rule).

## 0.28.0 — a2kit.log.log primitive (Context-shape divergence repair) — 2026-05-12

`ctx.info("msg", k=v)` — the kwargs-emit pattern shown in
`examples/streaming_logger` and `examples/tracker` — crashed under real
MCP transport with TypeError, masked as "Error calling tool 'X'" under
`App(debug=False)`. `fastmcp.Context.info` has a narrow signature
(`message, logger_name=None, extra=None`); `StderrToolContext` had silently
widened it to `(msg, **fields)`, and the in-process test client hid the
divergence from every test path.

Repairs the contract by finishing the log free-function pattern that
`event` / `report` already used:

### Added

- **`a2kit.log.log(ctx, level, msg_or_instance, **fields)`** — plus
  `info` / `warning` / `error` / `debug` aliases. Both forms (string +
  typed instance) share the `_typed_event_to_payload` helper with
  `event`, so coercion rules can't drift.

### Changed (breaking)

- **`StderrToolContext.info/warning/error/debug` narrowed** to fastmcp's
  exact signature — kwargs form removed. Migrate to `a2kit.log.log(...)`
  or wrap kwargs in `extra=`.

### Test gate

- Two-axis contract test (`tests/test_context_surface.py`): name
  coverage (legacy) + signature-binding registry `CTX_CALL_SHAPES` (new,
  load-bearing). Every call shape in `tests/` + `examples/` binds
  against both Context impls.
- End-to-end repro (`tests/test_field_logging_mcp_path.py`) using real
  `fastmcp.Client(transport=server)` — today's bug fails this; new code
  passes.
- `ty check examples/` joins `make lint` (0 errors after migration, was 14).
- 723 → 728 tests (+2 MCP-path probes, +1 log kwarg render, +2
  architectural invariants).

Tier 2/3/4 of the Context-shape divergence (13 more drifting methods)
captured as follow-ups in `openspec/changes/align-context-method-signatures/`
and `openspec/changes/rebuild-test-client-on-real-context/`.

## 0.27.2 — CLI cold-start: schema gen no longer triggers mcp.types — 2026-05-12

The previous release deferred `mcp.types` from module-load time but `--schema`
still triggered it via `meta.annotations.model_dump(...)`. Schema generation
now uses the stored kwargs dict directly, skipping the pydantic build entirely.

### Added

- **`A2KitMeta.annotations_as_dict()`** — returns the annotation kwargs in
  `ToolAnnotations` wire shape without constructing the pydantic object.
  Used by CLI schema gen (`packages/cli/schemas.py`) and MCP wire projection
  (`packages/mcp/server.py:_meta_to_dict`). The lazy `meta.annotations`
  property is unchanged for consumers that genuinely need the typed object.

### Performance

CLI cold-start (median over 15 runs, M1 Mac):

| Scenario | v0.27.1 | v0.27.2 | Δ |
|---|---:|---:|---:|
| `<app> --help` | 138ms | 139ms | flat |
| `<app> tool ping` | 138ms | 137ms | flat |
| `<app> tool hello` (DI) | 139ms | 140ms | flat |
| `<app> tool ping --schema` | 612ms | 137ms | **-78%** |

All CLI paths now run in the 127-146ms band. The `mcp.types` import is
fully off the cold-start path; only `<app> serve` (MCP transport) pulls it.

## 0.27.1 — CLI cold-start: defer mcp.types import — 2026-05-11

CLI tool invocations (`<app> --help`, `<app> <router> <tool>`) now skip the `mcp.types` / fastmcp / anyio / httpx imports entirely. Cold-start drops ~75% on the common case.

### Changed

- **`A2KitMeta.annotations` is now a lazy property.** The verb decorators (`@a2kit.read/write/list_/tool`) store annotation kwargs in `_annotations_kwargs` / `_annotations_explicit` at decoration time; `meta.annotations` constructs the `ToolAnnotations` instance on first read. Behavior is unchanged from the consumer's view; the field is still readable as `meta.annotations`.
- **`a2kit.tool` no longer imports `mcp.types` at module load.** `ToolAnnotations` lives under `TYPE_CHECKING`; only consumers that read `meta.annotations` (MCP schema gen, `--schema` flag) pay the import cost.

### Performance

CLI cold-start (median over 25 runs, M1 Mac):

| Scenario | v0.27.0 | v0.27.1 | Δ |
|---|---:|---:|---:|
| `<app> --help` | 544ms | 138ms | -75% |
| `<app> tool ping` (no DI) | 510ms | 138ms | -73% |
| `<app> tool hello` (DI singleton) | 610ms | 139ms | -77% |
| `<app> tool ping --schema` | 669ms | 761ms | +14% (materializes annotations) |

`<app> serve` (MCP transport) is unaffected — it needs the full mcp stack.

### Notes

- No API breakage. `meta.annotations.readOnlyHint` still works exactly as before; first access lazily imports `mcp.types`.
- The MCP wire-output projection (`packages/mcp/server.py:_meta_to_dict`) updated to materialize the lazy annotations into the wire dict (transparent to consumers).

## 0.27.0 — DI sync + container relocation + DI-aware lifecycle (breaking) — 2026-05-11

This release shrinks the DI substrate, removes the `connection` magic name from core, and makes lifecycle hooks DI-aware. The container is now a small synchronous library that knows nothing about specific features. Async resource initialization moves out of DI factories into resource classes (lazy-init pattern, documented in README "Resource pattern" section).

### Breaking

- **`packages/connections/container.py` is gone.** The DI container lives at `a2kit.packages.di.Container`. All imports update: `from a2kit.packages.connections.container import Container` → `from a2kit.packages.di.container import Container`.
- **DI factories MUST be synchronous.** `app.singleton(T, async_factory)` and `app.provide(T, async_factory)` raise `ValueError` at registration. Move async opens into resource classes (see README "Resource pattern").
- **`Container.resolve` is synchronous.** The async `resolve` method and `resolve_sync` are both deleted; `SyncResolveUnavailable` is gone. There is one resolve method, sync.
- **`Container.resolve` no longer accepts `connection=`.** Connection-string resolution moves to a dispatch hook in `packages/connections/dispatch.py`. The container has no notion of "connection".
- **`Container.partition_kwargs` returns `(wire, injectable)` — two-tuple, not three.** `needs_connection` is gone; use the generic `Container.wire_scopes_used_by(fn)` instead.
- **Lifecycle handler signature changed.** Old `(app: App)` is removed. Handlers take typed DI kwargs (`async def _open(state: AppState)`); resolution happens through the container the same way `@health_check` does it. The legacy `_app` parameter is no longer supplied.
- **`App.container()` returns `Container` (non-Optional).** Drops the `is None` guards at every consumer site. Container is eager-initialized in `App.__init__`.
- **`App._reject_singleton_connection_dep` is gone.** The sync-only rule transitively rejects connection-dependent factories.

### Added

- **`a2kit.packages.di`** — new home for the DI container. Module is feature-agnostic; no `"connection"` or other feature names appear anywhere in its code (enforced by `test_container_source_has_no_feature_names`).
- **`Container.register_wire_scope(name, *types)` and `Container.wire_scopes_used_by(fn)`** — generic primitive for "wire-routed string parameters". Consumer packages register a scope by name; schema gen consults the container generically. `connections` registers `"connection"` as one such scope.
- **`Container.apply_kwargs(fn, wire, *, pre_resolved=None)`** — pre_resolved cache lets consumer dispatch hooks seed values that the container should treat as already-resolved (instead of calling the factory).
- **`a2kit.packages.connections.dispatch`** — async dispatch hook factory that awaits `store.load(connection)` and substitutes typed configs into the container's per-call cache before sync resolution runs.

### Migration

A2kit consumers (a2web etc.) migrate by:

1. Removing the `_app: a2kit.App` parameter from `@on_startup`/`@on_shutdown`; replace with the typed kwargs the hook actually needs (e.g. `state: AppState`).
2. Converting async singleton/provide factories to sync. Move the async resource open into the resource class itself (lazy-init pattern from README).
3. Removing `Optional` from resource handles on AppState; locks move inside resources.
4. Removing any `_app.container().resolve(AppState, connection=None)` dance from hooks; the DI is automatic.

### Notes

- ~600 LOC deleted across the container, app.py, and consumer surfaces.
- Container: 540 → ~200 LOC (still has chain resolution; was further deleted).
- Test count went from 716 (v0.26) → 719 with broader behavior coverage of the new dispatch path.

## 0.26.1 — a2web feedback round 4 (additive ergonomics) — 2026-05-11

### Added

- **Typed `a2kit.log.event(ctx, instance)`** — the free function now accepts
  a class instance as its second positional argument. Name defaults to
  `type(instance).__name__`; payload derives via `model_dump(mode="json")`
  (pydantic), `dataclasses.asdict` (dataclass), or `vars(instance)` fallback.
  `Enum` field values are coerced via `.value`. Optional `name=` kwarg
  overrides the default class-name on the typed path. The legacy
  `event(ctx, "name.string", **kwargs)` form is unchanged.
- **`a2kit.testing.null_context()`** — a no-op `ToolContext`-shaped shim for
  unit-testing internal phase functions that bypass
  `a2kit.testing.client(app)`. Every wire method (logging, progress, event
  emit, report, sample, list_*) is a silent no-op. Production code can take
  `ctx: a2kit.ToolContext` (non-Optional) and tests construct the shim instead
  of passing `None`.
- **`a2kit.Param("description")` positional shorthand** — equivalent to
  `a2kit.Param(description="description")`. Cosmetically shorter at the
  `Annotated[T, Param(...)]` call site for one-line descriptions. Passing
  both the positional and the `description=` kwarg raises `TypeError`.

### Notes

- Pure additive. No breaking changes. Consumers writing the typed-event
  flattener shim (a2web's `_event_payload`, ~25 LOC) can delete it.
- README sections "Per-parameter descriptions" and "Logging + progress +
  events + reports" updated to document the new shapes. New "Null context
  for internal phase tests" subsection under Testing.

## 0.26.0 — a2web feedback round 3 (router-as-plugin + Surface + log sinks) — 2026-05-11

### Added

- **`Router` is now the unit of installation.** Optional class attributes
  on a Router subclass — `providers = (...)`, `on_startup`/`on_shutdown`
  methods, and a custom `install(self, app)` hook — are honored by
  `app.add_router(r)`. There is no separate "plugin" type; one verb
  installs everything the Router declares. Plain Routers (tools only)
  behave exactly as before.
- **`a2kit.Surface`** — `Flag` enum (`CLI`, `MCP`, `ALL`). Pass to any
  verb decorator (`@a2kit.read(surfaces=Surface.CLI)`) to constrain
  which transports the tool mounts on. CLI builder and MCP server
  filter by `Surface` membership at mount time. Default `Surface.ALL`.
- **`a2kit.packages.connections.connections(*conn_types)`** — Router
  factory that installs typed providers honestly via `Router.install`.
  Use alongside the existing `connections_cli(...)` for the full
  surface: `app.add_router(connections(X)); app.add_cli(connections_cli(X))`.
- **`A2K-SURFACE-EXPLICIT` lint rule** — fires when a credential-named
  tool (`login`, `logout`, `auth_*`, `rotate_key`, `issue_token`, etc.)
  defaults to `Surface.ALL`. Suppress with explicit `surfaces=` kwarg.
- **`app.log.add_sink(sink)`** — register an in-process observer for
  every log emission (events and reports), on every transport. Sinks
  are async callables receiving an `logging.LogRecord` payload (kind, name,
  payload dict, elapsed_ms, tool_name, ctx). Fan-out is sequential and
  best-effort; sink exceptions are caught and logged on `a2kit.log.sinks`.
  Replaces the double-emit pattern OTel/Datadog/audit-log integrations
  needed before.
- **`a2kit.log.logging.LogRecord`** + **`a2kit.log.logging.Handler`** — public types
  for sink implementers.
- **OPERATIONAL_CONTRACTS Q2** rewritten with four prescribed
  `anyio.fail_after` patterns (single-budget, nested multi-stage,
  silent degrade with `move_on_after`, cleanup-on-timeout).
- **OPERATIONAL_CONTRACTS Q6** rewritten: heartbeat pattern for
  visibility during long phases, `add_sink` API documentation,
  cancellation contract for sinks. Cross-linked from
  `docs/SPIKE_LOG_CANCELLATION.md`.

### Changed

- **README leading example** switched to imperative composition; the
  fluent chain is now documented as a "shorthand for compact composition
  in tests and small scripts." Subsystem-crossing installs (router,
  CLI, providers, lifecycle) are visible line-by-line.
- **`examples/tracker/server.py`** ported to the canonical two-call form
  (`add_router(connections(X))` + `add_cli(connections_cli(X))`).

### Deprecated

- **Hidden auto-install of connection providers via
  `add_cli(connections_cli(X))`.** Emits `DeprecationWarning` pointing at
  the new two-call form. The auto-install path will be removed in v0.27.

## 0.25.0 — a2web feedback round 2 (test client + annotations + health + descriptions + ops contracts) — 2026-05-10

### BREAKING

- **Antipattern #1 lint broadened.** `_check_return` previously rejected only
  `-> str` returns; now also rejects `int`, `float`, `bool`, `bytes`, and
  `None` (both `type(None)` and the literal `None` annotation form). Tools
  must return a Pydantic model, dict, or list/Page of either. Pre-1.0
  latitude — fail-at-import is the loudest signal possible. Migration: wrap
  primitive returns in a typed shape (`-> dict[str, int]` instead of `-> int`).

### Added

- **`a2kit.testing.client(app)`** — async-context-manager test client that
  runs the **full dispatcher** in-process. Captures events, progress,
  logs, and reports for assertions. Lifecycle hooks fire. `render_as(fmt, val)`
  for wire-format checks. `tools()` for descriptor introspection.
  `connection=` passthrough through the same DI chain CLI/MCP transports use.
- **MCP `ToolAnnotations` kwargs on verb decorators** — `@a2kit.read` /
  `@a2kit.write` / `@a2kit.tool` accept `idempotent`, `open_world`,
  `destructive`, `title`. Conservative defaults (idempotent=False,
  open_world=False, destructive=False on read / True on write).
  `@a2kit.read(destructive=...)` raises `TypeError` — read tools are
  non-destructive by spec. Explicit `annotations=ToolAnnotations(...)` is
  the escape hatch.
- **`App(name, health_tool=False, debug=False)` constructor flags.**
  When `health_tool=True`, a built-in `_meta.health` tool is registered.
  `debug=True` enables tracebacks in error envelopes (currently flag-only).
- **`@app.health_check` decorator** — register sync or async readiness
  probes. Probes can take DI kwargs (resolved through the App's dispatch
  hook). Aggregates into `{status: "ok"|"degraded", version, checks: [...]}`.
- **`a2kit.HealthResult`** — `status: Literal["ok", "fail"]` + optional
  `reason`. Classmethods `ok()` / `fail(reason)`.
- **`_meta.*` reserved namespace.** User tools cannot claim names starting
  with `_meta.` — built-in protocol-meta tools (currently just `_meta.health`)
  own that namespace. Decoration-time `ValueError`.
- **`a2kit.Param(description=..., **extras)`** — annotation marker for tool
  kwargs. Returns a `pydantic.Field` info object so the description flows
  through `Annotated[T, Param(...)]` to both the MCP input schema (via
  pydantic) and click `--option HELP` text (via the CLI builder's
  `description_of` helper).
- **Docstring → tool description contract.** First non-empty line of the
  docstring becomes the tool's short description; the full PEP-257-dedented
  body becomes the long help. CLI strips markdown for terminal rendering
  (`_strip_md` handles `**bold**`, `*italic*`, `` `code` ``,
  `[text](url)` → `text (url)`). MCP forwards the body verbatim
  (markdown intact).
- **`OPERATIONAL_CONTRACTS.md`** — documented contracts for cancellation
  propagation (Q1), per-tool timeouts (Q2 — recommended `anyio.fail_after`
  pattern), multi-App isolation (Q3 — production-supported), dev auto-reload
  (Q4 — out of scope), error envelope (Q5 — MCP `-32603` / CLI traceback;
  `App(debug=True)` toggles wire traceback), streaming output (Q6 —
  deferred).

### Changed

- **`_build_descriptors` uses `meta.tool_name`** instead of raw
  `fn.__name__` — honors the decorator's `name=` override so tools with
  explicit names (like the built-in `_meta.health`) register under the
  intended descriptor name.

## 0.24.0 — fastmcp.Context passthrough + app lifecycle + DI ergonomics + return-type discipline (a2web feedback round 1) — 2026-05-10

### BREAKING

- **`a2kit.ToolContext` is now `fastmcp.Context`.** The narrow `ToolContext`
  Protocol that ran on a wrapper adapter is gone — tools that annotate
  `ctx: a2kit.ToolContext` now receive the live `fastmcp.Context` on the MCP
  transport, and a Context-shaped CLI stub on the CLI transport. The lazy
  `__getattr__` on `a2kit` resolves `ToolContext` to `fastmcp.Context` on
  first access (cold-start invariant preserved: bare `import a2kit` still
  doesn't pull fastmcp).
- **All Context logging methods are async.** `ctx.info` / `ctx.warning` /
  `ctx.error` / `ctx.debug` / `ctx.log` / `ctx.report_progress` are async on
  both transports (matching `fastmcp.Context`). Sync callers will silently
  produce a coroutine and log nothing — always `await` them.
- **`ctx.event(...)` and `ctx.report(...)` removed from the Context API.**
  These moved off the Context class and live as free functions in
  `a2kit.log`: `await event(ctx, "name", **payload)` /
  `await report(ctx, payload)`. Per-call state (kill-switches, declared
  report type) flows through a `contextvars.ContextVar` set by the runtime
  dispatch site, so the free functions Just Work on either transport.
- **`FastMCPContextAdapter` and `bind_context` deleted.** No public consumers
  in-tree; both were private wiring for the now-defunct adapter pattern.
- **`a2kit.runtime` module deleted** (it held the narrow Protocol).

### Migration

```python
# --- ctx logging methods are async now ---
async def my_tool(*, ctx: a2kit.ToolContext) -> dict:
    ctx.info("hello", count=3)            # before  (silent on MCP, sync on CLI stub)
    await ctx.info("hello", count=3)      # after   (works on both transports)

# --- ctx.event / ctx.report → free functions ---
from a2kit.log import event, report
async def my_tool(*, ctx: a2kit.ToolContext) -> dict:
    await ctx.event("import.started", n=10)         # before
    await event(ctx, "import.started", n=10)        # after

    await ctx.report(BatchReport(...))              # before
    await report(ctx, BatchReport(...))             # after

# --- typed event registry (new) ---
class StepStarted(BaseModel):
    step: int; total: int
app.log.events.register(StepStarted, progress=lambda e: (e.step, e.total))
async def run(*, ctx: a2kit.ToolContext):
    await app.log.events.emit_typed(ctx, StepStarted(step=1, total=3))

# --- a2web pattern (singletons + lifecycle) ---
def register_state(app, *, settings=None):
    state = AppState(settings=settings or get_settings(), ...)
    atexit.register(_atexit_close, state)
    app.provide(AppState, lambda: state)

# After
@app.singleton(AppState)
def _build_state():
    return AppState(settings=get_settings(), ...)

@app.on_startup
async def _open_resources(app):
    state = app.container().resolve_sync(AppState)
    state.sqlite = await open_sqlite(state.settings)

@app.on_shutdown
async def _close_resources(app):
    state = app.container().resolve_sync(AppState)
    if state.sqlite is not None:
        await state.sqlite.close()
```

### Cold-start budget note

- Bare `import a2kit` invariant unchanged: stays under 100ms with no fastmcp
  in `sys.modules` (the `Context` re-export is lazy via `__getattr__`).
- User-app `<app> --help` triggers fastmcp import on first access to
  `a2kit.ToolContext` from a tool annotation. Fastmcp's own import cost
  (~1s on a typical machine) dominates total wall-clock; the a2kit + click
  - builder overhead on top stays under 200ms (parametrized in
  `tests/test_cold_start.py::test_user_app_help_a2kit_overhead_under_200ms`
  across the streaming_logger, elicitation, and sampling examples).

### Added

- **`a2kit.log.event` / `a2kit.log.report`** — protocol-neutral free functions
  replacing the deleted `ctx.event` / `ctx.report` methods. Take any
  `fastmcp.Context`-shaped object as the first arg; route via the per-call
  `bind_call_scope` contextvar set by the dispatch site.
- **`a2kit.log.EventRegistry`** + **`app.log.events`** — typed event registry.
  Register Pydantic event models once (optionally with a progress callback);
  emit instances via `await app.log.events.emit_typed(ctx, evt)`. Handles
  `model_dump(mode="json")` (datetime → ISO etc.), routes through `event()`,
  forwards to `ctx.report_progress(...)` when a callback is registered.
  Re-registration is last-write-wins.
- **`a2kit.log.format_condensed_line(level, msg, fields, elapsed_ms)`** — single
  canonical log-line renderer used by both the CLI stub and any future
  transport. `TEXT_CAP=60` with `…` elision applied to `msg` on both CLI
  and the MCP `message` field.
- **`a2kit.signature.resolve_hints(fn)`** — single fallback for
  `get_type_hints` failures across the six core sites that previously rolled
  their own try/except. Logs WARN once per `__qualname__` on failure,
  returns `{}`. Cold-start preserving (no eager fastmcp import).
- **`StderrToolContext` full `fastmcp.Context` surface**: per-instance state
  (`set_state`/`get_state`/`delete_state`), `read_resource` (file:// only,
  text + binary), primitive `elicit` loop (str/int/float/bool/enum), and
  `MCPOnlyError` for `sample`/`list_resources`/`list_prompts`/`get_prompt`/
  `list_roots`/`send_notification`. `send_log_message` mirrors the MCP-side
  structured-log primitive.
- **`a2kit.packages.cli.context.MCPOnlyError`** — raised by the CLI stub for
  methods that have no client-side facility. Constructor: `(method, hint=None)`.
- **`examples/elicitation/`**, **`examples/sampling/`**, **`examples/typed_events/`** — three new examples + tests covering elicit on stdin, sample raising on CLI, and typed-event registry usage.
- **`A2K-LOCAL-RETURN-MODEL` lint rule** — static AST check that fires when a
  tool's return annotation references a `pydantic.BaseModel` subclass defined
  inside a function, classmethod, or closure (including generic carriers like
  `Page[Result]`, `list[Result]`). Skips `if TYPE_CHECKING:` blocks. Closes
  the gap where the rule was documented in `ANTIPATTERNS.md` but not actually
  shipped.
- **Decoration-time return-type-scope check** — `_check_return_scope` in
  `src/a2kit/tool.py` raises `InvalidToolReturnTypeError` at import time when
  a tool's return-type class has `<locals>` in `__qualname__` (the CPython
  signal for "defined in a function body"). Pairs with the lint rule for
  belt-and-suspenders coverage.
- **`a2kit.testing.peek(app, T)`** — one-line wrapper over
  `Container.resolve_sync(T)` for tests. Re-exported from `a2kit.testing` and
  `a2kit.packages.testing`.

- **`App.on_startup(handler)` / `App.on_shutdown(handler)`** — register async or
  sync lifecycle handlers invoked exactly once before the first tool dispatch
  / after the last. Both methods double as decorators (`@app.on_startup`).
  Startup runs in registration order; shutdown in reverse (LIFO unwind).
  Startup failures abort cleanly with no shutdown handlers run; shutdown
  failures are logged via `a2kit.lifecycle` (ERROR) and swallowed so the
  original exit reason is preserved.
- **`App.singleton(type_, factory=None)`** — register a factory whose result is
  cached on the App for its lifetime. Method form (`app.singleton(T, fn)`) and
  decorator form (`@app.singleton(T)`) both supported. Factories must NOT
  depend on `connection` (directly or transitively) — `singleton` raises
  `ValueError` at registration, naming the offending parameter or chain.
  Async factories are coalesced under a lazy `asyncio.Lock` so concurrent
  first-resolves await exactly once.
- **`App.has_singleton(type_)` / `App.singletons()`** — introspection mirrors
  parallel to `has_provider` / `container().providers()`. Unresolved entries
  carry the public sentinel `a2kit.UNRESOLVED`.
- **`Container.resolve_sync(type_, *, connection=None)`** — synchronous resolve
  for chains where every factory is sync. Raises `SyncResolveUnavailable`
  (with `async_link` naming the first async factory) if the chain hits async.
  Singleton-cached values short-circuit as sync regardless of original
  factory.
- **CLI lifecycle integration** — `a2kit.run(app)` invokes registered handlers
  inside the same `asyncio.run` that wraps the tool body, so resources opened
  in startup are bound to the loop the tool runs in (no fresh-loop dance).
- **MCP lifespan integration** — `build_mcp_server(app)` derives a `lifespan=`
  context manager from the App's handlers and merges with any user-provided
  `lifespan=` kwarg (a2kit-startup → user-enter → body → user-exit →
  a2kit-shutdown).

### Changed

- **`Container.resolve(connection=...)` is now optional** (was required
  keyword) — connection-less apps no longer have to pass `connection=None`
  everywhere. No behavior change for connection-using apps.
- **`a2kit.log.event` and `a2kit.log.report` first args are positional-only**
  (`async def event(__ctx, __name, /, **payload)`). Lets typed event payloads
  include keys like `name` / `ctx` without colliding. All existing callers
  pass these positionally already.
- **A2K-IMPORT-DISCIPLINE allowlist** extended to include
  `src/a2kit/packages/cli/context.py` (lazy fastmcp import inside `elicit()`).

### Removed

- **`a2kit.runtime` module** (held the narrow `ToolContext` Protocol).
- **`a2kit.packages.mcp.context`** module (`FastMCPContextAdapter`,
  `bind_context`).
- **`ctx.event(...)` and `ctx.report(...)`** methods on the Context API. Use
  `await event(ctx, ...)` / `await report(ctx, ...)` from `a2kit.log`.

## 0.23.0 — type-driven format routing: TSV / JSON / page-tsv (TOON dropped) — 2026-05-09

### Changed (BREAKING)

- **Type-driven format routing.** `format_hint="auto"` (the default) now
  consults the tool's pre-computed `ToolDescriptor.format_hint`, derived once
  at `app.add_router()` from the resolved return-type annotation. Tools
  declared `-> list[ScalarOnlyModel]` route to **TSV** (~30% fewer tokens than
  JSON for the dominant tracker shape — see K research R122). Tools declared
  `-> Page[T]` (where `T` is scalar-only) route to a hybrid **`page-tsv`**
  format: JSON envelope, embedded TSV string for `items`, with an
  `_items_format: "tsv"` discriminator. All other shapes (single models,
  dicts, scalars, untyped, `Union`, deep nesting) route to JSON.
- **TOON removed.** `format_hint="toon"` raises `ValueError`. The `toon`
  module, `encode_toon`, `toon_or_json`, the `toon-format` dependency, and
  the `TOONSnapshotExtension` syrupy helper are gone. Empirical R122 token
  benchmark (cl100k_base / o200k_base) showed TOON has no win zone — TSV beats
  it by 4-36% on tabular shapes; JSON beats it by 16-20% on shapes with list
  or nested-dict columns.
- `Page` is now `class Page(BaseModel, Generic[T])` (was `@dataclass`). Bare
  `Page(items=[...], next_cursor="x")` construction stays compatible.
  Subclasses can add fields naturally: `class SearchPage(Page[Task]): total: int`.
- `App.tool_descriptors() -> list[ToolDescriptor]` is the typed introspection
  surface. `App.tools()` continues to return bound callables for back-compat.

### Migration

- Tools already typed (`-> list[Task]`, `-> Page[Task]`) get the new behavior
  with no source change. Token counts drop on tabular outputs.
- Untyped tools route to JSON (no behavior change vs. the legacy `auto`
  fallback to JSON).
- If you depended on TOON output, switch to JSON. The benchmark shows JSON is
  cheaper on every shape where TOON was previously chosen.

### Fixed

- **CLI formatter renders pydantic `BaseModel` returns** in both JSON and TOON
  paths. Previously TOON emitted `null` (with an `Unsupported type` warning) and
  JSON fell back to `default=str` producing a quoted model repr; the MCP path
  worked because FastMCP normalizes pydantic itself. `format_response` now
  normalizes `BaseModel` (including models nested in lists/dicts) via
  `model_dump(mode="json")` at the formatter boundary before either encoder
  runs. Auto-format selection (`toon_or_json`) sees the normalized payload, so a
  model whose dumped form has list/dict fields correctly picks TOON. No-op for
  non-pydantic inputs (byte-identical output).

## 0.22.0 — ergonomic round: typed DI, consolidated list_, class-attr enrichers — 2026-05-09

Round three on top of v0.21's de-magic posture, focused on developer ergonomics
without re-introducing magic. Four wins, all expressible as plain Python:

- **`@a2kit.list_(*default_fields, page_size=None, selectable_fields=None)`** absorbs
  list-view projection settings. The standalone `@lists(...)` decorator and the
  `a2kit.packages.mcp.lists` module are removed. When `selectable_fields` is omitted,
  the framework derives it from the tool's `list[T]` return type — no redundant
  enumeration of fields the Pydantic model already declares.
- **Class-attribute `enrichers` + optional `def enrich(self, exc)` method** replace
  the per-method `@enriches(...)` decorator. The `a2kit.packages.enrichers` module
  is removed. Resolution: instance method first, then class list, first non-None
  return wins. Enricher functions now return `str | None` (the framework rebuilds
  the exception with the enriched message); the old `(exc, tool_name) -> Exception`
  shape is gone.
- **Request-scoped DI via `App.provide(T, factory=None)`**. A typed container in
  `packages/connections` resolves tool-method kwargs annotated with provider types
  (`store: TrackerStore`, etc.) per call. When `factory` is omitted, the class
  itself is the factory and the container introspects `__init__`. Tool authors stop
  writing `__init__(self, get_store: GetStore)` factories; routers can be parameterless.
  `add_cli(connections_cli(ConfigT))` auto-installs a typed provider for `ConfigT` —
  no second `provide(ConfigT, ...)` call required.
- **Hybrid Router slug derivation**. `class TasksRouter(a2kit.Router)` derives slug
  `"tasks"` automatically (strip a single trailing `Router`, lowercase). Explicit
  `name = "..."` still wins. Collisions across routers in one App raise at build
  time. The de-magic-2 antipattern entry on slug auto-derivation is retracted with
  new reasoning: a single documented suffix-strip rule is convention, not magic.

The agent-facing wire schema strips injectable kwargs (`store: TrackerStore` is not
in the MCP/CLI input schema) and auto-includes `connection: str` whenever the
injectable graph reaches the connection-config provider. Cold-start budget unchanged.

### Migration

```python
# Before (v0.21):
class TasksRouter(a2kit.Router):
    name = "tasks"

    def __init__(self, get_store: GetStore) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.list_()
    @lists(default_fields=("id", "title"), page_size=20, selectable_fields=(...))
    @enriches(tracker_404_enricher)
    async def list_tasks(self, *, connection: str) -> list[Task]:
        store = await self.get_store(connection)
        ...

# After (v0.22):
class TasksRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]
    # name auto-derived → "tasks"

    @a2kit.list_("id", "title", page_size=20)
    async def list_tasks(self, *, store: TrackerStore) -> list[Task]:
        ...

app = (
    a2kit.App("tracker")
    .add_router(TasksRouter())
    .provide(TrackerStore)                       # class-as-factory
    .add_cli(connections_cli(TrackerConfig))     # auto-installs TrackerConfig provider
)
```

## 0.21.0 — de-magic round 2: stacked decorators, lint-enforced core purity — 2026-05-09

Second pass at trimming framework magic from the v0.20 surface. The verb decorators
(`@a2kit.read/write/list_/tool`) drop their feature kwargs (`enricher=`, `list_view=`,
`report=`, `router_slug=`); each feature now lives in its own package and attaches
via a stacked decorator that writes into `A2KitMeta.extra`. The Router class no
longer derives slugs by string surgery, and the CLI builder no longer monkey-patches
`click.Group.main` or relies on a module-level `ContextVar`.

A senior-Python read of `src/a2kit/*.py` now finds no references to "connection",
"enricher", "list_view", "report_type", "report_schema", or "router_slug" — verified
by a new lint rule (`A2K-CORE-CLEAN`) that runs in CI as a hard gate.

### Decorator surface

- **`@a2kit.read/write/list_/tool`** accept only `(name, tags, annotations)`. The
  four feature kwargs are removed.
- **Stacked feature decorators** replace them. Order: verb decorator outermost,
  feature decorators below.
  - `from a2kit.packages.enrichers import enriches` — `@enriches(my_enricher)`
  - `from a2kit.packages.mcp.lists import lists, ListViewSettings` — `@lists(default_fields=..., page_size=...)`
  - `from a2kit.packages.mcp.reports import reports` — `@reports(BatchReport)`
- **`A2KitMeta.extra: dict[str, Any]`** is the single extension point. Feature
  decorators write namespaced keys (`a2kit.enricher`, `a2kit.list_view`,
  `a2kit.report_type`, `a2kit.report_schema`, `a2kit.router_slug`).

### Router naming

- `Router.slug` resolves to `name=` constructor arg → `cls.name` class attribute →
  `type(self).__name__` **verbatim**. No suffix stripping, no camelCase split, no
  case conversion.
- Routers without `name` set get an unsightly slug — that's the forcing function.
  The tracker example sets `name = "projects"` / `name = "tasks"` explicitly.

### Router internals

- `Router._collect_methods` walks bound members instead of `type(self).__dict__`.
  Tools register as bound methods; `_bind_if_method` and the consequential manual
  rebind are gone from the CLI builder.

### CLI builder

- `_wrap_main_with_app_ctx` deleted. `_APP_CTX` ContextVar deleted. The schema
  command and the lazy `serve` command are factories that close over the active
  `App` directly. `LazyGroup` now stores `Callable[[], click.Command]` factories
  instead of `module:attr` import strings.

### Connections

- `WriteNotAllowed` moves to `a2kit.packages.connections.exceptions` — it was the
  last connection-aware identifier in core. Core now grep-clean.

### Lint

- **`A2K-CORE-CLEAN`** (new, hard gate) — rejects feature identifiers in
  `src/a2kit/*.py` outside `packages/`.
- **`A2K-EXTRA-NAMESPACE`** (new, hard gate) — rejects `meta.extra[<key>] = ...`
  writes whose key isn't `a2kit.*` or a `<package>.*` prefix.
- **`the removed report-type lint rule`** rewritten to look for stacked `@reports(ReportT)`
  rather than the dropped `report=` kwarg.

### Migration from 0.20

```python
# 0.20
@a2kit.read(enricher=my_enricher, report=BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...

# 0.21
@a2kit.read()
@enriches(my_enricher)
@reports(BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...
```

```python
# 0.20: from a2kit.exceptions import WriteNotAllowed
# 0.21: from a2kit.packages.connections.exceptions import WriteNotAllowed
```

```python
# 0.20: class TasksRouter(a2kit.Router): pass            # slug = "tasks" (auto)
# 0.21: class TasksRouter(a2kit.Router): name = "tasks"  # slug = "tasks" (explicit)
```

### Numbers

- Tests: 441 passing (was 428)
- Coverage: 93.52% (gate ≥92%)
- Cold-start: ~13ms (unchanged)

## 0.20.0 — protocol-agnostic core, plain-Python composition — 2026-05-09

Clean break from the v0.19 architecture. Core a2kit is a fat decorator on top of
FastMCP — `App`, `Router`, `@a2kit.read/write/list_`, `ToolContext` — and nothing
else. Connections, formatter, select grammar, lint, MCP/CLI adapters, testing
helpers, and OTel middleware live under `a2kit.packages.*` and load only when
imported. `import a2kit` measured at ~13 ms; FastMCP is confined to
`a2kit.packages.mcp`.

The release shipped through several intermediate spikes on `v1-thin-core`
(protocol-agnostic core, log streaming reports, class-based DI, pluggable plugin
architecture). The final shape collapses those experiments into the simplest
form that works: **constructor injection, three named composition verbs, no
sentinels, no plugin protocol, no class-as-key DI**.

### Composition

- **`a2kit.App(name)`** with three named verbs: `add_router(router)`,
  `add_cli(group)`, `add_mcp_middleware(middleware)`. No polymorphic dispatch.
- **`a2kit.Router`** is a plain Python class — pass factories via `__init__`,
  store on `self`, call from each tool method. The framework introspects
  nothing.
- **`a2kit.run(app, argv=None)`** — single console-script entry. Delegates to
  the lazy CLI builder; non-`serve` paths never load `fastmcp`.

### Verbs and metadata

- **`@a2kit.tool / read / write / list_`** stamp `A2KitMeta` (frozen
  dataclass) onto the function. Verb maps to `mcp.types.ToolAnnotations` +
  tags. Optional `enricher=fn` per-tool wraps the call in
  `try / except → enricher(exc, tool_name)`.
- **`@a2kit.read(report=ReportT)`** declares the typed mid-flight chunk type.
  `ctx.report(...)` validates against it; the schema dump exposes
  `reportSchema`.
- **`-> str` return** is rejected at decoration time
  (`InvalidToolReturnTypeError`) — return `dict` or a Pydantic model.

### `ToolContext` — four channels for mid-flight communication

- `ctx.info / warning / error / debug(msg, **kw)` — process telemetry.
- `await ctx.report_progress(i, n)` — numeric progress.
- `await ctx.event(name, **payload)` — typed narrative events.
- `await ctx.report(payload)` — typed result chunks (requires
  `report=ReportT` on the decorator).

All emissions carry an elapsed `+s.mmm` timestamp. CLI: `[ +s.mmm LEVEL] msg
key=val` on stderr. MCP: `notifications/message` with `data.elapsed_ms: int`
and a `data.a2kit_kind` discriminator.

**Kill-switch.** `--no-reports` / `--no-events` flags per invocation;
`app.set_log(reports=False, events=False)` programmatic; env `A2KIT_LOG__ENABLED=false`
process-wide. Most-specific layer wins.

### Connections

- **`a2kit.packages.connections`** exports `ConnectionConfig` (pydantic-settings
  base), `ConnectionStore` (load/save with eager `${VAR}` / `op://`
  substitution), and `connections_cli(*types)` — a Click-group factory you wire
  via `app.add_cli(connections_cli(TrackerConn))`.
- Eager substitution: `${VAR}` and `op://...` resolve at `store.load(...)`,
  not at first tool call. Round-trip preserves placeholders — `store.save(cfg)`
  writes the original `${MY_TOKEN}`, never the resolved value.
- No `Connections` plugin class. No `Store[ConnT]` Generic. No DI sentinel.
  Stores are plain classes; users wire factories explicitly.

### Adapters

- **`a2kit.packages.mcp`** — `build_mcp_server(app, **fastmcp_kwargs) -> FastMCP`.
  The ONE place fastmcp imports.
- **`a2kit.packages.cli`** — `build_full_cli(app)` returns the
  progressive-disclosure CLI (one entry per Router; `schema`, `serve`, plus
  any `add_cli(...)`-attached subcommands).
- Cold-start contract: after `import a2kit`, `'fastmcp' not in sys.modules`.
  Verified by `tests/test_cold_start.py`.

### Listview kit

- **`@a2kit.list_(list_view=ListViewSettings(default_fields=..., page_size=...,
  selectable_fields=...))`** declares the projection contract. Middleware
  applies projection / pagination / CEL-based filtering on the in-memory
  result post-hoc. `--fields=`, `--page-size=`, `--cursor=`, `--filter=`
  available at the call site.

### Filter syntax — real CEL

- **`a2kit.packages.select`** wraps `cel-python` for filter compilation. Users
  pass real CEL: `--filter='priority=="high" && !done'`. `&&`, `||`, `!`,
  comparisons, member access, ternary — all supported by the underlying CEL
  engine. Legacy atom syntax is gone.

### Output formatter

- **`a2kit.packages.formatter`** — TOON / JSON normalization via `toon-format`.
  Default is TOON (token-efficient for agent contexts); pass `--format=json`
  to opt in. `--format=auto` heuristically picks JSON for flat dicts, TOON
  otherwise.

### Lint

- **`a2kit lint static <path>`** — AST-only rules, no imports of user code.
  Active rules: `A2K002`, `A2K003`, `A2K006`, `A2K008`, `A2K009`, `A2K011`,
  `A2K012`, `A2K013`, `A2K014`, `A2K-CONN-LIST-PLACEHOLDER`,
  `A2K-IMPORT-DISCIPLINE`, `the removed report-type lint rule`.
- **`a2kit lint runtime --import pkg:server`** — duck-typed checks on a built
  server (snapshot presence, per-tool budgets, similar-name detection).
- **`make lint` is a hard gate** for `ruff check`, `ruff format --check`,
  `ty check src/`, and `a2kit lint static`. The repo carries zero
  `# ty: ignore` comments — verified by `tests/test_type_correctness_gate.py`.

### Testing

- **`a2kit.packages.testing`** ships an `app` fixture (returns
  `a2kit.App("test")`), a `cassette` fixture (vcrpy wrapper),
  `TOONSnapshotExtension` (syrupy single-file extension), and
  `compute_schema(fn)`. There is no `make_test_app` helper — tests construct
  an `App` and call `add_router(...)` directly.

### Optional OTel adapter

- **`a2kit.packages.otel`** (install with `pip install 'a2kit[otel]'`) —
  middleware that wraps every tool call in a `mcp.tool.{name}` span and
  increments an `a2kit.tool.calls{tool, verb, status}` counter. Wire via
  `from a2kit.packages.otel import install; install(server)`. Lazy: a2kit
  core does not import `opentelemetry` at any point.

### Migration from v0.19

The v0.19 architecture is gone. Notable shape changes:

| v0.19 | v0.20 |
|---|---|
| `from a2kit.di import Depends` / `from uncalled_for import Depends` | constructor injection on `Router.__init__` |
| `Annotated[T, Depends(g)]` parameter | factory passed to router constructor |
| `*, conn: T = Depends(g)` parameter default | factory passed to router constructor |
| `app.run()` | `a2kit.run(app)` |
| `app.dependency_overrides[fn] = fake` | `App() + add_router(R(fake_factory))` |
| `make_test_app(routers, overrides=...)` | `App() + add_router(...)` directly |
| `from a2kit.contrib.connections import ...` | `from a2kit.packages.connections import ...` |
| `from a2kit.scaffold import Router` | `from a2kit import Router` |
| `from a2kit.testing import ...` | `from a2kit.packages.testing import ...` |
| `from a2kit.formatter import ...` | `from a2kit.packages.formatter import ...` |
| Lazy `${VAR}` / `op://` | Eager (resolves at `store.load(...)`) |
| Legacy filter atom syntax | Real CEL (`&&` / `\|\|` / `!`) |

### Install note

`toon-format` 1.0 has not yet shipped; v0.20 pins the working pre-release
exactly. Pass `--pre` if a fresh resolve bypasses the pin:

```bash
uv pip install --pre 'a2kit'
```

## 0.19.0.dev0 — 2026-05-08

**Fix-forward review pass on the v0.15 architecture.** No surface
changes; addresses two latent bugs and sweeps documentation drift.

### Latent bugs fixed

- **Multi-`ConnectionConfig` Depends params are now rejected at
  decoration time.** A tool declaring two `Annotated[T, Depends(...)]`
  params resolving to `ConnectionConfig` subclasses previously
  silent-picked the first one for `WriteEnforce` / OTel correlation.
  Raises `TypeError` with a clear message.
- **`connection=` shape now normalized through OTel / structlog.** A
  caller passing `connection=("p","e","d")` or
  `connection=["p","e","d"]` put the raw shape onto
  `ctx.state[STATE_CONNECTION_KEY]`, which then serialised
  inconsistently. Routed through `_resolve_connection_key` before
  stash so the span / log record always sees the canonical tuple form.

### Surface vestiges removed

- **`store=` parameter dropped end-to-end** from
  `Router.register_read` / `register_write`, the
  `_RegisterableRouter` Protocol, `Router._apply_bindings`, and
  `RouterRegistry.apply`. Routers stopped owning per-router stores in
  v0.15; this kept threading `store` through dead code paths.
  *Migration:* anyone with a hand-rolled Router implementing the
  structural `_RegisterableRouter` Protocol must drop the `store`
  parameter from `register_read` / `register_write` / `register_list`
  signatures. The framework no longer passes it.
- **`RouterRegistry.routers_with_stores(fallback_store=...)` →
  `ephemeral_store_pairs(store)`.** Renamed to spell out the actual
  purpose (the only consumer is the `--register` CLI path; nothing
  Router-owned).
- **`_CURRENT_RUNNER` ContextVar deleted** — only ever written, never
  read.

### Public API hardening

- **`App.get_store(conn_type) -> ConnectionStore[T]`** is the public
  store-lookup hook. Replaces `app._stores` private-attribute poking
  from `contrib/connections/_factory.get_conn_factory`. Match is
  exact-class identity, not `isinstance`.
  *Migration:* third-party contrib factories should replace
  ``next(s for s in app._stores if s.connection_class is T)`` with
  ``app.get_store(T)``. Subclasses of a registered conn type don't
  resolve to the parent's store — each class owns one store.

### Documentation drift

- Module docstrings rewritten for the v0.15+ surface
  (`a2kit/__init__.py`, `contrib/connections/__init__.py`,
  `contrib/connections/_helpers.py`, `tools/_connection.py`).
- **`a2kit.contrib.connections.make()` placeholder deleted** — it
  returned an unconsumed tuple and only existed as a syntax stub for
  an unbuilt SubApp surface. Migration note in `todo.md`.

### Tests

- Coverage stays at 100% (cov-fail-under=100 enforced).
- `tests/test_v19_latent_bugs.py` covers the two latent fixes.
- `tests/test_decorator_v15.py` listview / Passthrough assertions
  tightened (typed exception + Response shape).

## 0.18.0.dev0 — 2026-05-08

**Structured tool logging.** Adds `a2kit.get_tool_logger(name)` — a
structlog `BoundLogger` that shares the same `tool.name` /
`tool.connection` labels the OTel span carries, by reading them from
`structlog.contextvars`. A new logging middleware binds those keys for
the duration of each tool call (both async-chain and sync `@tool`
paths), so any log emitted from the tool body, plugin code, or
downstream middleware inherits the labels. Concurrent tool calls stay
isolated (per-task contextvars).

What's *not* in scope: trace_id/span_id injection into log records.
The kit binds labels only — for full trace correlation, hosts bridge
structlog→stdlib logging and enable OTel `LoggingInstrumentor`
themselves. The kit ships **no** structlog *configuration*
(processors, formatter, handler) for the same reason. structlog
imports are lazy.

(Plan-vs-impl note: the v0.17 ledger called the type a "structlog
`LoggerAdapter`" — that was a stdlib/structlog conflation. structlog's
`BoundLogger` is the actual contextvar-aware shape and is what shipped.)

`structlog>=24` added to runtime dependencies.

### FastMCP request-id spike — closed

Investigation: `Context.request_id` exists on FastMCP's Context but is
only injected when the tool declares a `Context`-typed kwarg.
Stamping it as `mcp.request_id` on the span would force a2kit to
import `mcp.server.fastmcp.Context` at runtime — contradicting the
v0.11 `FastMCPLike` Protocol design. Closed; finding + follow-up paths
captured in `todo.md`.

## 0.17.0.dev0 — 2026-05-08

**Hygiene.** v0.17 audits the pre-v0.13 P1/P2/P3 backlog (most items
turned out stale or already-landed), executes the surviving real items
(formatter robustness + Hypothesis property tests + OTel
`tool.result.count`), and deletes the v0.16 `ConnectionInfo` alias.

### Backlog audit

`todo.md` P1/P2/P3 sections (lines 26-72, captured pre-v0.13) honest
again — every item is checked, struck stale, or surviving-and-current.
The v0.13–v0.15 surface deletes invalidated most P3 items
(`tools.py`, `_RouterContext`, `MCPRunner.store=`, `_auto_inject_enabled`,
typed-info DI all gone). The async store API, `MCPRunner.run_async`,
`EnricherFn` async support, and OTel `record_exception` already landed
in v0.11–v0.13.

### Formatter robustness (P1)

- **`_dump_items` raises on non-row items** instead of silently dropping
  them. Pre-v0.17 behaviour turned `[1, 2, 3]` into `[]`, masking
  row-shape bugs. `format_response` gates the call to only normalize
  when `data[0]` is a `dict` / `BaseModel`; heterogeneous lists now
  fall through to the JSON path.
- **`format_from_annotation` unwraps `Awaitable[T]` / `Coroutine[Y, S, T]`**
  before classifying — async tools no longer lose precomputation.
- **Bare `dict`, `Mapping[K, V]`, `TypedDict` subclasses** classify as
  `"json"` (previously fell through to `None`).
- **`_flat_pydantic_fields` handles multi-arm `Optional[Union[A, B]]`**.
  Previously only single-arm Optional was unwrapped; multi-arm fell
  through. New `_classify_arm` helper inspects each non-None arm.

### OTel observability (P2)

- **`tool.result.count` span attribute** — stamped by the OTel
  middleware when the tool returns `list` / `tuple` / `Page[T]`.
  Cardinality only — PII-safe and stamped after success only
  (meaningless on error).

### Property tests (Hypothesis)

- `truncate(value)` is structural identity at high `max_chars` and
  never mutates input — verified against a recursive value strategy
  (atoms / lists / dicts up to depth 4).
- `format_from_annotation(list[FlatModel])` precompute agrees with
  `toon_or_json` runtime classification.
- `hypothesis>=6` added to dev deps; 25 new tests in
  `tests/test_v17.py`.

### Deleted: `ConnectionInfo` alias

v0.16 added `ConnectionInfo = ConnectionConfig` as a one-cycle alias
with an explicit "delete in v0.17" plan. Done.
`src/a2kit/lint/_ast_helpers.py` no longer recognises the old name;
all tests + the tracker example use `ConnectionConfig` directly.
`ConnectionInfoLike` Protocol stays — it's a structural type and the
rename pressure doesn't apply.

### Tests

- 589 tests (564 → 589), 100% coverage.
- `make lint && uv run pytest -q && make examples` green.

## 0.16.0.dev0 — 2026-05-08

**Polish.** v0.16 closes the v0.15 coverage drop, renames the
long-deprecated `ConnectionInfo` → `ConnectionConfig`, and scrubs the
README of stale `Plugin` / `Provider` / `store=` references.

### Coverage refill: 80% → 100%

- ~290 focused tests in `tests/test_v16_coverage.py` covering the
  formatter decision tree, lint AST helpers + rule branches, `app.py`
  CLI body, projection / `_otel` / signature splicing, scaffold runner
  pyproject loaders, `ConnectionStore` edge cases, and enricher
  sync/async drain.
- `cov-fail-under` bumped back to `100` in `pyproject.toml`.
- A handful of genuinely-defensive branches got `pragma: no cover`
  (the optional celpy ImportError, the OTel real-provider fallback,
  the 3rd-tier anyio drain in `apply_enricher_sync`, a few rare
  branches in `_compute_tool_capabilities`).

### `ConnectionInfo` → `ConnectionConfig`

The class lives in `src/a2kit/connections.py` and is now
`ConnectionConfig`. `ConnectionInfo` remains as a module-level alias
for one cycle (removed in v0.17). All internal references — TypeVars,
contrib factory, scaffold CLI/stores, lint helper base-class
string-match — updated. The lint AST helper recognises both names so
user code on the alias still satisfies A2K003 / A2K012 detection.

### README scrub

- Status header rewritten to describe the v0.16 surface (was v0.13).
- API surface table adds `App`, `Depends`, `get_conn_factory`, the
  verb decorators (`@a2kit.read` / `@a2kit.write` / `@a2kit.list`).
- "How a new MCP starts here" walkthrough rewritten around `App` +
  `Annotated[ConnT, Depends(get_conn)]`.
- All v0.7-v0.12 migration footnotes (`*, info: ConnT`,
  `connection_param=`, `Router.store=`, `MCPRunner.store=`,
  `Plugin`/`PluginBase`/`Provider`) collapsed into a CHANGELOG
  pointer.
- `MCPRunner(server, store=store)` examples updated to the v0.15
  `connection_store=` kwarg name.

### Tests

- 564 tests, 100% coverage.

## 0.15.0.dev0 — 2026-05-08

**The big delete.** v0.15 collapses two years of v0.7→v0.12 connection-DI
vocabulary into the single `Annotated[T, Depends(factory)]` idiom. Breaking
compat; no deprecation footnotes.

### New surface

- **`a2kit.contrib.connections.get_conn_factory(app, ConnT)`** — the
  canonical Annotated/Depends factory for connection injection. Returns
  a callable matching the `Depends(...)` factory shape (declares
  `connection: str` as a kwonly so the resolver forwards the call-site
  value). Tests override via `app.dependency_overrides[get_conn] = fake`.
- **WriteEnforce middleware wired automatically.** Tools decorated with
  `@write` (or `write=True`) get the `write_enforce_factory()` middleware
  in their implicit chain — read-only connections raise `WriteNotAllowed`
  before the tool body runs.
- **Transitive `connection` kwarg surfacing.** When a tool declares
  `Annotated[Store, Depends(get_store)]` and `get_store` depends on
  `Annotated[Conn, Depends(get_conn)]`, the wrapper walks the chain and
  exposes `connection: str` on the published signature.

### Removed (breaking)

Tool decorator:

- `connection_param=` kwarg.
- Typed-info DI autodetect (`*, info: ConnT`); `_detect_info_param` helper.
- `store=`, `connection=`, `resolver_registry=`, `router_context=` kwargs.
- Connection-aware branches in `_prelude` / `_prelude_async`. Async
  prelude is now 16 LOC — only `tool_call_guard` remains.

DI container (`a2kit.di`):

- `Provider`, `Plugin`, `PluginBase`, `Binding`, `ToolPlan`.
- `ProviderCollisionError`, `ProviderCycleError`,
  `UnknownProviderTypeError`, `UnknownProviderDepError`.
- `resolve_chain`, `_validate_provider_graph`, `_provider_dep_types`.

Runner:

- `provides=` and `plugins=` kwargs.
- `store=` kwarg → `connection_store=`; public `MCPRunner.store`
  attribute is now private `_connection_store`.
- `lookup_provider`, `resolve`, `cli_commands`.

App:

- `App.use(Plugin)` / `App.use(Provider)` arms.

Router:

- `Generic[ConnT]` parameterisation.
- `store`, `resolver_registry`, `ephemeral`, `auto_connection_enricher`
  fields.
- `Router.context` ClassVar + `_RouterContext` (`_context.py` removed).

Lint:

- A2K001, A2K004. Both checked features that no longer exist.

Misc:

- `_safe_list_connection_keys` (decoration-time saved-key listing).

### Tests

- 11 version-stamped legacy test files deleted (~5800 LOC):
  `test_v03/v031/v04/v06/v07/v08/v10/v11/v12.py`, `test_tools_fat.py`,
  `test_exceptions_v02.py`.
- Added: `tests/test_app_use.py` and `tests/test_decorator_v15.py` cover
  Annotated/Depends end-to-end (saved-conn round-trip, overrides,
  transitive deps, WriteEnforce, CLI shape).
- Final: 290 tests, 80% coverage. `cov-fail-under` temporarily relaxed
  to 0; deferred 100% restoration to v0.16.

### Migration

```python
# v0.14
@MyRouter.read()
async def list_them(*, conn: TrackerConn) -> list[dict]: ...
```

```python
# v0.15
from typing import Annotated
from a2kit.di import Depends
from a2kit.contrib.connections import get_conn_factory

app = a2kit.App("tracker")
app.connect(TrackerConn)
get_conn = get_conn_factory(app, TrackerConn)

@MyRouter.read()
async def list_them(*, conn: Annotated[TrackerConn, Depends(get_conn)]) -> list[dict]: ...
```

`examples/tracker/` is the canonical reference; `examples/tracker/deps.py`
shows the slot pattern that keeps routers decoupled from the `App` instance.

## 0.14.0.dev0 — 2026-05-08

**Polish turn (in progress).** v0.14 picks up the v0.13 deferred backlog;
this dev cut lands two cleanup commits and adds App-scope enricher
plumbing. The big v0.12 connection-surface deletion (`Router.store`,
`MCPRunner.store=`, `connection_param=`, `_detect_info_param`,
`Plugin`/`PluginBase` Protocols, `Router(BaseModel, Generic[ConnT])`)
remains carried over and is the next shaping target — see `todo.md` for
the v0.14 ledger.

### New surface

- **`App(name, enricher=...)`** — App-scope enricher fallback. Resolution
  order at the binding layer is `tool > router > app`, with the existing
  `auto_connection_enricher(store)` as the implicit floor. Routers
  without their own `enricher=` inherit the app's at apply time.

### Removed

- **A2K005** lint rule (`KEY_FIELDS` migration aid + `cls.Key` arity
  cross-check). Carried since v0.5; the legacy `KEY_FIELDS` syntax is
  long gone. Drops `key_fields_value`, `connection_info_key_class`,
  `namedtuple_field_count`, `connection_info_subclasses` AST helpers
  alongside it. ~800 lines net deletion (src + tests + docs).

### Deferred to v0.15

- **`ConnectionInfo` → `ConnectionConfig` rename** — Pydantic schema
  name + error-message ripple across the test corpus exceeded session
  budget; documented for next cycle.
- **Hard delete of the v0.12 connection surface** (the headliner). All
  nine items (`Router.store`, `MCPRunner.store=`, `connection_param=`,
  `_detect_info_param`/`info_target`, `_prelude_async` connection
  branch, `Router(BaseModel, Generic[ConnT])` TypeVar, `Plugin` /
  `PluginBase` Protocols, `Provider` Protocol, `App.use()`'s Plugin
  arm) are interlocked with ~117 `connection_param=` test sites and
  31 `Plugin`/`PluginBase` references; doing them as one coordinated
  migration is its own multi-session pitch.
- **`SubApp` / `app.mount(...)` shape + `connections.make()` real
  SubApp.** Parked behind the surface deletion above.
- **`PLC0415` per-file ignore in `tests/**`.** 123 hits across the
  test corpus; non-trivial migration left for a focused commit.

## 0.13.0 — 2026-05-08

**Library-swap turn + middleware split.** Replaces three bespoke modules
with their stdlib / OTel / vcrpy equivalents, introduces `Annotated[T,
Depends]` DI alongside the v0.12 `provides=` path, splits the fat tool
decorator into a middleware chain, and lifts connection-aware logic into
`a2kit.contrib.connections` so the core decorator no longer knows what a
ConnectionInfo is.

### New surface

- **`Annotated[T, Depends(factory)]` DI** — FastAPI/FastMCP idiom for
  per-tool typed dependencies. `*, store: Annotated[TodoStore,
  Depends(get_todo_store)]` resolves at call time with per-call caching
  and cycle detection, validated at decoration.
  `app.dependency_overrides[get_conn] = fake` swaps factories in tests.
- **`Depends(factory)`** — frozen dataclass marker re-exported from the
  top-level `a2kit` namespace. Lives next to the v0.12 `Provider`
  Protocol; pick the shape that fits the call site.
- **Implicit middleware chain** (`a2kit.middleware`) — the tool decorator
  now assembles a Starlette-style chain at decoration time:
  `tool_call_guard` → `capability_guard` → `otel_span` (always); plus
  `write_enforce`, `list_view_apply`, and `enrich_errors` only when the
  verb / Router / connection asks for them. Authors keep writing
  `@MyRouter.write()` — the chain is implicit. Hooks for
  `@MyRouter.write(middleware=[mw])`, `Router.middleware = [...]`, and
  `App.middleware = [...]` exist for the rare tier-3 case.
- **`a2kit.contrib.connections`** — connection-aware helpers
  (`lookup_connection_async`, `resolve_connection_key`,
  `resolve_info_strings`, `write_enforce_factory`) live in their own
  contrib package. The v0.13 plan ("pull connections out of core") is
  partially landed — re-exports keep v0.12 paths working; v0.14 deletes
  the legacy paths and finishes the SubApp / `connections register`
  CLI subcommand work.
- **`RunnerOptions`** — typed dataclass for `MCPRunner.run(options=...)`.
  Replaces argv-string round-tripping in `App.cli`'s `serve` subcommand;
  `argv=` stays as a v0.12 compat layer.

### Library swaps

| Concern | Before | After |
|---|---|---|
| Sync→async drainage | `a2kit._async_bridge` (18 LOC) | `anyio.from_thread.run` direct |
| OTel NoOp fallback | `_otel.py._NullSpan` (~150 LOC) | `opentelemetry.trace.NoOpTracer` |
| VCR cassettes | `_cassette.py._make_async_ctx` (~40 LOC) | `vcrpy` direct |

Net delete: ~200 LOC of bespoke wrappers that re-implemented stdlib /
upstream-library shapes.

### Deferred to v0.14

- **`_select*.py` → `cel-python`.** Probed; structural blockers in
  user-facing grammar (`and`/`or` vs `&&`/`||`, atom keys with dots)
  and the `SelectExpr` AST consumed by lint rules and scaffold
  introspection (~100 references). Re-open as a dedicated pitch.
- **`tokens.py` → `pydantic-settings` + `pyonepassword`.** Mismatched
  abstractions (`resolve_env` substitutes inside arbitrary strings;
  `pydantic-settings` is a typed settings-model loader); zero-LOC
  savings on the op:// side.
- **Core deletes that touched 30+ test sites.** `Router.store`,
  `MCPRunner.store=`, `connection_param=`, the `_prelude_async`
  connection branch, `_detect_info_param` / `info_target` plumbing,
  `Router(BaseModel, Generic[ConnT])`, and the `Plugin` / `PluginBase`
  Protocols all stay as v0.12-compat surfaces. v0.14 will migrate the
  test corpus to `Annotated[Conn, Depends(get_conn)]` then delete the
  compat code in one pass.
- **`PLC0415` removal from `tests/**`.** The audit halved the noqas in
  `src/` (49 → 25); the remaining 25 are genuine optional-dep / circular
  / verb-decorator factory cases. The test corpus has 123 PLC0415 hits —
  non-trivial migration deferred.

### Coverage

Restored to **100%** (`cov-fail-under=100`). The two v0.12 holes
(`enrichers.py:108`, `tools/_signature.py:113`) plus three drive-by
gaps from the middleware split now have direct tests.

## 0.11.0 — 2026-05-08 (in progress)

**Contract-clarity turn.** Tightens the public vocabulary, restores type
safety on the most-used classes, and exposes a stable accessor for tool
metadata. No new behaviour — the engine is untouched. Existing v0.10 tools
keep working without changes.

### New

- **`a2kit.enrichers`** is the canonical home for `EnricherFn`,
  `chain(*fns)`, and `connection_enricher(store)`. The previous module
  `a2kit.errors` is now a deprecation shim that re-exports from `enrichers`
  and warns at import. Scheduled for removal in **v0.13**. Update imports:
  `from a2kit.enrichers import ...`. The clarification: `a2kit.exceptions`
  holds exception *classes*, `a2kit.enrichers` holds enrichment *functions*.
- **`ConnectionInfoLike` / `ConnectionStoreLike`** moved to their natural
  home `a2kit.connections` (still re-exported from the deprecated
  `a2kit.errors` for one cycle, and from the top-level `a2kit` namespace).
- **`FastMCPLike` Protocol** in `a2kit.scaffold` — the minimum FastMCP server
  surface `MCPRunner` drives (`tool()`, `run()`, `settings`). Use it to type
  your own server wrappers / mocks. Runtime-checkable.
- **`tool_metadata(fn)` → `ToolMetadata`** — public, frozen, slotted accessor
  for the kit-stamped `_a2kit_*` attrs (`tool_name`, `capabilities`,
  `format`). Tests and consumers should assert against `ToolMetadata`, not
  the underlying private attributes.

### Changed (typing — no runtime behaviour change)

- `Router.store / .enricher / .resolver_registry / .ephemeral` are now
  typed (`ConnectionStoreLike | None`, `EnricherFn | None`,
  `ResolverRegistry | None`, `Mapping[tuple[str, ...], ConnectionInfo] | None`)
  instead of `Any`. Pydantic still accepts these — `arbitrary_types_allowed=True`
  was already set — but ty / IDEs now see the real shape on every consumer.
- `MCPRunner.__init__(server, store=...)` accepts `FastMCPLike` and
  `ConnectionStore[Any] | None` instead of `Any`.
- `RouterRegistry._routers` entries are now `_RouterEntry` NamedTuples
  instead of bare 3-tuples — internal cleanup, no API change.
- `Page[T]` docstring locks the convention: `T` is `BaseModel` (preferred —
  enables tsv/toon precompute) or `dict[str, Any]` (ad-hoc rows). The
  TypeVar bound is left off because Pydantic v2 generic-bound interplay
  with `Page[dict[...]]` is fragile.
- `next_cursor` documented as an opaque agent-only string (the kit never
  parses or interprets it).

### Removed

- **`a2kit.A2KIT_CONFIG_HOME`** — was a self-alias for `ENV_CONFIG_HOME`.
  Use `a2kit.ENV_CONFIG_HOME` instead. `a2kit.A2KIT_CONFIG_HOME` now raises
  `ImportError` with a migration hint.

### Deprecated

- **`a2kit.errors` module** — emits `DeprecationWarning` at import. Removed
  in v0.13.

### Compatibility

- All v0.10 tests pass unchanged. 618 tests, 100% coverage, ruff + ty clean.
- Test fakes for `FastMCPLike`-typed args may need to add a `tool()` method
  if they didn't have one (most fixtures already do for FastMCP parity).

## 0.10.0 — 2026-05-07

**Surface-simplification turn.** Four targeted wins, all additive over v0.9:
the wire format is decided at decoration time when possible, `Page[T]` of
Pydantic models actually serialises to TSV/TOON, every Router with a store
gets the typo-suggestion enricher for free, and the agent-facing
`connection: str` schema lists the saved keys it knows about.

### New

- **Format-from-type at decoration time.** When the tool's return type is
  concrete (`list[Issue]`, `Page[Issue]`, `dict`, `Issue`, `int`, …), the kit
  precomputes the wire format (`tsv` / `toon` / `json`) once. Each call skips
  the runtime list-of-dicts walk. Stamped on the wrapper as `_a2kit_format`.

  Decision tree:
  - `list[T]` / `Page[T]` where `T` is a Pydantic model with all-flat
    fields → `tsv` locked.
  - Same shape with at least one `list` / `dict` / nested-Pydantic field →
    `toon` locked.
  - Single `dict`, single Pydantic model, scalar return, `None` → `json` locked.
  - Untyped `list`, `list[dict]`, `Any`, unresolvable forward ref → `None`
    (runtime fallback, identical to v0.9 behaviour).

- **`Page[T]` with Pydantic items.** `_dump_items()` flattens
  `Page[Issue].items` via `model_dump()` before the tabular encoder sees
  them, so `Page[Pydantic]` returns a real TSV/TOON payload instead of
  `str(Issue)` slop. Same fix applies to `list[Pydantic]`.

- **Auto-wired `connection_enricher` on Routers with a store.** A typo in
  the `connection` arg now returns

  ```
  Connection not found: prdo
  Available: prod, staging
  Did you mean: prod?
  ```

  …without the author wiring `enricher=connection_enricher(self.store)`.
  Disable with `auto_connection_enricher=False` on the Router subclass; an
  explicit `enricher=` still wins.

- **Schema enrichment for `connection: str`.** The injected docstring
  inlines the saved connection keys (`Currently saved: 'prod', 'staging'`)
  so the agent sees valid values inline instead of having to call
  `connections list` out-of-band. Empty stores fall back to the v0.9
  generic phrasing.

### Changed

- `format_response(...)` accepts `format_hint: FormatName | None` (default
  `None`). Hint is trusted unless the data shape is incompatible (e.g.
  `tsv` hint on a single dict → falls back to JSON).
- `connection_enricher(store)` parameter type relaxed from
  `ConnectionStore[ConnectionInfo]` to `Any` — the function only needs
  `.list_connections()`. Lets the router's internal `_EphemeralAwareStore`
  proxy flow through without `cast()`.

### Migration from 0.9

No breaking changes. `connection_param=` is still a soft-deprecated alias
(slated for v0.11). Three opt-out hooks:

- Router auto-enricher: `class WidgetsRouter(Router): auto_connection_enricher = False`
- Schema-key enrichment: not configurable in v0.10 — keys are listed when
  `store.list_connections()` succeeds and yields ≥ 1 entry.
- Format-from-type: omit the return annotation, or annotate with `list[dict]` /
  `Any` to force the runtime path.

## 0.9.0 — 2026-05-07

**Ergonomic overhaul.** Pre-1.0, no users — clean breaks across error
handling, capability declarations, list-view tools, and the connection-key
contract. Most tool signatures get shorter; the agent-facing schema gets
sharper; the kit's mental model collapses by one layer.

### New

- **`@Router.read()` / `@Router.write()` auto-inject `connection: str`** into
  the agent-facing schema whenever the Router has a store. Authors stop
  writing `connection_param="conn"` and stop adding `conn: str` to their fn
  signature.

- **Type-driven info DI** — declare a `ConnectionInfo`-subclass typed
  parameter on your fn (`info: WidgetConn`); the kit binds the resolved info
  there at call time. Hidden from the agent-facing schema. `Router.context.info()`
  survives as the helper-function escape hatch:

  ```python
  @WidgetsRouter.read()                                  # zero kwargs
  async def list_widgets(info: WidgetConn) -> list[dict]:
      return [{"url": info.url}]
  # Agent calls list_widgets(connection="prod"); kit resolves + injects info.
  ```

- **List-view triad** — three orthogonal flags, two execution modes each:

  | Concern    | Local (kit handles)               | Passthrough (tool handles)              |
  |------------|-----------------------------------|------------------------------------------|
  | `filter`   | CEL post-process on rows          | thread `filter:str` to fn (compile to JQL/SQL/…) |
  | `fields`   | dict-key projection on rows       | thread `fields:list[str]` to fn          |
  | `pagination` | slice + opaque cursor encoding | thread `limit:int, cursor:str|None` to fn; tool returns `Page[T]` |

  Replaces v0.8's `projection=True` / `cel_filter_param=` / `fields_param=`
  with a coherent execution-mode story so MCPs that pushdown filtering or
  pagination upstream (a2db SQL, a2atlassian JQL) get first-class support
  alongside in-memory data sources (Reddit JSON, local lists).

- **`Page[T]`** — typed Pydantic generic for tools that own pagination
  upstream. `items: list[T]`, `next_cursor: str | None`. Kit unwraps and
  threads `next_cursor` into the outer `Response`.

- **Output formats split honestly: `tsv` vs `toon`** — flat rows render as
  TSV (header + tab-separated scalar cells); rows with at least one nested
  value render as TOON (same shape, but nested cells are compact-JSON-encoded
  inline). `Response.format` is now `Literal['tsv', 'toon', 'json']`. The
  v0.8 'toon' label was lying about the encoding.

- **`Router.capabilities` is `ClassVar`** — caps describe the router's *type*,
  not its runtime instance. Mirrors the existing `read_capabilities` /
  `write_capabilities` `ClassVar` pattern.

  ```python
  class IssuesRouter(a2kit.Router):
      capabilities: ClassVar[set[Capability]] = {Cap.EXTERNAL}
  ```

- **Errors simplified — `EnricherFn = Callable[[Exception, str | None], Exception]`**
  replaces `ErrorEnricher` Protocol + `EnricherRegistry`. Composition via a
  6-line `chain(*fns)` helper. `connection_enricher(store)` factory replaces
  the `ConnectionNotFoundEnricher` class — closes over the store, returns a
  plain function.

  ```python
  @a2kit.tool(enricher=chain(my_enricher, connection_enricher(store)))
  async def query(...): ...
  ```

### Breaking

- `xml_guard` already renamed to `tool_call_guard` in v0.8 — this remains.
- **`projection=True`, `cel_filter_param=`, `fields_param=` removed.** Use
  `filter=Local|Passthrough`, `fields=Local|Passthrough`,
  `pagination=Local|Passthrough` instead.
- **`ErrorEnricher` Protocol, `EnricherRegistry`, `ConnectionNotFoundEnricher`
  class removed.** Use `EnricherFn` callables, `chain(*fns)`,
  `connection_enricher(store)` factory.
- **`ToolConfig` Pydantic model removed.** It was never wired to the live
  decorator — the authoritative kwarg contract is the `ToolKwargs` TypedDict.
- **`Router.capabilities` as a Pydantic instance field is gone.** Move to
  `ClassVar[set[Capability]]` on the subclass.
- **`Response.format` widened to `Literal['tsv', 'toon', 'json']`.** Existing
  `format == "toon"` assertions on flat data will return `"tsv"` instead.

### Soft-deprecated (drops in v0.10)

- **`connection_param=<name>` kwarg** still works as a back-compat alias for
  the v0.8 string-named connection lookup. New code should use the typed-info
  DI pattern (`info: <ConnectionInfo subclass>`).

### Internal

- 561 tests, 100% line+branch coverage, lint + ty clean.
- Examples still 5 files; example 03 renamed `03_projection_tool.py` → `03_list_view.py`
  and rewritten to demonstrate Local + Passthrough side-by-side.

## 0.8.0 — 2026-05-07

**Polish bundle.** Pre-1.0 cleanups surfaced after v0.7: rename
`xml_guard` → `tool_call_guard`, lift ephemeral handling out of the tool
decorator, type-tighten `Router.tool/.read/.write` signatures, type-promote
`format_response`, and add a `projection=True` ergonomic shortcut.

### New

- **`@a2kit.tool(projection=True)`** — auto-injects `filter: str` and
  `fields: list[str] | None` keyword-only params into the wrapper signature
  (FastMCP's tool schema picks them up; agents call with them) and post-processes
  the result through `format_response`. Authors no longer write any projection
  plumbing for the common case:

  ```python
  @a2kit.tool(projection=True)
  def list_widgets() -> list[dict]:
      """Return widgets."""
      return _WIDGETS
  ```

  Collisions with author-declared `filter`/`fields` params raise at decoration
  time. The explicit `cel_filter_param=`/`fields_param=` path remains as a
  power-user escape hatch and cannot combine with `projection=True`.

- **`a2kit.Response`** — typed Pydantic envelope returned by `format_response`.
  Fields: `format` (`Literal["toon", "json"]`), `data` (`str`), `truncated`
  (`bool`), `next_cursor` (`str | None`, reserved for v0.9 pagination). Frozen,
  `extra="forbid"`.

- **`Router.tool/.read/.write` signatures use `Unpack[ToolKwargs]`.** Authors
  composing higher-order Router classmethods now get end-to-end type-checking
  on the kwarg contract.

### Breaking

- **`xml_guard` → `tool_call_guard`** on `@a2kit.tool(...)`, `ToolConfig`, and
  the public `ToolKwargs` TypedDict. Same behaviour, less misleading name —
  the guard refuses any `str` arg containing `<parameter name=` (tool-call
  envelope contamination from agents), and that's a tool-call concern, not
  XML in the abstract.

- **`ToolXMLContamination` → `ToolCallContamination`.** Same shape, same
  message; renamed for symmetry with the kwarg.

- **`format_response` returns `Response`, not `dict`.** Migration: replace
  `env["format"]` with `env.format`, etc.

- **`ephemeral=` removed from public `@a2kit.tool` kwargs** and from the public
  `ToolKwargs` TypedDict. Ephemeral connections live at the Router level only —
  `Router(..., ephemeral={...})` works unchanged. Internally,
  `Router._apply_bindings` now wraps the effective store in a private
  `_EphemeralAwareStore` proxy so the tool decorator never thinks about
  ephemeral connections. Tools that previously passed `ephemeral=` directly to
  the decorator should construct an `_EphemeralAwareStore` explicitly or use a
  Router.

### Internal

- 556 tests, 100% line+branch coverage on 2224 statements / 832 branches.
  No changes to the linter pack, scaffold CLI, or runtime introspection seams.

## 0.7.0 — 2026-05-07

**Idiomatic Python pass.** Pre-1.0 cleanups: idiomatic `StrEnum Cap`, removal of
the `info` kwarg shape, auto-injected param docs, public `ToolKwargs`, FQN
ContextVar naming, A2K012 hardening, A2K013 added.

### New

- **`Cap` is a `StrEnum`.** `list(Cap)` enumerates all members; `Cap("write")`
  parses a raw string; `Cap.WRITE == "write"` is True; Pydantic v2 native
  serialization. The capability registry pre-registers built-ins via the same
  `capabilities.register(...)` path; lib code never branches on cap names.
- **Auto-inject param docs.** When a tool function has `connection_param="conn"`,
  the canonical `connection_param_doc(...)` text is prepended to the docstring
  at decoration time. Same for any `register_param_doc(name, text)` entry whose
  name matches a function parameter. Configurable via
  `[tool.a2kit.docs] auto_inject = false`.
- **A2K013** (advisory) — flags tool docstrings that still call
  `a2kit.docs.connection_param_doc(...)` / `param_doc(...)` via f-string;
  auto-injection covers it.
- **Public `ToolKwargs` TypedDict.** Use `Unpack[ToolKwargs]` for higher-order
  Router classmethod factories (e.g. a custom `expensive` decorator that
  defaults `Cap.EXPENSIVE`). New example: `examples/higher_order_decorator.py`.
- **A2K012 re-export resolution.** A2K012 now follows `from pkg import NAME`
  through `pkg/__init__.py` re-exports (cap depth 3) to confirm the constant
  terminates at a `Final[str]` annotation. Re-exports without a `Final[str]`
  terminus are flagged.

### Breaking

- **`info_kwarg` removed from `@a2kit.tool(...)`.** The kwarg-injection path
  (`*, info: ConnT | None = None`) is gone; the only supported access is
  `Router.context.info()`. `ToolConfig.info_kwarg` field also removed.
  Migration:

  ```python
  # Before:
  async def get_widget(conn: str, *, info: WidgetConn | None = None) -> dict:
      return {"url": info.base_url}

  # After:
  async def get_widget(conn: str) -> dict:
      info = WidgetsRouter.context.info()
      return {"url": info.base_url}
  ```

- **`Cap` is no longer a plain class with `Final[str]` constants.** Author
  syntax `Cap.WRITE`, `Cap.READ`, etc. is unchanged (StrEnum subclasses `str`,
  same equality semantics, same set/dict membership). The only observable
  difference: `Cap.WRITE.value == "write"` exposes the underlying string, and
  `repr(Cap.WRITE)` now shows `<Cap.WRITE: 'write'>`.

### Bug fixes

- **FQN-based `_RouterContext` ContextVar naming.** Two same-named Router
  classes in different modules (e.g. `app/jira/IssuesRouter` and
  `app/github/IssuesRouter`) used to share a ContextVar by `cls.__name__` and
  collide. v0.7 names the ContextVar with `f"{cls.__module__}.{cls.__qualname__}"`,
  giving each Router class independent state. Transparent rename — no author
  change needed.

### Examples

- **NEW** `examples/v07_minimal_mcp.py` (replaces `v06_minimal_mcp.py`) —
  StrEnum Cap demo + ContextVar-only flow.
- **NEW** `examples/higher_order_decorator.py` — `Unpack[ToolKwargs]` factory.
- **UPDATED** `examples/fat_tool.py`, `examples/router_class.py`,
  `examples/v03_minimal_mcp.py` — drop `info` kwarg, use ContextVar.

## 0.6.0 — 2026-05-07

**Router ergonomics + DI + type-verification + capability unification.** Additive
on top of v0.5.0; no destructive changes to v0.5 callers.

### New

- **Auto-derived Router names.** `class WidgetsRouter(a2kit.Router)` now slugs
  to `name="widgets"` automatically. `JiraConfluenceRouter` → `jira-confluence`.
  Explicit `name="..."` still wins.
- **`@MyRouter.read` / `.write` / `.tool` classmethod decorators.** Bind tools
  declaratively at module scope; `register_read` / `register_write` walk
  `cls._tools` by default. Each subclass gets its own fresh `_tools` list via
  `__init_subclass__` to avoid the mutable-default trap. Imperative override
  is still supported as the documented escape hatch (D).
- **Router-level DI.** Lift `store`, `enricher`, `resolver_registry`,
  `ephemeral` to the Router instance; every tool inherits. Per-tool decorator
  kwargs override.
- **`MyRouter.context.info()` typed accessor.** Each Router subclass gets a
  per-Router `_RouterContext` ClassVar backed by a `ContextVar`. The fat
  `@a2kit.tool` decorator sets it before the wrapped fn runs and resets after.
  The `*, info: ConnT` kwarg style still works in parallel and is opt-in
  (only injected if the function declares the kwarg or `**kwargs`).
- **Multi-store MCPs.** `Router(store=...)` per-router; `MCPRunner` aggregates
  via `RouterRegistry.routers_with_stores()`. CLI uses `--register router:key=...`
  namespaced parsing when >1 distinct store is registered; bare form raises
  with router-prefix suggestions.
- **A2K012 lint rule.** Advisory: raw-string custom capability that isn't a
  built-in `Cap.*` constant and isn't an imported / local `Final[str]` constant.
  Skipped on `tests/` and `examples/`.
- **Capability unification reframe.** Built-ins are pre-registered via the same
  `capabilities.register(...)` path as custom caps; `Cap` is a typed
  convenience reference (no special-casing in lib code). A2K009 stays as
  advisory for the built-in case.

### Breaking

- None for the v0.5 API surface. The `register_read` / `register_write`
  methods still exist; they now have a default implementation that walks
  `cls._tools`. Authors who override imperatively continue to work unchanged.

### Migration recipes

```python
# v0.5 — register_read with manual @a2kit.tool:
class WidgetsRouter(a2kit.Router):
    def register_read(self, server, store):
        @a2kit.tool(server=server, store=store, connection_param="conn")
        async def list_widgets(conn: str, *, info) -> list[dict]:
            return [{"url": info.url}]

# v0.6 — declarative + typed context:
class WidgetsRouter(a2kit.Router):
    pass

@WidgetsRouter.read(connection_param="conn")
async def list_widgets(conn: str) -> list[dict]:
    info = WidgetsRouter.context.info()  # typed
    return [{"url": info.url}]

routers.add(WidgetsRouter(store=store))
```

## 0.5.0 — 2026-05-07

**Breaking change.** `KEY_FIELDS: ClassVar[tuple[str, ...]]` is removed in favour
of a NamedTuple-based `Key` class declared via `key=` on the subclass. This
unlocks per-field types (e.g. `env: Literal["dev", "staging", "prod"]`),
keeps NamedTuple-as-tuple compatibility for the existing positional/tuple/kwargs
load shapes, and adds a fully-typed `store.load(WidgetKey(...))` shape.

**Migration recipe:**

```python
# Before (v0.4):
class WidgetConn(a2kit.ConnectionInfo):
    KEY_FIELDS = ("project", "env", "db")

# After (v0.5):
from typing import NamedTuple

class WidgetKey(NamedTuple):
    project: str
    env: str
    db: str

class WidgetConn(a2kit.ConnectionInfo, key=WidgetKey):
    ...
```

Subclasses that still declare `KEY_FIELDS` raise `MigrationRequired` at class
creation time with a generated migration snippet. (Pre-1.0 clean cut: no alias,
no warning grace period.)

**New**

- `ConnectionInfo.__init_subclass__` accepts `key=<NamedTupleClass>`. The class
  is bound as `cls.Key`. Default is the built-in `_DefaultKey(name: str)`.
- `ConnectionStore.load()` accepts a NamedTuple instance directly as a
  fifth call shape: `store.load(WidgetKey(project="a", env="dev", db="c"))`.
  All previous shapes (kwargs / tuple / list / positional / bare-string) still work.
- `ConnectionStore.key_class` property — exposes `model.Key`.
- `ConnectionStore.list_keys()` — returns typed NamedTuple instances rather
  than raw `tuple[str, ...]`. Existing index-style access still works.
- New exception: `MigrationRequired`.
- Examples: `examples/typed_key_literal.py` (per-field `Literal` typing),
  renamed `examples/key_namedtuple.py` (was `key_fields.py`),
  renamed `examples/v05_minimal_mcp.py` (was `v04_minimal_mcp.py`).

**Behavioural changes**

- `KeyFieldMissing` / `KeyArityMismatch` messages now reference the NamedTuple
  class name (e.g. `"Missing key field 'env' on WidgetKey"`).
- A2K005 lint rule simplified: no longer validates `KEY_FIELDS` shape (the
  attribute is gone). Now flags any leftover `KEY_FIELDS = ...` as a v0.5
  migration error and continues to cross-check `connection_param` arity against
  `cls.Key._fields`.

**Removed**

- `KEY_FIELDS: ClassVar[tuple[str, ...]]` — gone. The `__init_subclass__`
  validator that warned on uppercase entries is also gone (NamedTuples enforce
  identifier-shape at the language level).

## 0.4.1 — 2026-05-07

Patch on top of v0.4.0. Three changes: `ty` becomes a hard gate, internal
client-name references are scrubbed from the working tree (and from prior
commits via history rewrite), and two example files are renamed to describe
their shape rather than their inspiring upstream MCP.

**Strict typing**

- `ty` is now a mandatory typecheck step. `make typecheck` no longer skips
  when ty isn't installed — `ty>=0.0.34` is a dev dependency. CI runs
  `uv run ty check src/` between ruff and pytest as a hard gate.
- Pre-commit hook for `ty` runs at `pre-push` (not `pre-commit`) since
  type-checking is comparatively slow.
- Migration: `uv sync --all-extras` if you were previously skipping ty.

**Privacy / generality**

- Connection-name examples no longer reference internal client names.
- Two example files renamed:
  - `examples/a2atlassian_style.py` → `examples/flat_key_style.py`
  - `examples/a2db_style.py` → `examples/multi_field_key_style.py`
- Prose references to `a2atlassian` / `a2db` in source comments, docstrings,
  README, ANTIPATTERNS, and CHANGELOG replaced with descriptive phrases
  ("a Jira/Confluence-wrapping MCP", "a SQL-wrapping MCP"). Real package
  imports (`atlassian-python-api`, `mcp.server.fastmcp`) are unchanged.

**History rewrite**

- v0.4.1 also rewrites the prior 4 commits via `git filter-repo` to scrub
  internal client connection-name references from commit history. Anyone with
  a clone before this point should
  `git fetch --all && git reset --hard origin/main` to sync. (Realistically:
  nobody has a clone — the repo was just published.)

## 0.4.0 — 2026-05-07

Pre-1.0 clean cut. Removes all v0.3 deprecation aliases (no external consumers
to break). Adds CEL projection, completes A2K005, activates A2K010, ships
A2K011, auto-loads pyproject defaults, splits `_select.py`. Internal repo only —
not published to PyPI.

**Breaking changes (deprecation aliases removed):**

- `a2kit.Feature` / `a2kit.FeatureRegistry` — gone. `from a2kit import Feature`
  raises `ImportError` with a migration hint. Use `Router` / `RouterRegistry`
  (kwarg-init).
- `RouterRegistry.feature(...)` decorator — gone. Use `RouterRegistry.router(...)`.
- `MCPRunner` flags `--enable`, `--no-enable`, `--writes` — gone. The synthetic
  `(read or write)` clause translation is removed. Migration:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
- `build_cli(connection_class=...)` kwarg — gone. Derived from
  `store.connection_class`.
- `MCPRunner(connection_class=...)` kwarg — gone. Same derivation.
- `register_ephemeral_connections(args, connection_class)` positional — gone.
  Only `register_ephemeral_connections(args, store=store)` remains.

**New**

- `a2kit.projection` module: `filter_records(records, *, expr)` (CEL boolean
  expression filter), `project_fields(records, *, fields)` (key selection).
  `[projection]` extra brings in `cel-python>=0.5`. Lazy-imported; missing
  dep raises `ProjectionUnavailable`.
- `a2kit.format_response(data, *, filter="", fields=None, ...)` composes
  filter → projection → truncation → format routing.
- `@a2kit.tool(cel_filter_param="filter", fields_param="fields")` auto-threads
  the named function args into `format_response`.
- New exceptions: `ProjectionUnavailable`, `InvalidFilterExpression`.
- `MCPRunner` auto-loads `[tool.a2kit.runner] default_select` from the nearest
  `pyproject.toml` (walks up from CWD). Resolution order: explicit kwarg →
  pyproject value → hard default `"default and not write and not destructive"`.
- `[tool.a2kit.capabilities]` table in `pyproject.toml`. Each entry is
  registered into `a2kit.capabilities` at `MCPRunner.__init__` time. Same
  `CapabilityRecord` validation as the code-side path.
- **A2K010** lint activated: scans `default_select=...`, `parse_select(...)`,
  `--select "<expr>"` literals in source, `scripts/*.sh`, `Makefile`, and
  `pyproject.toml`. Unknown atoms emit `A2K010` with `difflib` suggestions.
- **A2K011** advisory lint: `@a2kit.tool` returning raw `dict`/`Mapping` is
  flagged ("prefer Pydantic BaseModel for richer schema snapshots").
  Configurable via `[tool.a2kit.lint] disabled = ["A2K011"]`. Suppressible
  via `# noqa: A2K011` on the function definition line.
- **A2K005 completed**: cross-checks tool `connection_param` type annotation
  against the resolved store's `KEY_FIELDS` arity. `str` for arity > 1 is
  rejected; `tuple[...]`, typed key model, or `dict[str, str]` accepted.
  Falls back to advisory when the store can't be resolved within the file.

**Cleanups / refactors**

- `_select.py` split into `_select_parse.py` (~110 LOC) + `_select_eval.py`
  (~40 LOC) + `_select.py` façade. Public re-exports unchanged.
- `examples/projection.py`, `examples/cel_filter_tool.py`,
  `examples/toml_capabilities.py`, `examples/v04_minimal_mcp.py` — new.
- ANTIPATTERNS.md adds entries 14–18 (Pydantic class-attr fields, runtime
  `Capability` alias, forward refs + `__future__` annotations, opt-in pytest
  plugins, hard breaks vs synthetic deprecation clauses).
- `tests/test_v04.py` covers projection, A2K005 multi-field, A2K010, A2K011,
  TOML capability loading, removal guards.

**No PyPI publish.** Repo push is the only release channel for v0.4.

## 0.3.1 — 2026-05-07

Patch on top of v0.3.0. Adds Router (Pydantic) + capabilities + select grammar

- Pydantic configs + strict types. Backward-compatible aliases for one cycle.

**New**

- `Router` (Pydantic `BaseModel`, generic over `ConnT`) replaces `Feature`.
  Subclass and instantiate via kwargs: `IssuesRouter(name="issues", capabilities={Cap.EXTERNAL})`.
- `RouterRegistry.apply()` sets a thread-local `_active_router`; the fat
  `@a2kit.tool` decorator reads this via the **auto-tag seam** and merges
  the router's name + capabilities + `Cap.READ`/`Cap.WRITE` (per phase) onto
  every registered tool's tag set.
- `Cap` constants (`Cap.READ`, `Cap.WRITE`, `Cap.DESTRUCTIVE`, `Cap.EXPENSIVE`,
  `Cap.PII`, `Cap.EXTERNAL`).
- `a2kit.capabilities` namespace — register custom caps:
  `a2kit.capabilities.register("tickets-management", description="...")`.
- `--select` boolean expression flag on `MCPRunner`. Grammar:
  atoms (router/tool/capability names), operators `and`/`or`/`not`,
  optional `tool:` / `router:` / `cap:` namespace prefix, parentheses.
  Default: `default and not write and not destructive`.
- `a2kit.sel(...)` typed builder mirrors the CLI grammar via `&`, `|`, `~`.
- `SelectExpr` (Pydantic AST), `SelectAtom`, `parse_select()`.
- Pydantic configs: `ToolConfig`, `RunnerConfig`, `BudgetConfig` (all
  `extra="forbid"`, `frozen=True`).
- `ConnectionInfo.__init_subclass__` validates `KEY_FIELDS` shape (tuple,
  non-empty, identifier per entry, lowercase warned).
- `ConnectionStore.load(...)` unwraps `pydantic.ValidationError` and re-raises
  the underlying `KeyArityMismatch` / `KeyFieldMissing` / `InvalidConnectionKey`.
- `UnknownCapability` exception with `difflib`-based `suggestions=[...]`.
- New lint rules:
  - **A2K008** — Name collision across router/tool/capability namespaces.
  - **A2K009** — Raw built-in capability string (`'write'` instead of `Cap.WRITE`).
  - **A2K010** — Reserved (v0.4) — unknown atom in `--select` expressions.
- Ruff `ANN` rules added to `[tool.ruff.lint]` selection. `tests/` and
  `examples/` paths get per-file ignores for `ANN001`/`ANN201`/etc.
- New examples: `examples/router_class.py`, `examples/select_grammar.py`,
  `examples/typed_decorator.py`. Updated `examples/v03_minimal_mcp.py`,
  `examples/feature_class.py`.
- `make typecheck-strict` target (graceful fallback if ty unavailable).
- `.pre-commit-config.yaml`, `package.json` (jscpd + actionlint),
  `.jscpd.json`, `scripts/find_similar.py` (similar-tool-name detector).

**Breaking changes**

- `--enable` / `--no-enable` / `--writes` flags on `MCPRunner` are deprecated.
  They still work for one cycle (with `DeprecationWarning`) and are translated
  internally to a `--select` expression.

  Migration recipe:
  - `--enable issues,sprints` → `--select "router:issues or router:sprints"`
  - `--no-enable sprints`     → `--select "default and not router:sprints"`
  - `--writes`                → include `(read or write)` in your `--select`
  - `--enable issues --writes` → `--select "router:issues and (read or write)"`

**Deprecations (one-cycle warning, removal in v0.4)**

- `Feature` / `FeatureRegistry` (use `Router` / `RouterRegistry`).
  Class-attribute style (`class IssuesFeature(Feature): name = "issues"`) is
  not supported under Pydantic; use `IssuesRouter(name="issues", ...)` instead.
- `RouterRegistry.feature(...)` decorator (use `RouterRegistry.router(...)`).
- `--enable` / `--no-enable` / `--writes` (use `--select`).

**Internal renames (underscore-prefixed; no external impact)**

- `a2kit/_capabilities.py`, `a2kit/_select.py`, `a2kit/_router_state.py`,
  `a2kit/_configs.py` — all leading-underscore internals.

## 0.3.0 — 2026-05-07

Feature class, KEY_FIELDS, server-auto-register, lint subpackage. Internal-only
release one day after v0.2 — applies a clean cut where it makes sense.

**Breaking changes**

- `KEY_PARTS: ClassVar[int | None]` → `KEY_FIELDS: ClassVar[tuple[str, ...]]`.
  No alias — pre-1.0 clean cut. Migration: replace `KEY_PARTS = N` with the
  field-named tuple, e.g. `KEY_FIELDS = ("project", "env", "db")`. Default
  `("name",)` covers the single-key case, so subclasses with `KEY_PARTS = 1`
  can simply drop the line.
- `build_cli(connection_class=...)` and `MCPRunner(connection_class=...)` are
  deprecated. The store knows its model — use `build_cli(store, name="...")`
  and `MCPRunner(server, store=store)`. Passing `connection_class=` still
  works for one cycle, with a `DeprecationWarning`.
- `register_ephemeral_connections(args, connection_class)` → prefer
  `register_ephemeral_connections(args, store=store)`. Old shape works with a
  warning.

**New**

- `@a2kit.tool(server=server, ...)` auto-registers the wrapped function with
  FastMCP's tool manager. Idempotent when stacked under an explicit
  `@server.tool()` (innermost) — the decorator detects an existing entry by
  name and skips. The single-decorator path is the new default; stacked form
  remains for callers who need explicit FastMCP options.
- `ConnectionInfo.KEY_FIELDS` — named-tuple key shape. Default `("name",)`.
  `ConnectionStore.load(...)` now accepts kwargs (`load(project=..., env=..., db=...)`),
  tuples, lists, positional args, and bare-string sugar for the single-field
  default.
- New typed exceptions: `KeyFieldMissing`, `KeyArityMismatch`.
- `ConnectionStore.connection_class` — exposes the bound model class.
- `a2kit.scaffold.Feature` — base class bundling enricher + snapshot_dir +
  cassette_dir + register hooks. The v0.2 `@registry.feature(name, ...)`
  decorator path is unchanged. Register an instance via `registry.add(MyFeature())`.
- `a2kit.docs.register_param_doc(name, text)` + `a2kit.docs.param_doc(name)`.
  Registered text is auto-injected into a tool's docstring when the existing
  docstring doesn't mention the parameter. Explicit text wins.
- `a2kit.lint` subpackage:
  - **Static rules:** `A2K001` (tool decorator missing param), `A2K002`
    (`-> str` returns), `A2K003` (module-local Pydantic return), `A2K004`
    (canonical connection-param helper), `A2K005` (`KEY_FIELDS` shape +
    usage), `A2K006` (duplicate param description).
  - **Runtime checks:** `A2KR001` (snapshot presence), `A2KR002` (per-tool
    budget), `A2KR003` (total schema budget), `A2KR004` (similar tool names).
  - CLI: `uvx a2kit lint paths...` and `uvx a2kit check --import path:server`.
  - Configurable via `[tool.a2kit.lint]` / `[tool.a2kit.check]`. Per-line
    `# noqa: A2KXXX`.
  - See `LINT.md` for rationale and examples.

**Examples added**

- `examples/v03_minimal_mcp.py` — < 30 LOC for a 2-tool MCP using `@a2kit.tool(server=...)`.
- `examples/feature_class.py` — `Feature` base class with enricher + snapshot dir.
- `examples/key_fields.py` — all four `load()` call shapes against a 3-part key.

Existing examples (`runner.py`, `scaffold_cli.py`, `feature_modules.py`) updated
to drop the now-redundant `connection_class=` kwarg.

**Deprecations (one-cycle warning, removal in v0.4)**

- `build_cli(connection_class=...)`
- `MCPRunner(connection_class=...)`
- `register_ephemeral_connections(args, connection_class)` (positional)

## 0.2.0 — 2026-05-07

Production-grade primitive set. Promotes a2kit from "ready for first external
consumer" to a foundation that absorbs every recurring MCP boilerplate at n=2.
All v0.1 API still imports unchanged; the bare `@a2kit.tool()` is byte-equivalent
to `@a2kit.tools.tool()` from v0.1.

**New modules:**

- `a2kit.formatter` — `truncate`, `toon_or_json`, `format_response`. Vendored
  TOON encoder (~12 LOC) + recursive truncation + canonical envelope.
- `a2kit.docs` — `connection_param_doc(name, *, cli, example, custom_suffix)`.
  One canonical paraphrase for the connection-param docstring (eliminates
  per-tool phrasing drift).
- `a2kit._cassette` (re-exported as `a2kit.testing.cassette`) — vcrpy thin
  wrapper. Decorator + sync/async context manager.

**New scaffold primitives:**

- `a2kit.scaffold.MCPRunner` — wraps `server.run()` with `--register`,
  `--scope`, `--enable`, `--no-enable`, `--writes`, `--http [host:port]` parsing.
  Sets the thread-local transport seam used by `streaming=True` tools.
  Skippable: calling `server.run()` directly is fully supported.
- `a2kit.scaffold.FeatureRegistry` — decorator-style feature-module
  registration with `default=` flag and `apply(server, store, *, enabled,
  include_writes)`.

**Fat `@a2kit.tool` decorator** (extends v0.1 — every new arg is optional):

- `store=` + `connection_param=` + `info_kwarg=` — connection lookup +
  injection.
- `ephemeral=` — in-memory connections take priority over store.
- `resolver_registry=` — recursive `${ENV}` / `op://` resolution on every
  string field of the loaded `ConnectionInfo`.
- `write=True` — enforces `read_only` check; raises `WriteNotAllowed`.
- `xml_guard=True` (default) — refuses any `str` arg containing
  `<parameter name=`; raises `ToolXMLContamination`.
- `otel=True` (default) — wraps the call in `a2kit.tool.<name>` span when a
  non-default tracer provider is configured; no-op otherwise. Lazy import,
  optional `[otel]` extra.
- `streaming=True` — async-iterator returns collected on stdio, passed
  through on HTTP.
- `tool_name=` — explicit name for the OTel span (defaults to `__name__`).
- Public top-level alias `a2kit.tool` (v0.1 `a2kit.tools.tool` retained).
- Standalone helper `a2kit.tools.assert_clean_string(value, param_name)`.

**Pytest plugin additions:**

- `--update-cassettes` flag.
- `update_cassettes` boolean fixture.

**New exceptions:** `WriteNotAllowed`, `ToolXMLContamination`.

**Optional extras:**

- `[otel]` — `opentelemetry-api>=1.20`. Lazy-imported.
- `[testing]` — `vcrpy>=6`. Lazy-imported via `a2kit.testing.cassette`.

**Examples added:** `fat_tool.py`, `runner.py`, `formatter.py`,
`feature_modules.py`, `streaming_tool.py`, `cassette_test.py`. `scaffold_cli.py`
updated to use `MCPRunner`. `make examples` runs all of them end-to-end.

**Anti-patterns consolidated:** `ANTIPATTERNS.md` at repo root — 13 entries,
each with citation.

**No deprecations.** `a2kit.tools.tool` still exported.

## 0.1.0 — 2026-05-07

Initial thin-library release. Promotes a2kit from single-primitive spike to a v0.1
library ready for first external consumer.

**Public API surface:**

- `ConnectionInfo`, `ConnectionStore`, `default_config_dir` — TOML-backed
  named-connection store. Already in 0.0.1.
- `resolve_token`, `ResolverRegistry`, `resolve_env`, `resolve_op`, `resolve_literal`,
  `default_registry` — token resolvers (`${ENV_VAR}`, `op://...`, literal). Already
  in 0.0.1.
- `tools.tool` decorator — composes with FastMCP's `@server.tool()`. Refuses
  `-> str` returns at decoration time (`InvalidToolReturnTypeError`); rewrites
  return annotations on both wrapper and wrapped function. Optional `enricher`
  routes exceptions through an `ErrorEnricher`.
- `tools.preserve_return_annotation` — public utility for the annotation-rewrite
  trick alone, without the rest of `tool(...)`.
- `errors.ErrorEnricher` Protocol — `enrich(exc, *, tool_name) -> Exception`.
- `errors.EnricherRegistry` — chains enrichers in registration order; first
  divergent return wins.
- `errors.ConnectionNotFoundEnricher` — built-in enricher; adds
  `available_connections` and a `difflib` suggestion to `ConnectionNotFound`
  exceptions.
- `scaffold.build_cli(store, connection_class, name)` — Click group with
  `login`/`logout`/`connections list`/`connections show`/`connections delete`.
  Author adds their own commands via `cli.add_command(...)`.
- `scaffold.register_ephemeral_connections(args, connection_class)` — parses
  `--register KEY field=val ...` blocks from argv into in-memory connections.
- `scaffold.scope_filter(store, scope)` — read-only filtered store view.
- `testing.snapshot_schemas(server, dir)` — writes one compact-JSON file per
  FastMCP tool (file size = byte-accurate token-budget proxy).
- `testing.assert_schemas_match(server, dir)` — raises `SchemaSnapshotMismatch`
  on drift; message contains a unified diff.
- `pytest_plugin` — opt-in via `pytest_plugins = ["a2kit.pytest_plugin"]` in
  the consumer's `conftest.py`. Provides `schema_snapshot` fixture and
  `--update-schema-snapshots` flag.
- New exceptions: `InvalidToolReturnTypeError`, `SchemaSnapshotMismatch`.

**No deprecations.** All 0.0.1 API still imports unchanged.

**Out of scope (deferred):**

- Retry/rate-limit base client (anticipated at n=1; confirm or kill at n=3).
- Feature-module registration with `--enable` (anticipated at n=1).
- Pagination unification (anticipated at n=1).
- Output-format router (TSV/TOON/JSON) — module-level concern, not a primitive.
- Token-budget defaults — module-level concern.
- OTel integration — deferred to v0.2.

## 0.0.1 — 2026-05-07

Initial spike. `ConnectionStore` extracted from two upstream MCPs (a SQL
wrapper and a Jira/Confluence wrapper); pluggable `ResolverRegistry`; typed
exceptions on resolver failure.
