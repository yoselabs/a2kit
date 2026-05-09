## ADDED Requirements

### Requirement: `Router` subclasses accept `enricher` as a class kwarg

`a2kit.Router` SHALL implement `__init_subclass__` (PEP 487) such that
subclasses MAY pass `enricher=fn` in the class header:

```python
class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):
    ...
```

The captured enricher SHALL be applied to every tool defined on the
class, identical in behavior to the existing `enricher =
staticmethod(fn)` class-attribute form and the
`Router.__init__(enricher=fn)` constructor form.

When multiple forms are set, the precedence SHALL be (most-specific to
least): `__init__` arg > class kwarg > `enricher` attribute. This matches
the principle "explicit construction overrides class declaration."

#### Scenario: Class kwarg captured and applied
- **WHEN** `class TasksRouter(a2kit.Router, enricher=tracker_404_enricher):` is declared and `TasksRouter()` is instantiated
- **THEN** every tool on the router has its `A2KitMeta.enricher` set to `tracker_404_enricher`

#### Scenario: __init__ arg overrides class kwarg
- **WHEN** the class is declared with `enricher=A` and instantiated as `TasksRouter(enricher=B)`
- **THEN** every tool has `A2KitMeta.enricher` set to `B`

#### Scenario: Class kwarg overrides class attribute
- **WHEN** the class declares both `enricher = staticmethod(A)` (attribute) AND `enricher=B` (kwarg)
- **THEN** the kwarg `B` wins

#### Scenario: Plain function class attribute still wraps as staticmethod
- **WHEN** the class declares `enricher = my_enricher_fn` (no `staticmethod`)
- **THEN** `Router.__init_subclass__` SHALL detect the bare function attribute and wrap it as `staticmethod` automatically — the `enricher = staticmethod(...)` form continues to work, and the bare-function form now works too

#### Scenario: Other class kwargs are ignored gracefully
- **WHEN** a subclass passes an unknown kwarg, e.g. `class TasksRouter(a2kit.Router, frob=1):`
- **THEN** `__init_subclass__` raises `TypeError` with a clear list of accepted kwargs (per PEP 487 default behavior)
