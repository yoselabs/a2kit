# a2kit anti-patterns

Concrete failures observed while building two upstream MCPs (a SQL-wrapping
MCP and a Jira/Confluence-wrapping MCP) and a2kit itself. Each entry:
*the mistake* (one paragraph), *what to do instead* (one paragraph),
*citation* (file:symbol).

> Retired entries (vs. pre-v1.0 numbering, kept here for diff reviewers):
>
> - **old #4** ("pin the FastMCP `_tool_manager` seam") — v1.0 builds tools
>   via `FunctionTool.from_function` directly; the underscore-prefixed
>   manager is no longer reached for schema extraction.
> - **old #5** (`pytest11` entry-point auto-registration) — there is no
>   `a2kit.pytest_plugin` module in v1.0. Test fixtures live in
>   `a2kit.packages.testing` and are imported explicitly.
> - **old #6** ("don't ship a `main()` / `MCPRunner`") — v1.0 ships exactly
>   one entry, `a2kit.run(app)`. The lesson now applies to App composition,
>   not runner avoidance; merged into entry #5.
> - **old #14 (Pydantic class-attribute defaults)** — the v1.0 `Router`
>   is a plain Python class, not a Pydantic model. Pattern unreachable.
> - **old #15** (`Capability = str` runtime alias / TC001 noqa) —
>   `Capability` is gone; `a2kit.capabilities.Cap` is a `StrEnum`.
> - **old #16** (Pydantic generic forward refs / `model_rebuild`) —
>   `Router` is no longer a Generic Pydantic model.
> - **old #17** (duplicate of pytest11 retirement above).
> - **old #18** (`--writes` deprecation shim AST pollution) — both the
>   shim and the lint rule A2K010 it defended are gone in v1.0.
> - **old #19** (`KEY_FIELDS: tuple[str, ...]` vs. typed NamedTuples) —
>   v1.0 connections use `pydantic-settings` `ConnectionConfig` triples
>   `(project, env, db)`; the loose-tuple antipattern is unreachable.

## 1. Don't return primitives from a tool

The mistake: typing a tool as `-> str` (or any other primitive — `int`,
`float`, `bool`, `bytes`, `None`) looks natural ("agents read text") but
breaks the wire contract. FastMCP double-serialises strings — the tool
returns a JSON-encoded string, the runtime wraps it in another JSON
envelope, and the agent sees a quoted-quoted blob. Other primitives
produce schemas whose shape is the bare type while real consumers expect
named fields. The only honest answer is a structured shape.

What to do: return a Pydantic model, `dict`, or a list/Page of either. If
you need a string body, wrap it: `return {"format": "markdown", "data": "<text>"}`.
The decorators in `a2kit.tool` enforce this at decoration time — `_check_return`
raises `InvalidToolReturnTypeError` the moment the file imports, citing
the offending type and `antipattern #1` in the message.

As of v0.25 the guard rejects `str`, `int`, `float`, `bool`, `bytes`, and
`None` (both `type(None)` and the literal `None` annotation form). Earlier
versions only caught `-> str`.

Citation: `src/a2kit/tool.py::_check_return`,
`src/a2kit/exceptions.py::InvalidToolReturnTypeError`.

## 2. Pydantic models used as tool return types must be at module scope

The mistake: defining a `class Result(BaseModel): ...` inside the function
that registers a tool, or inside a closure. FastMCP's
`inspect.signature(eval_str=True)` walks the wrapper chain to resolve the
return annotation; `eval_str=True` runs `eval(annotation_str, globals, locals)`
and it cannot see locals from a function that has already returned. Result:
`InvalidSignature: name 'Result' is not defined` at server build time.

What to do: hoist every BaseModel used as a tool return type to module scope.
Two enforced mechanisms catch this — there is no opt-out:

- **Static lint** — rule `A2K-LOCAL-RETURN-MODEL` (in
  `src/a2kit/packages/lint/rules/local_return_model.py`) walks tool return
  annotations and fires on any `BaseModel` subclass whose `ClassDef` is
  inside a function, classmethod, or closure (including generic carriers
  like `Page[Result]`, `list[Result]`). Skips `if TYPE_CHECKING:` blocks.
- **Decoration-time runtime check** — `_check_return_scope` in
  `src/a2kit/tool.py` raises `InvalidToolReturnTypeError` at module-import
  time if the return-type class has `<locals>` in its `__qualname__`. This
  catches the antipattern even when the linter is not run, provided the
  module's annotations are not stringified (`from __future__ import
  annotations` defers to the lint rule, since stringified names cannot be
  resolved without the function's locals dict — which is exactly the
  failure mode being flagged).

Citation: surfaced during a2kit v0.2 build; reproducible with FastMCP and any
locally-defined Pydantic return-type model.
`src/a2kit/packages/lint/rules/local_return_model.py`,
`src/a2kit/tool.py::_check_return_scope`,
`src/a2kit/packages/mcp/server.py::build_mcp_server`.

## 3. `from __future__ import annotations` stringifies return annotations

The mistake: under PEP 563 every annotation is a string at runtime. Code that
checks `if return_annotation is str:` silently misses the case where the
annotation is the literal string `"str"`. Decorators that try to enforce a
return-type contract end up letting `-> str` through.

What to do: resolve annotations through `typing.get_type_hints()` (which
evaluates strings against the function's globals), or accept both `ret is str`
and the stringified form. a2kit's signature helpers route through
`get_type_hints` so PEP 563 modules work uniformly.

Citation: `src/a2kit/signature.py::find_context_param` (uses
`get_type_hints`), `src/a2kit/tool.py::_check_return`.

## 4. Don't add a primitive that overlaps a FastMCP primitive

The mistake: shipping a "tool" decorator that competes with `@server.tool()`.
A wrapper that produces a tool descriptor of its own forces the consumer to
choose between the two stacks; once the wrapper diverges from FastMCP's tool
shape (different argument coercion, different error envelope), every fix in
FastMCP misses your wrapper.

What to do: a2kit's `@a2kit.tool/read/write/list_` decorators only stamp
`A2KitMeta` onto the function. The MCP adapter (`build_mcp_server`) registers
each function as a `FunctionTool` and round-trips the meta into
`tool.meta["a2kit"]` for middleware to read. FastMCP keeps the authoritative
tool list, schema, and dispatch; a2kit owns metadata, not registration.

Citation: `src/a2kit/tool.py`, `src/a2kit/packages/mcp/server.py::build_mcp_server`.

## 5. Don't trust tool-call envelopes the agent passes you as strings

The mistake: an agent's tool-call envelope (`<parameter name="x">...`) leaks
into the body of a string argument; the tool happily processes the broken
value and the failure surfaces three layers down with a confusing error.

What to do: `GuardsMiddleware` scans every string argument for the marker
`<parameter name=` before dispatch and raises `ToolCallContamination` —
short error, points at the offending parameter, asks the agent to retry.
The middleware is wired automatically by `build_mcp_server`.

Citation: `src/a2kit/packages/mcp/guards.py::GuardsMiddleware`,
`src/a2kit/exceptions.py::ToolCallContamination`.

## 6. Read-only is the default; write tools are explicit

The mistake: every tool can mutate. The agent triggers a write on a
production database the user only ever wanted to query. There's no audit
trail because the tool's annotations didn't carry a write/read distinction.

What to do: split decorators by verb. `@a2kit.read` / `@a2kit.list_` stamp
`ToolAnnotations(readOnlyHint=True, destructiveHint=False)` and tag the
tool with `read`; `@a2kit.write` stamps `destructiveHint=True` and tags
`write`. Clients (and CLI/MCP filters) can inspect `meta["a2kit"]` to gate
the destructive set. `WriteNotAllowed` is raised by connection-store
helpers when a read-only connection is asked to mutate.

Citation: `src/a2kit/tool.py::read`, `src/a2kit/tool.py::write`,
`src/a2kit/exceptions.py::WriteNotAllowed`.

## 7. Don't paraphrase the connection-param explanation in every tool

The mistake: every tool docstring re-explains "the `connection` argument is
the saved connection name, not a project key" in slightly different wording.
The agent's mental model drifts; one tool says "connection key", another
says "connection name", a third says "saved profile". Eventually it sends a
project key and gets a confusing not-found error.

What to do: the v1.0 CLI / MCP adapters auto-inject the canonical
connection-parameter description from the `ConnectionConfig` type the
factory resolves. Tool docstrings should *not* re-state it. Lint rule
A2K013 fires when a tool's docstring calls
`a2kit.docs.connection_param_doc(...)` — auto-injection covers it.

Citation: `src/a2kit/packages/lint/rules/shape.py` (A2K013, marker
`_A2K013_MARKERS`).

## 8. OTel must not import the package when no provider is set

The mistake: instrumenting every tool call by unconditionally importing
`opentelemetry.trace` adds a transitive dep to every consumer, including
those that never wanted OTel. Worse: even with the import, the default
no-op provider produces span objects with no attributes; the per-call
allocation cost is real and pure waste.

What to do: ship OTel as an opt-in package. `a2kit.packages.otel`
lazy-imports `opentelemetry-api` inside `install(server)`; `import
a2kit.packages.otel` does *not* pull `opentelemetry` into `sys.modules`.
Declare `pip install 'a2kit[otel]'` as the activation step. Without
`install(server)`, FastMCP runs with zero OTel cost.

Citation: `src/a2kit/packages/otel/middleware.py`,
`src/a2kit/packages/otel/__init__.py::install`.

## 9. Don't ship a TOON encoder; use the vetted dep

The mistake: writing 200 LOC of encoder for a wire format that is "tab,
newline, header row" — re-implementing CSV badly. v0.x carried a 12 LOC
hand-rolled encoder; even that became drift surface as the spec evolved.

What to do: depend on the `toon-format` package and route every call
through `a2kit.packages.formatter.encode_toon`. The byte-identical guarantee
of `format_response` (when `format_hint="toon"`) is enforced by the test
suite: `Response.data == toon_format.encode(raw)` exactly. One seam, one
upstream, no in-tree encoder.

Citation: `src/a2kit/packages/formatter/toon.py::encode_toon`,
`src/a2kit/packages/formatter/__init__.py::format_response`.

## 10. Don't silently auto-stream from stdio MCPs

The mistake: returning an async iterator from a tool when the transport is
stdio. The MCP stdio framing has no streaming semantics; the iterator never
gets serialised, the agent sees an empty result.

What to do: in v1.0, tool authors return concrete values (lists, dicts,
Pydantic models). Streaming is a transport concern handled by FastMCP, not
an a2kit decorator flag. If you need progressive output, use FastMCP's
native progress / partial-result hooks — don't smuggle an async iterator
through a sync return type.

Citation: `src/a2kit/packages/mcp/server.py::build_mcp_server` (no
streaming wrapper exists by design).

## 11. v1.0 — `Depends(...)` parameter defaults (any form)

The mistake: writing `*, conn: T = Depends(get_conn)` or
`Annotated[T, Depends(get_conn)]` on a tool. The `de-magic` change removed
both forms — the framework no longer introspects parameter defaults for
DI sentinels.

What to do: constructor injection on the `Router` class. Pass factories
in via `__init__`, store on `self`, call from each tool method:

```python
class TasksRouter(a2kit.Router):
    def __init__(self, get_store) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.read()
    async def get_task(self, *, connection: str, task_id: str) -> Task:
        store = await self.get_store(connection)
        return store.get(task_id)
```

A senior reader can predict every line without reading the framework source.

Citation: `examples/tracker/routers.py`.

## 12. v1.0 — re-exporting external library symbols from a2kit

The mistake: writing `from a2kit import Depends` (or `Middleware`, `Context`,
etc.). a2kit's `__init__.py` no longer re-exports symbols owned by external
libraries — FastMCP, the MCP SDK, `uncalled_for`, structlog, OTel, cel-python,
vcrpy, syrupy, pydantic-settings. Importing them through a2kit's namespace
hides version coupling and breaks when those libraries evolve independently.

What to do: import from the owning library directly.

```python
from uncalled_for import Depends                                  # not a2kit.Depends
from fastmcp import Context                                       # not a2kit.Context
from fastmcp.server.auth.providers.google import GoogleAuthProvider
```

a2kit's public surface contains only what a2kit owns
(`App`, `Router`, `tool`/`read`/`write`/`list_`, `Cap`, `ToolContext`,
`A2KitMeta`, `WriteNotAllowed`, `ToolCallContamination`, …). The lazy
`__getattr__` in `a2kit/__init__.py` is the authoritative list.

Citation: `src/a2kit/__init__.py::_LAZY_ATTRS`.

## 13. v1.0 — importing `fastmcp` from a non-MCP code path

The mistake: a CLI subcommand handler, a connection helper, or a router
module imports `fastmcp` at module load. Cold-start budget for non-`serve`
modes is sub-second; loading FastMCP costs ~500 ms on first import. Once any
non-`serve` path imports it, `<app> --help` and `<app> schema` lose their
snappiness.

What to do: confine `fastmcp` imports to `a2kit.packages.mcp/*` (and the
`a2kit.packages.otel/*` middleware adapter, which subclasses
`fastmcp.server.middleware.Middleware` but is itself lazy-loaded via
`packages.otel.install()`). The CLI builder lazy-imports `serve_command`
via `LazyGroup`. Lint rule `A2K-IMPORT-DISCIPLINE` enforces the allowlist.

The `tests/test_cold_start.py` subprocess assertions are the contract:
after `import a2kit`, `import a2kit.packages.lint.cli`, and
`import a2kit.packages.connections.cli`, `'fastmcp' not in sys.modules`
must hold.

Citation: `src/a2kit/packages/lint/rules/importing.py::rule_import_discipline`,
`src/a2kit/packages/cli/builder.py::LazyGroup`.

## 14. Don't fold structured findings into log strings

The mistake: a tool body that does `ctx.info(f"found {n} duplicates in {batch}")`.
The data is structured (a count + a batch identifier), but the agent
receives it as an unparsed string. Pattern-matching on log lines is
fragile, and the agent loses any signal that "this was a finding worth
reacting to" vs "this was ambient telemetry."

What to do: use `ctx.event(name, **payload)` for typed narrative milestones
(`await ctx.event("duplicates.found", count=3, batch=4)`) or `ctx.report(payload)`
for typed result chunks declared via `report=ReportT` on the verb decorator.
Both stream immediately to the client and arrive as structured data — the
agent can filter by event name, dispatch on report type, or surface the
payload to the user without parsing the log line.

Citation: `src/a2kit/packages/mcp/context.py::FastMCPContextAdapter`,
`src/a2kit/packages/cli/context.py::StderrToolContext`.

## 15. Don't rely on `A2KIT_LDD=off` env var inside test code

The mistake: integration tests that disable the LDD channels by setting
`A2KIT_LDD=off` in the test environment. The env var is read once at
`App.__init__`, so any App constructed before the env mutation keeps the
old value, and any App constructed in a child process inherits the parent
process's env at fork time. Test results become order-dependent and
hard to reproduce.

What to do: pass `app.set_ldd(reports=False, events=False)` explicitly
in the test's setup. This works regardless of import order, regardless
of how the App was constructed, and is visible at the test's call site
(no hidden env spookiness).

Citation: `src/a2kit/app.py::App.set_ldd`.

## 16. Factories are functions, not classes

The mistake: introducing a base class (`Store[ConnT]`, `Loader[ConnT]`) so
the framework can introspect a Generic parameter and "automatically" wire
construction. That's clever for clever's sake — `__orig_bases__` walking
reads as advanced-Python sleight-of-hand to a senior reviewer.

What to do: write a plain function.

```python
async def get_store(connection: str) -> TrackerStore:
    conn = await _conn_store.load((connection,))
    return TrackerStore(conn)


app.add_router(TasksRouter(get_store))
```

The "store" is a plain class with a constructor. The "factory" is a plain
function. Composition is the user's job, not the framework's.

Citation: `examples/tracker/server.py`, `examples/tracker/store.py`.

## 17. Stores SHOULD be cheap to construct

The mistake: a `TrackerStore.__init__` that opens a database connection,
loads cached state, or does any I/O. The runtime constructs a fresh store
per tool call. Slow `__init__` adds proportional latency to every
invocation.

What to do: keep `__init__` to attribute assignment. Do I/O in methods
(`load_state`, `replace`, `query`). If you genuinely need pooling or
caching across calls, wrap a singleton inside the store and cache it on
the connection (or on the store class).

Citation: `examples/tracker/store.py::TrackerStore.__init__`.

## 18. Three named verbs, not one polymorphic `use`

The mistake: re-introducing `app.use(thing)` polymorphism — same call
accepts a Router, a Click group, a middleware, an arbitrary class, etc.,
with type-driven dispatch. It reads compactly at the call site, but the
runtime walks an `isinstance` ladder, the order matters, and the next
unfamiliar type silently miscategorises (the original `pluggable-core`
ladder mismatched ABCMeta's `register()` against the Plugin Protocol).

What to do: three named verbs, each takes one specific kind of thing.

```python
app.add_router(TasksRouter(get_store))
app.add_cli(connections_cli(TrackerConn))
app.add_mcp_middleware(my_middleware)
```

The reader sees `add_router(...)`, knows it's a Router. No surprises.

Citation: `src/a2kit/app.py::App.add_router`.

## 19. v0.21 — feature kwargs accumulating on the verb decorator

The mistake: every new feature parks a kwarg on `@a2kit.read/write/list_/tool`.
v0.20 had four (`enricher=`, `list_view=`, `report=`, `router_slug=`); the
fifth and sixth were one more capability away. Each kwarg drags a typed
field into `A2KitMeta`, a consumer in core, and a permanent obligation
on the central decorator's signature. To a senior reviewer this reads as
"the framework parks feature state wherever it's convenient."

What to do: each feature owns a stacked decorator that writes a namespaced
key into `A2KitMeta.extra` (the single dict-typed extension point).
Adapters read from `extra` at registration time. The verb decorator's
kwargs collapse to `(name, tags, annotations)` and stop growing.

```python
# v0.20 (deprecated)
@a2kit.read(enricher=my_enricher, report=BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...

# v0.21
@a2kit.read()
@enriches(my_enricher)
@reports(BatchReport)
async def import_csv(self, *, ctx, file: str) -> dict: ...
```

The boundary is enforced by lint (`A2K-CORE-CLEAN`, `A2K-EXTRA-NAMESPACE`):
core source can't reference feature identifiers, and `extra` keys must be
namespaced (`a2kit.*` or `<package>.*`).

Citation: `src/a2kit/tool.py::_stamp` — three kwargs, full stop.

## 20. ~~v0.21 — auto-derived Router slugs~~ (RETRACTED in v0.22)

**Original concern:** combinatorial slugify (`Router` suffix strip +
camelCase split + lowercase) chained three transformations and let the
naming convention drift silently.

**Why retracted:** the antipattern was *combinatorial* slug derivation,
not derivation per se. v0.22 ships a single, documented rule: strip
exactly one trailing `Router` suffix (case-sensitive), lowercase the
rest. One transformation. Collisions error at app build time, so
silent drift is impossible. Explicit `name = "..."` still wins for
when the wire name needs to be anchored against future class renames.

```python
class TasksRouter(a2kit.Router):
    pass
# slug → "tasks"  (auto-derived)

class TasksRouter(a2kit.Router):
    name = "task-list"
# slug → "task-list"  (explicit override; survives class rename)
```

The forcing function for explicit naming has shifted: pick `name = "..."`
when the wire identity must outlive code refactors, not merely to avoid
ugly defaults. Citation: `src/a2kit/routers.py::_derive_slug`.

## 21. v0.21 — ContextVar + monkey-patch to propagate state into Click subcommands

The mistake: stash the active `App` in a module-level `ContextVar`, then
monkey-patch `click.Group.main` to set/reset the var around the dispatch
call so lazy subcommands can `_APP_CTX.get()`. Two layers of indirection
to thread one argument. The patch is invisible at call sites, the
ContextVar reads succeed in unrelated test contexts, and any future
maintainer hits the same "where does `app` come from?" question every
time they read a subcommand body.

What to do: the CLI builds per-app, so close over `app` in the command
factory. Lazy subcommands become `Callable[[], click.Command]` factories
that capture `app` at registration time. No ContextVar, no monkey-patch.

Citation: `src/a2kit/packages/cli/builder.py::build_full_cli` —
`build_schema_command(app)` and `_build_serve_factory(app)` close over
the active App; `LazyGroup` stores factories, not import strings.

## 22. v0.22 — `def __init__(self, get_store: GetStore)` factory closure on Routers

The mistake: every router carries a `get_store: Callable[[str], Store]`
closure in `__init__`, then every tool method does
`store = await self.get_store(connection)` as the first line. The
factory exists so the connection-scoped Store can be materialized per
call from a process-wide router. It works, but the pattern repeats
across every project, every router, every tool — a cliché the framework
should absorb.

What to do: use `App.provide(T, factory=None)` to register a typed
provider once, then declare the resolved type as a tool kwarg. The
container reads `__init__` annotations and chains; the wire `connection`
is auto-included on the schema when the chain reaches the
auto-installed `ConnectionConfig` provider.

```python
# Before (v0.21):
class TasksRouter(a2kit.Router):
    def __init__(self, get_store: GetStore) -> None:
        super().__init__()
        self.get_store = get_store

    @a2kit.read()
    async def get_task(self, *, connection: str, task_id: str) -> Task:
        store = await self.get_store(connection)
        return store.get(task_id)

# After (v0.22):
class TasksRouter(a2kit.Router):
    @a2kit.read()
    async def get_task(self, *, store: TrackerStore, task_id: str) -> Task:
        return store.get(task_id)

app = (
    a2kit.App("t")
    .add_router(TasksRouter())
    .provide(TrackerStore)                   # class-as-factory
    .add_cli(connections_cli(TrackerConn))   # auto-installs TrackerConn
)
```

Citation: `src/a2kit/packages/connections/container.py::Container`.

## 23. v0.22 — repeating `@enriches(...)` on every method of a router

The mistake: an exception enricher specific to a router (e.g.
`tracker_404_enricher`) gets stacked on every single tool via a
per-method decorator. Eight tools means eight identical lines. The
enricher is a *router-level* invariant masquerading as per-method
state.

What to do: declare the enricher chain as a class attribute. Add a
`def enrich(self, exc) -> str | None` method only when an enricher
genuinely needs `self`. Resolution: instance method first, then class
list, first non-None wins.

```python
# Before (v0.21):
class TasksRouter(a2kit.Router):
    @a2kit.read()
    @enriches(tracker_404_enricher)
    async def get_task(self, ...): ...

    @a2kit.write()
    @enriches(tracker_404_enricher)
    async def create_task(self, ...): ...

# After (v0.22):
class TasksRouter(a2kit.Router):
    enrichers = [tracker_404_enricher]

    @a2kit.read()
    async def get_task(self, ...): ...

    @a2kit.write()
    async def create_task(self, ...): ...
```

Enricher signature also tightens: `(exc) -> str | None`. The framework
re-raises with the enriched message — enrichers stop carrying exception
construction logic. Citation:
`src/a2kit/packages/cli/builder.py::_wrap_with_enricher`.

## 24. v0.22 — re-enumerating row fields the return type already declares

The mistake: `@lists(default_fields=("id", "title"), selectable_fields=
("id", "title", "status", "assignee", "priority", "project_id",
"created_at", "done"))` lists every field of `Task` by hand, on top of
a tool that already declares `-> list[Task]`. The Pydantic model knows
its fields; copying them into the decorator is duplication waiting to
drift.

What to do: stop passing `selectable_fields` unless you specifically
want a strict subset. The framework derives the full set from the
return-type annotation (`list[T]` → `T.__pydantic_fields__` or
`dataclasses.fields(T)`). Pass only `default_fields` (the projection
default) and `page_size` (when you want pagination). The standalone
`@lists(...)` decorator is also retired — list-view settings live on
the consolidated `@a2kit.list_(...)` since list-view is intrinsic to
the list verb.

```python
# Before (v0.21):
@a2kit.list_()
@lists(
    default_fields=("id", "title", "status", "assignee"),
    page_size=20,
    selectable_fields=("id","title","status","assignee","priority","project_id","created_at","done"),
)
async def list_tasks(...) -> list[Task]: ...

# After (v0.22):
@a2kit.list_("id", "title", "status", "assignee", page_size=20)
async def list_tasks(...) -> list[Task]: ...
```

Citation: `src/a2kit/tool.py::list_` and `_derive_selectable_fields`.


## 25. v0.27 — kwargs on `ctx.info / warning / error / debug`

`fastmcp.Context.info(message, logger_name=None, extra=None)` is the
real upstream signature. The CLI stub historically widened it to
`info(msg, **fields)` so structured narrative logging would render
nicely on stderr. Tools written against the widened shape worked on
CLI and through the in-process test client (a CLI subclass) but
crashed on real MCP transport with
`TypeError: Context.info() got an unexpected keyword argument 'foo'`
— masked as `ToolError: Error calling tool 'X'` to agents under
`App(debug=False)`.

Use `a2kit.ldd.info(ctx, msg, **fields)` (and `warning` / `error` /
`debug` siblings) for structured field-bearing logging. The free
function dispatches internally: `await ctx.log(level=..., message=...,
extra={...})` on MCP, `_emit(LEVEL, msg, fields)` on CLI. Same wire
format, same rendering, both transports green. `ctx.info("plain
message")` and `ctx.info("msg", extra={...})` (fastmcp's narrow form)
continue to work; only the `**kwargs` shape was an invention.

```python
# Before:
await ctx.info("starting import", file=file, batch_size=batch_size)

# After:
from a2kit.ldd import info
await info(ctx, "starting import", file=file, batch_size=batch_size)
```

Citation: `src/a2kit/packages/ldd/__init__.py::log` (the dispatcher);
`tests/test_context_surface.py::test_field_bearing_logging_is_only_on_ldd_not_on_ctx`
(the architectural-invariant test that catches regressions).


## 26. v0.31 — reaching into `A2KitMeta.extras` by string key

Pre-v0.31, `A2KitMeta.extra` was a `dict[str, Any]` open extension slot.
Verb decorators and routers wrote namespaced keys (`"a2kit.report_type"`,
`"a2kit.router_slug"`, `"a2kit.list_view"`, `"a2kit.surfaces"`,
`"a2kit.report_schema"`); consumers read them with `meta.extra.get(...)`.
The open-dict shape carried no type guarantees and let typos go silent.

The v0.31 surface is `A2KitMeta.extras: A2KitMetaExtras`, a pydantic
`BaseModel` with named fields. Read and write by attribute access:

```python
# Before:
report_type = meta.extra.get("a2kit.report_type")
meta.extra["a2kit.router_slug"] = "tasks"

# After:
report_type = meta.extras.report_type
meta.extras.router_slug = "tasks"
```

The wire-projection on `tool.meta["a2kit"]["extras"]` carries the same
attribute names (without the `a2kit.` prefix). New extras land as new
fields on `A2KitMetaExtras`, not as string keys.

Citation: `src/a2kit/metadata.py::A2KitMetaExtras`;
`src/a2kit/packages/lint/rules/purity.py::rule_extra_namespace`
(enforces the attribute-name set).

## 27. function-local imports to dodge a package cycle

The mistake: two packages need each other, so instead of fixing the
dependency direction you move one import inside a function body. The
module-scope graph looks acyclic and the type checker stays quiet, but
the cycle is still there — it just runs at first call instead of at
import. It compounds: `mcp/_wrappers.py` carried 21 `: Any`
annotations because importing the real `App` / `Router` types would
have closed an `mcp ↔ cli` cycle, so the wrappers lost all type
safety. A `TYPE_CHECKING`-guarded import hides a cycle the same way —
`ty` survives it, but the design cycle is real and still constrains
every future refactor.

What to do instead: treat a function-local or `TYPE_CHECKING` import of
a sibling package as a smell to investigate, not a fix. Break the cycle
structurally — relocate the misfiled symbol to the package that owns it
(`run_code` was CLI orchestration misfiled in `codemode`), extract a
shared dependency into a lower leaf package (`StderrToolContext` →
`packages/context`), or invert a parameter to the narrowest type that
works (`run_checks` needed a `Resolver`, not the whole `App`). A
deferred import is legitimate only for a genuine cold-start guard on a
forward (acyclic) edge — never to paper over a back-edge.

Citation: `src/a2kit/packages/mcp/_wrappers.py` (module-scope `App` /
`Router` imports); the `decouple-import-cycles` change.

## v0.36 — DI scoped-lifecycle anti-patterns

### `_ensure()` lazy-init on a `provide()`-registered class

```python
# Don't:
class BrowserPool:
    def __init__(self) -> None:
        self._b = None

    async def _ensure(self) -> Browser:
        if self._b is None:
            self._b = await launch_browser()
        return self._b

app.provide(BrowserPool)
```

The lazy-init pattern made sense before the container had lifecycle
awareness. In v0.36 the container enters the resource on first
`Container.get(T)` and unwinds on scope exit — `_ensure()` duplicates
machinery the framework already provides and leaks resource state on
exception. Register the resource with `__aenter__`/`__aexit__` and let
the container drive entry/exit:

```python
# Do:
class BrowserPool:
    async def __aenter__(self) -> "BrowserPool":
        self._b = await launch_browser()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._b.close()

app.provide(BrowserPool)
```

### Parameterized lambdas as factories

```python
# Don't:
app.provide(SqliteResource, lambda conn: SqliteResource(conn))
```

Lambdas can't carry parameter type annotations, so the framework
can't chain-resolve `conn` from another registered provider. The
factory looks injectable but isn't. Use `def`:

```python
# Do:
def make_sqlite(conn: ConnectionConfig) -> SqliteResource:
    return SqliteResource(conn)

app.provide(SqliteResource, make_sqlite)

# Or just register the class directly — its __init__ annotations work:
app.provide(SqliteResource)  # SqliteResource.__init__(self, conn: ConnectionConfig)
```

### `aclose` / `close` without `__aenter__`/`__aexit__`

```python
# Don't:
class HttpClient:
    async def aclose(self) -> None:
        await self._session.close()
```

In v0.35 the framework auto-detected `aclose` / `close` as cleanup
hooks. v0.36 retires that — only `__aenter__`/`__aexit__` is honored
(single-protocol convention). Resources with bare `aclose` / `close`
methods will NOT be cleaned up at app exit. Wrap them:

```python
# Do:
class HttpClient:
    async def __aenter__(self) -> "HttpClient":
        self._session = await new_session()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._session.close()
```

Or use `@asynccontextmanager`:

```python
@asynccontextmanager
async def make_http_client() -> HttpClient:
    session = await new_session()
    try:
        yield HttpClient(session)
    finally:
        await session.close()

app.provide(HttpClient, make_http_client)
```

### Service-locator: `ctx.get(T)` for conditional dependencies

```python
# Don't:
async def extract(url: str, ctx: ToolContext) -> str:
    if needs_js(url):
        browser = await ctx.get(Browser)  # service locator
        return await browser.scrape(url)
    return await plain_get(url)
```

Service-locator pulls hide dependencies from the function signature —
the tool's wire surface no longer documents what it needs. Use
`Lazy[T]` instead; same conditional-entry semantics, declared in the
signature:

```python
# Do:
from a2kit.packages.di import Lazy

async def extract(url: str, browser: Lazy[Browser]) -> str:
    if needs_js(url):
        b = await browser()
        return await b.scrape(url)
    return await plain_get(url)
```

See `docs/patterns/conditional-deps.md`.

### App-scope factory depending on a per-call type

```python
# Don't:
class Reporter:
    def __init__(self, tx: Transaction) -> None:
        self._tx = tx

app.provide(Transaction, per_call=True)
app.provide(Reporter)  # app-scope by default — depends on a per-call type
```

The framework rejects this at `async with app:` with a clear scope
violation. Per-call types live for one dispatch; an app-scope instance
would cache a stale per-call value. Either move `Reporter` to per-call
too, or use `Lazy[Transaction]` so the closure resolves the per-call
type from the live dispatch scope at use time.

Citation: `src/a2kit/packages/di/container.py::_validate_scope_graph`.

### `app.override(T, fake)` does not exist — re-register instead

```python
# Don't:
app.override(LLM, FakeLLM())  # AttributeError — method removed
```

There is no dedicated test-override seam. Re-register the type at the
composition root; `provide()` is last-write-wins:

```python
# Do (in build_test_app):
app.provide(LLM, lambda: FakeLLM())
```

See `docs/patterns/test-overrides.md`.
