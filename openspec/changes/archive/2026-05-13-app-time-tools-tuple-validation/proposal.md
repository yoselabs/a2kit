# App-time validation of `tools` tuple completeness

## Why

A `@a2kit.read/write/list_/tool`-decorated method that's missing from
its Router's `tools` tuple is silently invisible on every transport.
No error, no warning. The method exists, gets decorated, has `A2KitMeta`
attached — but never reaches `FunctionTool.from_function`, never
appears in `list_tools`, never gets called. The footgun is tier-1:
adding a tool, forgetting to update the tuple, deploying, debugging
why "the tool isn't there."

v0.31's CHANGELOG promised a static lint rule for this:

> a decorated-but-unlisted method silently does NOT register
> (a follow-up lint rule will flag this drift statically)

The lint rule hasn't shipped. Per the devil's-advocate analysis on
deferred wish #5, the *better* enforcement site is App-construction
time — `App.add_router()` already iterates the tuple at
`routers.py:86`. One extra walk of `vars(cls)` checking for
`_a2kit`-tagged callables and set-diffing against the tuple is
cheaper than a lint plugin, safer than `Router.__init__` (which can
fire mid-refactor before the tuple is updated), and runs in every
test suite + every dev `python -m app` boot.

## What Changes

- `App.add_router(router)` walks `vars(type(router))` to find every
  attribute that's a callable carrying `A2KitMeta` (via `get_meta`).
  Sets the diff `decorated_methods - tools_methods`. If non-empty,
  raises `A2KitDecoratedMethodNotInTools` with the router class
  name, the decorated method names, and the corrective action
  ("add to `tools`, or remove the `@a2kit.*` decorator").

- Exception lives in `src/a2kit/exceptions.py` alongside the other
  framework-internal diagnostics.

- The check applies to every router added to an App, including the
  synthetic `_MetaRouter` for `_meta.health` (which obeys the
  invariant by construction).

- Regression test in `tests/test_routers.py` (or new
  `tests/test_app_validation.py`) — define a Router with a
  decorated-but-unlisted method, assert
  `app.add_router(router)` raises with a precise message.

## Impact

- **Affected specs**: `router-conventions` — add a new requirement
  *"App-time validation rejects decorated-but-unlisted methods"*.
- **Affected code**:
  - `src/a2kit/app.py` — `add_router` calls a new helper
    `_validate_router_tools(router)` immediately after the router
    type is confirmed. Helper raises on drift.
  - `src/a2kit/exceptions.py` — new
    `A2KitDecoratedMethodNotInTools(A2KitError, TypeError)`.
  - `tests/test_routers.py` or new `tests/test_app_validation.py`
    — regression test.
- **APIs**: BREAKING for any consumer that *intentionally* decorates
  a method but excludes it from `tools` (e.g. for staging an
  unreleased tool). Workaround: comment out the decorator instead,
  or use the `visibility="hidden"` extras kwarg. Search of `src/`,
  `examples/`, and `tests/` for the pattern is part of task 0.
- **Dependencies**: none.
- **CI cost**: one extra `vars(cls)` walk per `add_router` call; ~µs.
- **Risk**:
  - **`_MetaRouter` self-test**: the synthetic router added by
    `App(health_tool=True)` must pass the same check. Mitigated by
    `_MetaRouter`'s `tools = (aggregated_health,)` already being
    correct.
  - **Inherited decorated methods**: if a Router subclass inherits a
    decorated method from a base class and overrides nothing, the
    method shows up in `vars(cls)` via MRO walk. The check uses
    `cls.__dict__` directly (own attributes only) to avoid this.
- **Out of scope**: a separate lint rule (replaceable now that
  App-time enforces); per-method `__a2kit_hidden__` opt-out flag (no
  caller demand).
