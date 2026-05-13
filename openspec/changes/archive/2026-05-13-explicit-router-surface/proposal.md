# Explicit Router surface (eliminate above-ceiling magic)

## Why

FastMCP defines a clear "magic ceiling": the framework reads what you
wrote, and never invents what is missing. Tool authors can answer
"what gets registered?" by scanning their own source. a2kit's
`Router` base currently exceeds that ceiling in three places. Each
makes the code less readable, harder to type-check, and impossible to
audit without scanning framework source.

**A1. Router slug auto-derived from `type(self).__name__`.**
`src/a2kit/routers.py:_derive_slug` strips a trailing `Router` and
lowercases the rest. A reader looking at `class TasksRouter(Router):`
cannot answer "what is the slug?" without reading the framework's
derivation rule. The slug is invented from the class name; the source
file does not contain the answer.

**A2. Router tools discovered by walking `dir(self)`.**
`Router.__init__` walks every attribute on the instance, swallows
exceptions from broken property descriptors, and collects everything
that happens to carry an `_a2kit` meta marker. The reader has no list
of "the tools on this router"; the framework computes one by
introspecting at runtime. Property descriptors that raise silently
drop tools. The bare-except branch is exactly the "above ceiling"
shape `loud-degrade-everywhere` is trying to eliminate.

**A2.5/A2.6. Router lifecycle and providers are framework-read side channels.**
`App.add_router(r)` (`src/a2kit/app.py:130-157`) silently auto-installs
`r.providers` onto the DI container and auto-appends `r.on_startup` /
`r.on_shutdown` to `App._startup_handlers` / `_shutdown_handlers`.
A reader inspecting the Router subclass cannot tell that those
attributes feed framework wiring without reading `add_router`'s
source. To close this, **all Router class attributes that drive
registration SHALL be explicit declarations the reader sees on the
page**: `slug`, `tools`, `providers`, and `lifespan` are the single
discovery surface. `App.add_router(r)` legitimately reads them —
same shape as FastMCP reading `@mcp.tool` decorators on a module.
No `__init_subclass__`, no `dir()`, no other side-channels.

**A3. Decorator stacking via `PENDING_EXTRA_ATTR`.**
`@reports(T)` (and any other staging decorator) writes
`fn._a2kit_pending_extra["a2kit.report_type"] = T`. The verb decorator
flushes that side-channel into `meta.extra`. Two decorators
communicating through a hidden attribute on the wrapped function is
above ceiling: a reader who only inspects `@a2kit.read()` cannot see
the `reports=` configuration, and a reader who only inspects
`@reports(T)` cannot see how it reaches metadata.

All three patterns share the same shape: the framework computing
what the author should have written explicitly. This proposal makes
every one of them a written-down attribute on the class or a kwarg on
the verb decorator. After this change, a reader can answer "what is
the slug?", "which methods are tools?", and "what report type does
this tool produce?" by reading the Router subclass body — no
framework source required.

## What Changes

### A1. Require an explicit `slug` class attribute

- Remove `_derive_slug` from `src/a2kit/routers.py`.
- Remove the `name` constructor arg and `name` class attribute.
- Add a required `slug: ClassVar[str]` class attribute on every
  `Router` subclass. Missing slug raises `TypeError` at
  `Router.__init__` time naming the subclass.
- The slug is a string literal in the subclass body, visible to
  type checkers and to `grep`.

### A2. Require an explicit `tools` class attribute

- Remove `_collect_methods` (the `dir(self)` walk) from
  `src/a2kit/routers.py`.
- Add a required `tools: ClassVar[tuple[Callable[..., Any], ...]]`
  class attribute. The author lists every tool method in the tuple.
- `Router.__init__` iterates the tuple, binds each entry to the
  instance via `getattr(self, fn.__name__)`, and stamps router-slug
  on its meta. Missing meta on any listed entry raises `TypeError`
  naming the offending method.
- A lint rule (out of scope here, tracked as a follow-up TODO)
  reports any method decorated with `@a2kit.read/write/list_/tool`
  that is NOT listed in `tools` on the enclosing Router.

### A2.5. Router lifecycle becomes an explicit `lifespan` method

- Remove the auto-bridge in `App.add_router` that scans for
  `on_startup` / `on_shutdown` methods in the Router subclass body
  and appends them to `App._startup_handlers` / `_shutdown_handlers`
  (`src/a2kit/app.py:149-161`).
- Routers that need resources expose a single
  `@asynccontextmanager async def lifespan(self):` method (or the
  base class declares it as `None` by default; subclasses override).
- `App.add_router(r)` reads `r.lifespan` and composes it into the
  App's top-level lifespan using `a2kit.lifespan.compose(...)`,
  introduced by the sibling proposal `lifespan-over-lifecycle-hooks`.
- A reader looking at `class TasksRouter(Router):` sees the lifespan
  body in one place; startup work appears before `yield`, shutdown
  after. No second decorator surface to wire.

### A2.6. Router `providers` becomes an explicit declared class attribute

- No change to the public surface: `providers: ClassVar[tuple[...]]`
  remains the supported shape and `App.add_router(r)` continues to
  read it and install each entry on the container.
- The spec change is documentary: `providers` is **explicitly
  promoted to a peer of `slug` and `tools`** — a class-level
  declaration that `add_router` legitimately reads, not framework
  inference. The previous spec did not pin this; this proposal
  pins it so future refactors don't move `providers` into a
  side-channel (e.g. `__init_subclass__` registry, decorator
  protocol).

### A3. Fold staging decorators into verb-decorator kwargs

- Remove `stage_extra` and `PENDING_EXTRA_ATTR` from
  `src/a2kit/metadata.py`.
- Add `reports: type | None = None` (and any other current staging
  inputs surfaced today via `@reports`-style decorators) as kwargs on
  `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, and `@a2kit.tool`.
- Verb decorators populate `A2KitMeta.extra` (or the typed extras
  shape introduced by `align-with-pydantic-and-stdlib`, once that
  lands) from their own kwargs directly. No side-channel attribute
  on the function object.
- The standalone `@reports(...)` decorator (and the
  `a2kit.packages.…` module hosting it, if any) is removed. Sweep
  call sites across this repo and the `examples/` tree.

### Capabilities

- `router-conventions` — slug becomes a required class attribute
  (no derivation); tools become a required class attribute (no
  `dir()` walk); `providers` is pinned as an explicit class
  attribute; `lifespan` is added as the lifecycle surface for
  Routers.
- `app-lifecycle` — narrow delta: **Router.lifespan composition
  rule** only. `App.add_router(r)` SHALL compose `r.lifespan` (when
  present) into the App's top-level lifespan via
  `a2kit.lifespan.compose(...)`. The broader `lifespan=` surface
  on `App.__init__` is owned by the sibling proposal
  `lifespan-over-lifecycle-hooks`; this delta does not duplicate
  it.
- `verb-decorators`, `tool-descriptors` — as before.

### Coordination with sibling proposals

- `lifespan-over-lifecycle-hooks` introduces `App.lifespan`,
  `a2kit.lifespan.compose(*lifespans)`, and removes
  `@app.on_startup` / `@app.on_shutdown`. **This change owns
  `Router.lifespan`**; **the sibling owns `App.lifespan`** and the
  `compose` helper. Both ship paired in v0.31.0 — neither lands
  alone. The merge order is: sibling first (introduces `compose`),
  this proposal second (consumes `compose` in `add_router`).
- `align-with-pydantic-and-stdlib` introduces a typed
  `A2KitMetaExtras` shape. Once both land, `A2KitMeta.extra` is
  fully typed AND populated only from verb-decorator kwargs (this
  proposal removes the side-channel path; the sibling types the
  destination). Order does not matter; the two changes compose.
- `loud-degrade-everywhere` plans to `WARN_ONCE` the bare-except
  branch in `routers.py`'s `dir()` walk. Once **this** proposal
  lands the `dir()` walk is gone entirely, and that
  `loud-degrade-everywhere` site becomes a no-op. The
  loud-degrade proposal should drop it from its scope when it
  picks up the post-this-change state.

## Impact

- **Affected code**:
  - `src/a2kit/routers.py` — drop `_derive_slug` and
    `_collect_methods`; add slug-required + tools-required checks.
  - `src/a2kit/metadata.py` — drop `stage_extra` and
    `PENDING_EXTRA_ATTR`.
  - `src/a2kit/__init__.py` (or wherever verb decorators live) —
    add `reports=` kwarg to `read`/`write`/`list_`/`tool`.
  - Any `@reports(...)` definition and its module — removed.
  - Every `Router` subclass in `src/` and `examples/` — adds
    `slug = "..."` and `tools = (...)` class attributes.
  - Every `@reports(T)` call site — folded into the adjacent verb
    decorator's `reports=T` kwarg.
  - Tests covering slug derivation and `dir()`-based discovery —
    rewritten to assert explicit-attribute behaviour.

- **APIs**: BREAKING.
  - Every Router subclass author MUST add `slug` and `tools`. The
    "two lines of boilerplate per Router" cost is intentional; the
    benefit is one-pass readability and type-checker visibility.
  - Every Router subclass using `on_startup` / `on_shutdown` methods
    MUST migrate to a single `@asynccontextmanager async def
    lifespan(self):` method.
  - Every `@reports(...)` stacked-decorator user MUST fold it into
    the verb decorator's `reports=` kwarg.
  - **Target release: v0.31.0**, paired with
    `lifespan-over-lifecycle-hooks`. Both ship together. v1.0 is
    deferred because the signature-rewrite (A4) and wire-scope
    synthesis (A6) above-ceiling items are still pending; closing
    the Router providers/lifecycle gap (this revision) was the only
    remaining v1.0-blocker for the Router surface itself. See
    `design.md` D4 for the full rationale.

- **Dependencies**: none.

- **Risk**: low-mechanical. The migration is a sweep — every Router
  gets two new lines; every `@reports` is rewritten into a kwarg. No
  semantic change to tool dispatch, registration, or wire format.

- **Cross-SDK note**: the Python SDK becomes marginally more
  verbose to write (two extra lines per Router) and meaningfully
  easier to read. The Rust/TS SDKs were always going to require
  explicit slug + tool listing (no equivalent to Python's
  `dir()`-walk reflection), so this lands the Python surface on
  the same shape, simplifying cross-SDK documentation.
