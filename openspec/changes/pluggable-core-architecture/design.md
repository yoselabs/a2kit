## Context

Two domain concepts have leaked into core a2kit:

1. **Connections.** The `App` class knows about
   `_connection_types`, `connect()`, `get_store()`. The
   `signature.py` module imports `ConnectionConfig` to detect store
   classes. Core exceptions include three connection-specific names
   (`ConnectionKwargMissing`, `ConnectionNotRegistered`,
   `StoreConnectionTypeUnknown`). The `Store` Protocol is in core.
2. **Enrichers.** `A2KitMeta.enricher` is a typed core field. The
   `Router.__init_subclass__(enricher=...)` class kwarg captures the
   value in core. The MCP / CLI adapters call `enricher_wrap(...)`
   from the enrichers package — but they decide WHEN to call it,
   coupling adapter code to the enricher concept.

This is at odds with the v1.0 promise: "thin core, opt-in plugin
packages." Today the core tree contains plumbing for two specific
features that aren't even loaded in some applications. A user who
doesn't need connections still gets `<app> connections ...` in their
CLI; an app that doesn't use enrichers still carries the field
through every tool's metadata.

The user's stated principle: **core knows nothing about
connections or enrichers; both are real plugins; the boundary is
lint-enforced.**

This change formalizes the plugin contract, migrates connections and
enrichers to it, and adds `A2K-CORE-PURITY` as a hard gate.

### Constraints

- **No regression at the call site.** Tools written today
  (`*, conn: TrackerConn = Depends(TrackerConn), connection: str`)
  must keep working when the Connections plugin is registered.
- **Backwards-compat sugar where cheap.** `App.connect(C)` continues
  to work as long as the Connections plugin is registered (raises
  with a clear hint otherwise). `Router(enricher=fn)` constructor
  arg becomes a no-op when Enrichers plugin is missing. Existing
  tests stay green with explicit plugin registration.
- **Cold-start unchanged.** Core may shrink; nothing should grow.
  `import a2kit` < 100 ms; importing a plugin pays only for that
  plugin's transitive deps.
- **Lint enforces the boundary.** `A2K-CORE-PURITY` is hard-gated.
  Regression-proof.

## Goals / Non-Goals

**Goals:**
- Define `Plugin` Protocol with optional contribution methods.
- `App.use(thing)` polymorphic dispatch.
- Migrate connections feature to a plugin.
- Migrate enrichers feature to a plugin.
- Move connection-specific exceptions / Store marker / DI code out
  of core.
- Add `A2K-CORE-PURITY` lint rule.
- Refresh tracker example to use explicit plugin registration.

**Non-Goals:**
- OTel migration. OTel is already a separate package; refactor to
  plugin protocol can be a follow-up.
- Generic middleware Plugin examples. The Protocol allows it; we
  don't ship a third plugin in this change.
- Removing `App.use_factory(...)`. The legacy stub-factory path
  moves to the Connections plugin (since it's a connections feature)
  but keeps its API.
- Plugin discovery via entry points. Explicit registration is the
  contract; `pyproject.toml` `entry_points` is out of scope.
- Multi-plugin precedence configuration. First-registered wins;
  defer ordering knobs until a concrete need surfaces.

## Decisions

### Decision 1: Plugin Protocol uses optional methods, not subclasses

The `Plugin` Protocol declares `register(app)` as required and other
methods as OPTIONAL. Plugins implement only what they contribute. The
App walks plugins and uses `hasattr(plugin, "cli_commands")` (or
similar) to decide whether to call.

Considered alternatives:

- **ABC with all methods, default `[]` returns.** Forces every
  plugin to inherit a base. Reads like Java; Python's duck typing
  fits Protocol better.
- **Single-method plugin returning a "contribution bundle" dict.**
  Plugins return a dict with keys for each contribution type. Less
  type-safe; harder to grep for "what does this plugin contribute?"

Protocol with optional methods wins: type-checkable,
duck-friendly, and `runtime_checkable` for `isinstance(p, Plugin)`
sanity checks.

### Decision 2: `app.use(thing)` is the ONE registration verb

Three dispatch arms inside `use`:

1. **Plugin instance** → `register(self)` + append to plugin list.
2. **Router instance** → core-native registry. (Routers are core,
   no plugin involvement.)
3. **Foreign type** → walk plugins, find one whose `claim(thing)`
   returns True, call `adopt(thing, self)`.

Order matters: Plugin check first (it's the cheapest), then Router
(also core-native), then plugin-claim walk. Foreign types that match
no plugin raise `TypeError` listing what IS registered.

This keeps the App API minimal (one method) while letting plugins
intercept arbitrary types they care about.

### Decision 3: Plugins own their state, not the App

The `Connections` plugin keeps `_conn_types: list[type]` on itself.
The App has `app.plugins()` returning the list of registered plugin
instances. Code that needs to know "what connection classes are
registered?" asks the Connections plugin directly, not the App.

This is the bigger inversion. Today the App holds
`_connection_types` and the connections package reads from it. After:
the connections plugin holds the registry and the App holds nothing
domain-specific.

### Decision 4: Tool wrappers compose left-to-right

When multiple plugins contribute `tool_wrappers()`, they're applied
in plugin-registration order. So with `[w1, w2]`, the registered
function is `w2(w1(fn, meta), meta)`. Earlier plugins wrap closer to
the original fn (most "inner"); later plugins wrap outermost.

The Enrichers plugin's wrap is exception-transform — outer position
is correct (it sees the final exception state). If we add OTel
later, OTel's tracing wrap also belongs outer. Order matters when
multiple plugins both wrap; we'll cross that bridge when it
surfaces. For now, registration order is the documented contract.

### Decision 5: DependsResolver Protocol is plugin-contributed

`Depends(<class>)` resolution today lives in
`a2kit.signature.bind_class_dependencies` and contains explicit
imports of `ConnectionConfig`. That's a core-purity violation.

After: core's `signature.py` exposes a generic
`bind_class_dependencies(fn, app)` that walks
`app.depends_resolvers()`. Each resolver implements:

```python
class DependsResolver(Protocol):
    def claim(self, target: Any) -> bool: ...
    async def resolve(self, target: Any, kwargs: dict, app: "App") -> Any: ...
```

The Connections plugin ships two resolvers (one for conn classes,
one for store classes). Core stays domain-neutral.

### Decision 6: `RouterMixin` for router-level enrichers

Class kwarg `enricher=fn` on `Router` is removed from core. Restoring
the UX in the Enrichers package: `RouterMixin` provides
`__init_subclass__(enricher=...)` that writes to each tool's
`meta.extra["enricher"]`. Authors who want the kwarg syntax mix in
`RouterMixin`:

```python
class TasksRouter(a2kit.Router, RouterMixin, enricher=fn):
    ...
```

Authors who don't care about per-router defaults skip the mixin and
decorate methods individually. Core `Router` doesn't know enrichers
exist.

### Decision 7: `A2K-CORE-PURITY` is a static rule

The rule walks AST imports under `src/a2kit/` (excluding
`src/a2kit/packages/`) and fires when any `import` or `from ... import`
references `a2kit.packages.*`. This is the inverse of
`A2K-IMPORT-DISCIPLINE` (which forbids fastmcp imports outside
`packages/mcp`).

Implementation: ~30 LOC in `src/a2kit/packages/lint/rules/core_purity.py`,
wired into the `RULES` dispatch tuple. Default-on. Hard gate.

### Decision 8: Backwards-compat sugar for `App.connect`

`App.connect(C)` keeps working *if* `Connections()` plugin is
registered:

```python
def connect(self, conn_class):
    plugin = next((p for p in self._plugins if isinstance(p, Connections)), None)
    if plugin is None:
        raise RuntimeError(
            "App.connect() requires the Connections plugin. "
            "Did you forget `app.use(Connections())`?"
        )
    plugin.adopt(conn_class, self)
    return self
```

But wait — this references `Connections` by name from core, which
violates A2K-CORE-PURITY. The trick: core's `App.connect` doesn't
import `Connections`; it walks plugins for one whose `claim` accepts
the class. If found → adopt. If not → raise generic error pointing at
the registry.

```python
def connect(self, conn_class):
    for plugin in self._plugins:
        if hasattr(plugin, "claim") and plugin.claim(conn_class):
            plugin.adopt(conn_class, self)
            return self
    raise RuntimeError(
        "App.connect(...) found no plugin handling this class. "
        "Did you `app.use(Connections())`? Registered plugins: "
        f"{[type(p).__name__ for p in self._plugins]}"
    )
```

Same effect; no name coupling.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Existing user code breaks at `app.connect(...)` if plugin isn't registered | Clear error message naming the missing plugin. README migration section. CHANGELOG breaking-change call-out. |
| `A2K-CORE-PURITY` rule false-positives on `TYPE_CHECKING` imports | The rule walks runtime imports only; `if TYPE_CHECKING:` blocks are safe. Tests cover. |
| Plugin-protocol overhead on every tool registration | The flatten-and-walk cost is O(plugins × tools), measured once at `build_*_server` time, not per-call. Negligible for realistic apps (<10 plugins, <100 tools). |
| Multiple plugins claiming same target type | First-registered wins. Documented. Future change can add explicit ordering if needed. |
| Refactor breaks tests that reach into `App._connection_types` | Update those tests to query the `Connections` plugin instance directly. The plugin is on `app.plugins()`. |
| Tracker example growing in line count due to explicit plugin registration | Two extra lines (`app.use(Connections()); app.use(Enrichers())`). Worth it: composition root reads as a manifest of what's active. |

## Migration

```python
# Before:
import a2kit

class TrackerConn(a2kit.packages.connections.ConnectionConfig): ...

app = a2kit.App("tracker-mcp")
app.connect(TrackerConn)
app.use(ProjectsRouter())

class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):
    ...

# After:
import a2kit
from a2kit.packages.connections import Connections, ConnectionConfig
from a2kit.packages.enrichers import Enrichers, RouterMixin

class TrackerConn(ConnectionConfig): ...

app = a2kit.App("tracker-mcp")
app.use(Connections())
app.use(Enrichers())
app.use(TrackerConn)
app.use(ProjectsRouter())

class TasksRouter(a2kit.Router, RouterMixin, enricher=tracker_404_enricher):
    ...
```

For users who only have `app.connect(C)`, the back-compat sugar
keeps that line working *as long as* `app.use(Connections())` is
registered. The clearest message is in the error when the plugin is
missing — naming the exact line to add.

## Open Questions

- Should `Plugin` allow async `register(app)`? Most plugin work is
  sync; defer until OTel-style async setup needs it.
- Should plugins have an `unregister(app)` hook for testing? Today
  tests use fresh `App` instances; no cleanup pattern exists.
  Defer.
- Should we ship a `Plugins.from_imports()` helper that scans
  `sys.modules` and instantiates plugins automatically? Tempting but
  fights the explicit-registration contract. Skip.
- Should `app.use(SomePlugin)` (class, not instance) be sugar for
  `app.use(SomePlugin())`? Saves typing `()` for plugins with no
  state. Defer; explicit instantiation makes "what's registered?"
  scannable.
