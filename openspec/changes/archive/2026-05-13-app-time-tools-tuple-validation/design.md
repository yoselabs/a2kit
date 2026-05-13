# Design — app-time-tools-tuple-validation

## Context

The router contract today verifies that *listed* `tools` entries
are decorated (`routers.py:97-105`). It does NOT verify the
inverse: that every decorated method on the class is listed. This
asymmetry is the source of the silent-invisible-tool footgun.

The proposal lands the inverse check, at App-construction time.

## D-WHERE — `App.add_router`, not `Router.__init__`

Two enforcement sites considered:

1. `Router.__init__(self)` — fires when `R()` is constructed.
2. `App.add_router(self, router)` — fires when the App pulls the
   router in.

`Router.__init__` is too early for two reasons:

- **Mid-refactor flow**: contributor adds `@a2kit.read()` to a
  method, runs `python -m my_app` to test, the module-level
  `R()` instantiation crashes before they can update the tuple.
  Friction.
- **Multiple-router decomposition**: A Router class may be
  defined in a module that imports another module's tooling.
  An incomplete-but-not-yet-used Router class instantiating in
  import order can crash before the App ever sees it.

`App.add_router` runs at the boundary where the framework
*actually cares* about the invariant: when the router becomes
part of an App that serves traffic. By that point the consumer
has signalled "this is a real router, register its tools." The
check belongs there.

## D-DETECTION — walk `cls.__dict__`, not `vars(cls)`

`vars(cls)` returns the class's own attributes only (same as
`cls.__dict__`). Either works. Use `cls.__dict__` directly for
clarity — that's the canonical "own attributes" surface.

Crucially, the walk MUST NOT use `dir(cls)` or any MRO walk:
inherited decorated methods from a Router base class should not
fail validation on the subclass that didn't add them itself. If a
subclass wants to expose an inherited tool, it lists the inherited
method in its own `tools` tuple explicitly.

## D-DETECTION-LOGIC

```python
def _validate_router_tools(router: Any) -> None:
    cls = type(router)
    tools_names = {getattr(fn, "__name__", None) for fn in (cls.tools or ())}
    decorated_methods = {
        name
        for name, attr in cls.__dict__.items()
        if callable(attr) and get_meta(attr) is not None
    }
    missing = decorated_methods - tools_names
    if missing:
        raise A2KitDecoratedMethodNotInTools(
            router_cls_name=cls.__name__,
            missing=sorted(missing),
        )
```

`cls.tools` is guaranteed to be a tuple of callables by the time
`add_router` runs — `Router.__init__` already enforced that. So
the helper's preconditions hold.

## D-EXCEPTION

```python
class A2KitDecoratedMethodNotInTools(A2KitError, TypeError):
    """Raised when a Router subclass has decorated methods that
    are not listed in its `tools` tuple. Without this check, the
    methods register no tools — they're invisible on every
    transport."""

    def __init__(self, router_cls_name: str, missing: list[str]) -> None:
        self.router_cls_name = router_cls_name
        self.missing = missing
        missing_quoted = ", ".join(repr(m) for m in missing)
        super().__init__(
            f"Router {router_cls_name!r} has decorated methods that "
            f"are not in its `tools` tuple: {missing_quoted}. "
            f"Either add them to `tools = (...)`, or remove the "
            f"`@a2kit.read/write/list_/tool` decorator from methods "
            f"you don't want registered."
        )
```

`A2KitError` for the framework-prefix; `TypeError` because it's a
class-shape error caught at construction time (parallels the
existing `slug`/`tools` invariants in `Router.__init__` which also
raise `TypeError`).

## Alternatives considered

### Alt-A — ship a custom ruff/pylint plugin

Pre-existing plan from v0.31 CHANGELOG. Rejected because:

- Requires plugin distribution + consumer config to opt in.
- Doesn't fire at runtime; a `pytest` run against an App that has
  the drift will pass.
- App-time check costs ≈ same effort to write; covers both CI
  and runtime.

### Alt-B — enforce in `Router.__init__`

Rejected per D-WHERE above.

### Alt-C — opt-in flag (`App(validate_routers=True)`)

Hides the safety net behind an opt-in. The whole point of v0.31's
CHANGELOG note was that this should be on by default. Opt-in is
worse than no check (consumers don't discover the flag).

## Risks

- **`_MetaRouter` self-check**: the synthetic router added by
  `App(health_tool=True)` is built inline at
  `app.py:153-163`. Its `tools = (aggregated_health,)` correctly
  matches its single decorated method. Pre-validated.
- **Backwards compat**: any consumer who *intentionally* decorated
  a method without listing it (e.g. for staging an unreleased
  tool) gets a hard error on next App construction. Workaround:
  comment out the decorator, or use `visibility="hidden"` on the
  tool extras. Documented in proposal's BREAKING note.
- **Imports**: `get_meta` is already imported by `app.py` (via
  `tool.py` indirection); no new heavy imports.

## Out of scope

- A separate lint rule.
- Per-method opt-out flag.
- Inheritance walk (MRO) for decorated methods.
