# health-probe — remove-health-tool-flag delta

## REMOVED Requirements

### Requirement: Built-in health tool

**Reason for removal**: the `App(health_tool=True)` constructor flag
was redundant after v0.33's auto-install via `@app.health_check`.
v0.33 kept it as a soft no-op for backward compatibility; v0.34
removes it entirely. The replacement install path
(`@app.health_check` triggers idempotent installation) covers every
v0.33 use case. Per project principle, dead surface SHALL crash
rather than gracefully degrade.

**Migration**:
```python
# before
app = a2kit.App("myapp", health_tool=True, lifespan=lifespan)

# after
app = a2kit.App("myapp", lifespan=lifespan)
# register at least one @app.health_check to install _meta.health
```

`App(...)` with `health_tool=...` raises `TypeError` at construction
with an embedded migration hint.

## ADDED Requirements

### Requirement: `_meta.health` SHALL install exclusively via `@app.health_check`

The synthetic `_meta.health` tool SHALL install as a side effect of
the first `@app.health_check` registration on an `App`. The install
SHALL be idempotent — subsequent `@app.health_check` calls SHALL
register additional checks without re-installing the synthetic
router. Apps with zero registered checks SHALL NOT have
`_meta.health` exposed; the synthetic router exists only when at
least one check exists.

The previous `App(health_tool=True)` install path SHALL NOT exist.
Constructing `App(...)` with that keyword SHALL raise `TypeError`
with a message naming `@app.health_check` as the replacement.

#### Scenario: First @app.health_check installs the synthetic tool

- **GIVEN** `app = a2kit.App("a")` (no checks yet)
- **WHEN** `@app.health_check` is applied to a function for the first time
- **THEN** `_meta.health` becomes invocable on the app's MCP/CLI surface
- **AND** `app.tools()` includes the synthetic tool descriptor

#### Scenario: Repeated @app.health_check is idempotent

- **GIVEN** an app with two `@app.health_check`-decorated functions registered
- **WHEN** the app is inspected
- **THEN** exactly one `_meta.health` tool descriptor exists
- **AND** both checks fire when `_meta.health` is invoked

#### Scenario: `health_tool=True` raises with migration hint

- **GIVEN** code `a2kit.App("a", health_tool=True)`
- **WHEN** the constructor evaluates
- **THEN** `TypeError` is raised
- **AND** the message contains `"health_check"`

#### Scenario: No checks → no synthetic tool

- **GIVEN** `app = a2kit.App("a")` with no `@app.health_check` registrations
- **WHEN** the app is inspected
- **THEN** `_meta.health` is NOT present in `app.tools()`
- **AND** invoking `_meta.health` over MCP returns the standard "unknown tool" error
