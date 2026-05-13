## Why

Three real consumers (a2web shipping; a2atlassian and a2db migrating shortly) will pin against the same surface. A targeted audit of that surface against MCP spec semantics, README claims, and consumer usage found one production bug, five footguns where invalid kwargs are silently accepted, a handful of dead-surface kwargs and verbs that no consumer reaches for, and a README that contradicts the code on lifecycle hooks. Fix all of it in one v0.33 pass before the next migration locks in the current shape.

## What Changes

**Bug**
- `<app> health` ModuleNotFoundError on every fresh non-dev install: `builder.py` health command imports `a2kit.packages.testing.client`, which transitively imports `pytest`. Decouple the health subcommand from the testing package — it only needs the container and the health registry.

**Footguns — accept-invalid → raise at decoration**
- **BREAKING** `@a2kit.read(idempotent=...)` / `@a2kit.list_(idempotent=...)` → `TypeError`. Per MCP spec, `idempotentHint` is only meaningful when `readOnlyHint=false`; reads are already idempotent by definition. Same shape as the existing `destructive=` rejection on `@read`.
- **BREAKING** `@a2kit.list_` on a function whose return is not `list[T]` / `tuple[T,...]` / `set[T]` / `frozenset[T]` → `TypeError` at decoration. Currently silently degrades (selectable fields become `()`).
- **BREAKING** `@a2kit.list_(page_size=N)` with `N <= 0` → `ValueError` at decoration. Currently silently no-ops at runtime.
- **BREAKING** `@a2kit.tool(annotations=..., idempotent=...)` (or any flag kwarg passed alongside explicit `annotations=`) → `TypeError`. No more silent winner.
- `@app.health_check` registers a probe regardless of `health_tool=True`. New rule: first `@app.health_check` call auto-enables the health tool. `App(health_tool=True)` becomes redundant (still accepted, no-op when checks are also registered).

**Dead surface — drop**
- **BREAKING** Remove `@a2kit.tool` (bare verb). Zero consumer use; `@a2kit.read` / `@a2kit.write` / `@a2kit.list_` cover every observed case.
- **BREAKING** Remove `name=` kwarg from public verb decorators. Tool name derives from `fn.__name__` (auto-camel-to-snake). Internal `_meta.health` registration stays via a private alias.
- **BREAKING** Remove decorator form of `app.singleton(T)` (i.e. `@app.singleton(T)` over a factory). Method form `app.singleton(T, factory, ...)` is the only path. Frees the slot for the `teardown=` parameter shipping in v0.33's next change.
- **BREAKING** Remove stacked `@reports(T)` decorator. `reports=T` kwarg on the verb decorator is the only path. Removes the `A2K-LDD-REPORT-TYPE` lint rule's "outside-function" branch.

**Collapses**
- **BREAKING** Merge `app.tool_descriptors()` into `app.tools()`. `app.tools()` returns `list[ToolDescriptor]`. Each descriptor exposes `.fn`, `.meta`, `.verb`, `.slug`, `.name`. The old "list of callables" path goes away.

**DX**
- Split `AmbientContextMissing` message: distinguish "no active dispatch" from "active dispatch but tool body omitted `ctx: ToolContext` parameter" — different actionable hint per failure mode.

**Documentation rescue**
- README has ~10 stale references to `@app.on_startup` / `@app.on_shutdown` (removed in v0.31; canonical path is `App(lifespan=cm)`). Remove all.
- README claims a `Surface` Flag enum; code has `Visibility = Literal["hidden", "cli", "all"]`. Reconcile to the code shape; document the three values.
- README's `install_connections` + `connections_cli` examples pass the same connection type twice. Update to single-call form.
- Spell out the `LDD` acronym ("logging, data, diagnostics") at first reference in README and in `a2kit/ldd.py` module docstring.
- Fix `Router.slug` docstring (currently denies auto-derivation that the code actually performs from class name).
- Document `list_` trailing underscore (avoids shadowing the built-in).
- Document the default connection-store path.

**Infrastructure**
- New CI test: every public symbol claimed in README (`a2kit.X`, `@a2kit.X`, `App.X`, `Router.X`) must `hasattr` against the live code. Fails loud on doc/code drift.

## Capabilities

### New Capabilities
- `docs-code-parity`: README symbol-drift CI gate. Every public symbol named in README must resolve in the live module surface; failures fail `make lint`.

### Modified Capabilities
- `verb-decorators`: drop `@a2kit.tool` bare verb, drop `name=` kwarg, raise `TypeError` on `idempotent=` for read/list verbs, raise `TypeError` on `annotations=` + flag-kwarg conflict
- `mcp-tool-annotations`: codify the spec-derived constraint that `idempotentHint` and `destructiveHint` are write-verb-only kwargs
- `tool-return-type-discipline`: `@a2kit.list_` requires `list[T]`-shaped return annotation at decoration time; non-collection returns raise `TypeError`
- `health-probe`: `@app.health_check` auto-enables health tool; `<app> health` CLI decouples from `a2kit.packages.testing` (no pytest import on fresh install)
- `tool-descriptors`: single accessor `app.tools()` returning `list[ToolDescriptor]`; legacy `app.tool_descriptors()` removed
- `app-singletons`: remove decorator form `@app.singleton(T)`; method-call form `app.singleton(T, factory)` is the only path
- `operational-contracts`: `AmbientContextMissing` message distinguishes "no dispatch" vs "tool missing ctx param"

## Impact

- **Code**: `src/a2kit/tool.py` (decorator guards, drop `name=`, drop `@tool`), `src/a2kit/app.py` (health auto-enable, tools()/tool_descriptors() collapse, singleton decorator-form removal), `src/a2kit/packages/cli/builder.py` (health_cmd decoupling), `src/a2kit/packages/testing/__init__.py` + `fixtures.py` (defensive guard), `src/a2kit/packages/mcp/reports.py` (drop stacked decorator), `src/a2kit/packages/lint/` (simplify `A2K-LDD-REPORT-TYPE`), `src/a2kit/exceptions.py` + `src/a2kit/packages/ldd/` (AmbientContextMissing message split), `README.md` (substantial rewrite).
- **Tests**: flip tests that asserted current (broken) accept-invalid behavior; add tests for each new raise; add the docs-code parity CI test; add a smoke test that `<app> health` works without `pytest` installed.
- **Consumers**: a2web is the only live consumer; spot-fix any places that used the dropped APIs (per audit: none today). a2atlassian and a2db pin to v0.33 from the start.
- **Migration**: all breaking changes follow a2kit's "loud failure with embedded migration hint" convention. Each raise names the kwarg/verb and points to the replacement.
- **Out of scope** (deferred to follow-up changes): teardown-per-singleton (W1), Router-tools orphan detection (W2), App-as-Router (`@app.read` on App), `add_provider` / `add_singleton` rename, `--select` mechanism, `set_ldd` rework, dispatch-hook public setter.
