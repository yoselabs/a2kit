# router-conventions — app-time-tools-tuple-validation delta

## ADDED Requirements

### Requirement: App-time validation rejects decorated-but-unlisted methods

When a Router is added to an App via `App.add_router(router)`, the App SHALL inspect the Router class's own attributes (`type(router).__dict__`) and verify that every method decorated with `@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, or `@a2kit.tool` is listed in the router's `tools` tuple. If any decorated method is missing from the tuple, `add_router` SHALL raise `a2kit.exceptions.A2KitDecoratedMethodNotInTools` with the Router class name and the names of the missing methods.

The check applies to the Router class's own attributes only (`cls.__dict__`), not inherited attributes via MRO. A subclass that inherits a decorated method from a base class without re-listing it does NOT fail validation.

#### Scenario: Drift raises with the missing method name

- **GIVEN** a Router subclass with two `@a2kit.read()`-decorated methods, only one of which appears in `tools = (one,)`
- **WHEN** `App("a").add_router(R())` is called
- **THEN** the call raises `A2KitDecoratedMethodNotInTools`
- **AND** the message identifies the Router class name and the unlisted method's name

#### Scenario: All-listed passes through

- **GIVEN** a Router subclass with two decorated methods, both listed in `tools = (one, two)`
- **WHEN** `App("a").add_router(R())` is called
- **THEN** the call succeeds and both tools are registered

#### Scenario: Inherited decorated method does not fail

- **GIVEN** a base Router `B` with a decorated method `b_tool` listed in its own `tools = (b_tool,)`, and a subclass `S(B)` that inherits `b_tool` without overriding it, with `S.tools = (s_only,)` (its own decorated method)
- **WHEN** `App("a").add_router(S())` is called
- **THEN** the call succeeds; `S`'s validation only inspects `S.__dict__`, not the inherited attribute from `B`

#### Scenario: Synthetic `_MetaRouter` passes

- **GIVEN** `App("a", health_tool=True)` which auto-installs the `_MetaRouter` for `_meta.health`
- **WHEN** the App is built
- **THEN** no `A2KitDecoratedMethodNotInTools` is raised — the synthetic router's `tools = (aggregated_health,)` matches its single decorated method
