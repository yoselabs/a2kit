# verb-decorators — dispatcher-timeout-decorator delta

## ADDED Requirements

### Requirement: Verb decorators accept `timeout=` kwarg

The verb decorators `@a2kit.read`, `@a2kit.write`, and `@a2kit.list_` SHALL accept a `timeout` keyword argument with the following forms:

- `timeout=None` (default) — no timeout; the tool body owns its own budget if any.
- `timeout=<number>` (float or int) — interpreted as seconds.
- `timeout=<string>` — bare number or with unit suffix `"ms"` (milliseconds), `"s"` (seconds), or `"m"` (minutes). Example: `"60s"`, `"2m"`, `"500ms"`.

The decorator SHALL parse the value at decoration time. Invalid string forms SHALL raise `TypeError` immediately, not at call time. The canonical normalized value (float seconds) SHALL be stored on `A2KitMetaExtras.timeout_seconds`.

When `timeout_seconds` is set, the dispatcher (both MCP and CLI transports) SHALL wrap the tool body in an `anyio.fail_after(seconds)` cancel scope. The scope SHALL sit innermost in the wrapper chain — inside the LDD-state scope and the dispatch-hook DI resolution — so neither DI cost nor LDD scope setup counts against the budget. On timeout, the wrapper SHALL raise Python's built-in `TimeoutError`.

The MCP transport's structured error envelope SHALL serialize `TimeoutError` as `{"class": "TimeoutError", "message": ...}` per the `mcp-structured-wire-error-envelope` contract. The CLI transport SHALL surface `TimeoutError` via the existing non-zero-exit + stderr-traceback path.

`A2KitMeta.annotations_as_dict()` SHALL surface `timeout_seconds` (when set) under the `a2kit` extras namespace, so MCP consumers reading `tool.meta` can plan retry policy.

#### Scenario: Float timeout is honored over MCP

- **GIVEN** `@a2kit.read(timeout=0.05)` on a tool whose body sleeps 0.5 seconds
- **WHEN** the tool is invoked via `fastmcp.Client(transport=build_mcp_server(app))`
- **THEN** the response is `isError=True`
- **AND** `json.loads(content[0].text)["class"] == "TimeoutError"`

#### Scenario: String form `"60s"` parses to 60.0 seconds

- **GIVEN** `@a2kit.read(timeout="60s")` on a tool
- **WHEN** the tool's `A2KitMeta` is inspected
- **THEN** `meta.extras.timeout_seconds == 60.0`

#### Scenario: String form `"500ms"` parses to 0.5 seconds

- **GIVEN** `@a2kit.read(timeout="500ms")` on a tool
- **WHEN** the tool's `A2KitMeta` is inspected
- **THEN** `meta.extras.timeout_seconds == 0.5`

#### Scenario: Invalid timeout string raises at decoration time

- **WHEN** `@a2kit.read(timeout="2 hours")` decorates a tool
- **THEN** the decoration raises `TypeError`

#### Scenario: Timeout meta surfaces in annotations dict

- **GIVEN** `@a2kit.read(timeout=30.0)` on a tool
- **WHEN** the test inspects `meta.annotations_as_dict()`
- **THEN** the returned dict contains `{"a2kit": {..., "timeout_seconds": 30.0, ...}}`

#### Scenario: No timeout means no fail_after wrapper installed

- **GIVEN** `@a2kit.read()` (no `timeout=`) on a tool whose body sleeps 0.5 seconds
- **WHEN** the tool is invoked
- **THEN** the call completes successfully — no `TimeoutError`
