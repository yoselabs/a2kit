## Context

After the four `v1-thin-core` commits (`v1-cleanup-debt`, `ldd-streaming-reports`, `dx-polish-tracker-refresh`, `pluggable-core-architecture`), the surface area carries **eight distinct magic mechanisms**, each invented to solve friction created by the previous one:

```
v1-cleanup-debt              →  Depends(<class>) class-as-key DI
ldd-streaming-reports        →  (no new magic; LDD is straightforward)
dx-polish-tracker-refresh    →  Store[ConnT] Generic + class kwarg enricher
pluggable-core-architecture  →  Plugin Protocol, DependsResolver Protocol,
                                polymorphic app.use(), claim/adopt walk,
                                A2K-CORE-PURITY lint rule
```

The audience — DataArt's whole practice — is staffed with senior Python engineers who will read the `connections/plugin.py` + `signature.py` + `app.py::use()` triangle and see "framework anxiety, not solved problem." The fat-decorator core (`@a2kit.read/write/list_`, schema generation, dual MCP/CLI dispatch) is the actual product. Everything else dilutes the pitch.

The user named the cut directly: **"AI slop."** The mark of AI slop is locally-defensible abstractions that, summed, look like over-engineering to a human with taste. We have eight of them.

This change is the strategic retreat: keep the decorator, kill the framework around it, and ship v1.0 looking like Python.

## Goals / Non-Goals

**Goals:**

- Tracker example reads like normal Python in ≤ 50 LOC across `server.py + routers.py + store.py`.
- A reader unfamiliar with a2kit can predict every line's behavior without reading the framework source.
- `import a2kit` stays under 100 ms (no regression; expect small improvement).
- All eight magic mechanisms listed in `proposal.md` removed.
- DI becomes "factories are functions; pass them to your router constructor." One paragraph in README.
- `ConnectionStore` remains as a small useful class for `${VAR}` / `op://` substitution and JSON persistence — the genuinely-load-bearing 30 lines.
- All existing test value preserved (delete tests for deleted mechanisms; rewrite tests whose targets changed shape; everything else stays green).

**Non-Goals:**

- Not removing the fat decorator. `@a2kit.read/write/list_` and the `A2KitMeta` stamp stay.
- Not removing `ToolContext` / LDD channels. Those are simple and earn their keep.
- Not removing the formatter / select / lint packages. Those are not magic.
- Not changing the MCP-vs-CLI dual-mode story. That's the product.
- Not preserving backwards compat with the prior four commits. This is a 5th commit on `v1-thin-core`; the branch's contract resets.
- Not introducing a new plugin Protocol "later." YAGNI. When a real plugin demand exists (not Connections), invent one then.
- Not making `Router` optional. Routers earn their keep by grouping tools and namespacing CLI subcommands.

## Decisions

### D1. DI shape: constructor injection, nothing else

**Decision.** `Depends(...)` is removed in all forms — class-as-key AND callable form. `uncalled_for` is dropped from `pyproject.toml`. Constructor injection is the only DI shape:

```python
class TasksRouter(a2kit.Router):
    def __init__(self, get_store) -> None:
        self.get_store = get_store

    @a2kit.read()
    async def list_tasks(self, *, connection: str, project_id: str) -> list[Task]:
        return self.get_store(connection).list_tasks(project_id)

# server.py
app = a2kit.App("tracker")
app.add_router(TasksRouter(get_store))
```

**Alternatives considered:**

- **Keep `Depends(<callable>)` as the survivor.** Rejected per user direction: keeping a second DI shape gives "two ways to do the same thing" — the very anti-pattern this change targets. Cleaner to ship one idiom.
- **Keep class-as-key DI.** Rejected per the entire premise of this change.

**Rationale.** Constructor injection is invisible to the framework — the router's tools see `self.get_store` as a regular attribute. No reflection, no hidden parameters, no schema-stripping logic. Dropping `uncalled_for` removes a dependency, simplifies cold-start, and removes the `Depends(...)` parameter-default sentinel pattern (which reads as FastAPI cargo cult to senior reviewers).

### D2. App composition: three named verbs

**Decision.**

```python
app.add_router(router)              # Router instance
app.add_cli(click_group_or_command) # Click subcommand to mount on root
app.add_mcp_middleware(middleware)  # FastMCP middleware
```

No `app.use(thing)` polymorphism. No `app.connect(C)`. No `app.use_factory(...)`.

**Alternatives considered:**

- **Keep `app.use()` polymorphic.** Rejected: the isinstance ladder bug (ABCMeta `register()` false-matching Plugin) is the canonical "your dispatcher has unintended cases" story. A reader has to know the dispatch order to predict behavior.
- **Single `app.add(thing)` polymorphic.** Same problem, smaller name.

**Rationale.** Three short verbs, each takes one specific kind of thing. The reader sees `add_router(...)`, knows it's a Router. No surprises.

### D3. Connections as plain class

**Decision.** `ConnectionStore` becomes the public type:

```python
from a2kit.connections import ConnectionStore, connections_cli

conn_store = ConnectionStore(TrackerConn, app_name="tracker")

def get_store(connection: str) -> TrackerStore:
    return TrackerStore(conn_store.load(connection))

app.add_cli(connections_cli(conn_store))   # explicit, opt-in
```

The package retains: `ConnectionConfig` (Pydantic-settings base), `ConnectionStore` (load/save with `${VAR}` / `op://` substitution), `connections_cli(store)` factory returning a Click group.

**Alternatives considered:**

- **Keep the `Connections()` plugin class.** Rejected: it exists only to be "registered with the app" so `app.cli_commands()` can flatten contributions. With `app.add_cli(...)` direct, there's nothing to mediate.
- **Remove `connections_cli` entirely; users hand-roll their own login UI.** Rejected: the substitution + JSON-persistence + `login/logout/list/show/delete` UX is genuinely useful and ~200 LOC. Worth keeping; just don't wrap it in a plugin abstraction.

### D4. Stores: plain classes with explicit constructors

**Decision.** No `Store[ConnT]` Generic. No `__orig_bases__` introspection. A "store" is just a class:

```python
class TrackerStore:
    def __init__(self, conn: TrackerConn) -> None:
        self.path = conn.db_path
```

Composition is a one-liner the user writes:

```python
def get_store(connection: str) -> TrackerStore:
    return TrackerStore(conn_store.load(connection))
```

**Rationale.** The Generic was solving "given a Store class, find its conn class." We can solve that with a one-line factory. No reflection, no advanced-Python features.

### D5. Enricher: per-tool decorator only

**Decision.** Keep `@a2kit.read(enricher=fn)` per-tool. Drop:

- `class TasksRouter(a2kit.Router, enricher=fn):` PEP 487 class kwarg
- `self.enricher = ...` instance attr scanning
- Router-level meta scanning for an enricher attr

`Router.tools()` still applies the per-tool enricher (mechanism stays in core; the wiring is now exclusively per-`A2KitMeta.enricher`).

**Alternatives considered:**

- **Keep the class kwarg form.** Rejected: PEP 487 `__init_subclass__` is one of the more obscure Python features; reading `class TasksRouter(a2kit.Router, enricher=fn):` requires explanation. Per-tool is explicit at the call site.
- **Drop enricher entirely.** Rejected: the connection-not-found → 404 enrichment is a genuinely useful pattern for MCP tool failures.

### D6. No Plugin Protocol

**Decision.** Delete `src/a2kit/plugin.py`. Delete `Plugin`, `DependsResolver`, `ToolWrapper` Protocols. Delete `runtime_checkable` machinery and the `_plugins` registry on App.

**Rationale.** The Protocol existed to let `Connections` be detachable. With the connections package importable directly and the CLI subcommand opt-in via `app.add_cli(connections_cli(store))`, there's no abstraction to plug. Inventing a Plugin Protocol with no second plugin is YAGNI. When (if) we have one (e.g. metrics middleware), invent the Protocol then with the actual second use case in hand.

### D7. No `A2K-CORE-PURITY` lint rule

**Decision.** Delete `src/a2kit/packages/lint/rules/core_purity.py`. Drop `A2K_CORE_PURITY` from `static.py::ALL_RULES`. Drop the rule's tests.

**Rationale.** The rule existed to enforce the boundary the Plugin Protocol invented. With no Plugin Protocol, the boundary is gone, and the rule polices nothing. (Lint rules that defend invented architecture are a tell of AI slop; we shouldn't keep one.)

### D8. Delete `make_test_app` entirely

**Decision.** No test-app helper. Tests construct an `App` directly:

```python
def test_list_tasks():
    fake_get_store = lambda connection: FakeStore()
    app = a2kit.App("test")
    app.add_router(TasksRouter(fake_get_store))
    # ... invoke through app
```

The `make_test_app` symbol is removed from `src/a2kit/packages/testing/__init__.py`. The `packages/testing` module retains its syrupy snapshot extension and any other genuinely-load-bearing helpers; only the App-builder helper is deleted.

**Rationale.** A two-line "make an App and register routers" call doesn't need a helper. The helper was load-bearing only when it carried `overrides={...}` (which itself only existed because of the framework's class-as-key DI). With both gone, the helper has no job. Tests reading `app = a2kit.App("test")` are arguably *clearer* than `make_test_app(...)` because the reader sees production code shape with no test-only indirection.

### D9. Migration recipe for users

The `v1-thin-core` branch is unreleased; nobody's depending on the prior four commits' shape. CHANGELOG documents the migration anyway:

| Before | After |
|---|---|
| `app.use(Connections())` | (delete; ConnectionStore is direct) |
| `app.use(TrackerConn)` | (delete; conn config is just a class) |
| `app.use(TasksRouter())` | `app.add_router(TasksRouter(get_store))` |
| `Depends(TrackerConn)` | constructor injection |
| `Depends(TrackerStore)` | constructor injection |
| `Depends(get_conn)` (callable form) | constructor injection |
| `from uncalled_for import Depends` | (delete; uncalled_for no longer a dependency) |
| `class TrackerStore(a2kit.Store[TrackerConn])` | `class TrackerStore:` |
| `app.connect(TrackerConn)` | (delete) |
| `class R(a2kit.Router, enricher=fn):` | `@a2kit.read(enricher=fn)` per tool |
| `make_test_app(routers, overrides={...})` | construct routers with test factories |

## Risks / Trade-offs

- **[Risk] Constructor injection looks verbose for routers with many factories.** → Mitigation: routers stay narrow (one bounded context per router); if a router needs >3 factories, that's a smell pointing at decomposition, not at framework lacking. Document in ANTIPATTERNS.

- **[Risk] Users who built on the prior four commits have to rewrite.** → Mitigation: the branch is unreleased; nobody's downstream. Internal examples (just `examples/tracker/`) are updated in this change.

- **[Risk] Removing `Plugin` Protocol forecloses extension.** → Mitigation: it doesn't. Anyone can write a function that takes an App and adds routers/cli/middleware to it. That IS the extension story. When we have a *real* plugin (not Connections), we can invent a Protocol with that as the design point.

- **[Risk] Coverage drops when we delete tests for deleted mechanisms.** → Mitigation: coverage is a ratio. Deleting code AND its tests in equal measure preserves the ratio. Spot-check with `make test` after deletion; expect to land in the 92-94% band.

- **[Trade-off] Three verbs (`add_router`/`add_cli`/`add_mcp_middleware`) is more API surface than one (`use`).** → Accepted: explicit > implicit. Reading code beats writing code.

- **[Trade-off] Constructor injection requires routers to know they have factories.** → Accepted: this IS the dependency. The framework hiding it via `Depends(...)` was the magic we're cutting.

- **[Risk] User changes mind mid-implementation, wants some magic back.** → Mitigation: tasks.md ordered to land verb rename + Plugin deletion FIRST (high-blast-radius, irreversible), then connection/DI cleanup (incremental). User can call halt after Phase 1 if cold feet.

## Migration Plan

This is a 5th commit on `v1-thin-core` (per user direction in conversation). The prior four commits stay in the history.

```
v1-thin-core branch:
  8bd70c6  v1.0 thin-core + cleanup-debt
  b04cb02  ldd-streaming-reports
  c919875  dx-polish-tracker-refresh
  6f70239  pluggable-core-architecture
  ───────  de-magic                      ← this change
```

After the de-magic commit lands, branch is ready for merge to main + v1.0 tag (pending separate user authorization).

**Rollback strategy.** Single revert of the de-magic commit restores the prior shape. No data, no migrations, no irreversible side effects.

## Open Questions

1. ~~**Should `make_test_app` survive at all?**~~ **Resolved per user direction: delete entirely.** See D8.

2. **Does `Router` deserve a class kwarg form for *anything*?** Currently we're killing `enricher=fn` as a class kwarg. There's no other use. So: delete `__init_subclass__` entirely. Confirmed implicitly by D5; called out for visibility.

3. **`a2kit.run(app)` lazy CLI import survives unchanged?** Yes. That's not magic, that's a cold-start optimization. Stays.

4. **Does `examples/tracker/` need a separate `connection.py` file?** With the connection class being 4 lines, it could move into `server.py`. Prefer keeping the file for clarity; it's easy to point to in docs.

5. **Should `connections_cli(store)` take *multiple* stores for multi-conn-type apps?** Out of scope here. Single store is the v1.0 shape; if multi-store comes up, address it in a future change without re-introducing a plugin Protocol.
