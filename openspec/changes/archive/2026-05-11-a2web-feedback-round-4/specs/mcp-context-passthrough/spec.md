## MODIFIED Requirements

### Requirement: LDD event and report primitives are protocol-neutral functions

The library SHALL expose `a2kit.ldd.event(ctx, payload, *, name=None, **kw)` and `a2kit.ldd.report(ctx, payload)` as free functions that accept any `fastmcp.Context`-shaped object. The `event` function SHALL accept either form:

1. **Kwargs form** (unchanged): `event(ctx, "name_string", key=value, ...)`. Second positional is the event name; remaining kwargs are the payload.
2. **Typed form** (new): `event(ctx, instance)`. Second positional is any class instance. Name defaults to `type(instance).__name__`; explicit `name=` overrides. Payload derived from the instance:
   - `dataclasses.asdict(instance)` if dataclass.
   - `instance.model_dump(mode="json")` if pydantic `BaseModel`.
   - `vars(instance)` fallback.
   - Any `Enum` value in the payload is replaced by `value.value`.

The library SHALL NOT add `event` or `report` methods to the `a2kit.ToolContext` re-export. Existing `--no-events` / `--no-reports` CLI flags and the `A2KIT_LDD` env var SHALL continue to gate these primitives.

#### Scenario: Kwargs form delivers an event

- **WHEN** a tool calls `await event(ctx, "api.fetched", count=30)` under `<app> serve`
- **THEN** the MCP client receives a `notifications/message` whose `level="info"`, `logger="event"`, `data={"name": "api.fetched", "count": 30, "elapsed_ms": ...}`

#### Scenario: Typed form delivers an event by class

- **GIVEN** `@dataclass class ApiFetched: count: int` and a tool calling `await event(ctx, ApiFetched(count=30))`
- **WHEN** the tool runs under `<app> serve`
- **THEN** the MCP client receives a `notifications/message` whose `data={"name": "ApiFetched", "count": 30, "elapsed_ms": ...}`

#### Scenario: Typed form with enum field

- **GIVEN** `class Verdict(Enum): OK = "ok"` and `@dataclass class TierEnded: verdict: Verdict`
- **WHEN** `await event(ctx, TierEnded(verdict=Verdict.OK))` is called
- **THEN** the delivered payload contains `"verdict": "ok"` (the enum value, not the enum instance)

#### Scenario: Explicit name override

- **WHEN** `await event(ctx, ApiFetched(count=30), name="api.custom_name")` is called
- **THEN** the delivered `data["name"]` is `"api.custom_name"`, not `"ApiFetched"`

#### Scenario: --no-events suppresses both forms

- **WHEN** the same tool runs with `--no-events`
- **THEN** neither form delivers an event, but neither call raises

### Requirement: a2kit.ToolContext is a re-export of fastmcp.Context

The library SHALL expose `a2kit.ToolContext` as a lazy re-export of `fastmcp.Context` via PEP 562 module-level `__getattr__` on the `a2kit` package. The library SHALL NOT define an independent `ToolContext` Protocol or subclass `fastmcp.Context`. `a2kit.ToolContext is fastmcp.Context` SHALL evaluate to `True` at runtime.

#### Scenario: Accessing ToolContext resolves to fastmcp.Context

- **WHEN** a process executes `import a2kit; t = a2kit.ToolContext`
- **THEN** `t is fastmcp.Context` evaluates to True
