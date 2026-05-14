# Remove `App(health_tool=True)` — dead surface, no graceful migration

## Why

v0.33 changed the health-probe story so that the **first
`@app.health_check` call auto-installs** the `_meta.health` synthetic
router idempotently. That made `App(health_tool=True)` redundant in
the common case. v0.33 kept the flag accepted "as no-op when checks
are also registered" — soft-deprecation.

Per project principle, dead surface should **crash, not gracefully
degrade**. Soft-deprecation hides the migration from consumers' read
paths. Round-9 consumer feedback already noted: "The CLAUDE.md
template still has `App("a2web", health_tool=True, lifespan=lifespan)`,
and other consumer repos likely do too." Those consumers will
continue copying the dead pattern as long as it silently no-ops.

The fix: hard-remove the flag. Loud failure with embedded migration
hint, matching the `@a2kit.tool` / `name=` / `@app.singleton` removal
pattern from v0.33 prettification.

## What Changes

- **REMOVE** the `health_tool: bool = False` parameter from
  `App.__init__` in `src/a2kit/app.py`. Replace its reception with
  a `**kwargs`-based guard that raises `TypeError` with the
  migration hint:
  ```
  App(health_tool=...) was removed. Register a check with
  @app.health_check to auto-install the _meta.health tool, or
  omit the flag if you don't need health checks.
  ```
- **REMOVE** the corresponding wiring in `App.__init__` body
  (`self._health = HealthRegistry(enabled=health_tool)`,
  `if health_tool: self._install_health_tool()`). The
  `_install_health_tool` method becomes called only from
  `health_check(...)`.
- **MODIFY** `HealthRegistry`'s `enabled` semantics — `enabled=True`
  is now triggered exclusively by the first `@app.health_check`
  call. If no consumer code references `HealthRegistry(enabled=...)`
  externally, the `enabled` kwarg can be removed entirely (audit
  required).
- **MODIFY** the `health-probe` capability spec:
  - REMOVED Requirement: "Built-in health tool" — the
    `App(health_tool=True)` path
  - MODIFIED: replacement requirement spelling out the
    `@app.health_check`-only install path
- **DELETE** v0.33's "Changed — `@app.health_check` auto-enables the
  health tool" CHANGELOG block's transitional language; replace with
  a v0.34 "BREAKING — `health_tool=` removed" entry.

## Consumer migration

Single-line, mechanical:

```python
# before
app = a2kit.App("myapp", health_tool=True, lifespan=lifespan)

# after
app = a2kit.App("myapp", lifespan=lifespan)
# add @app.health_check on at least one check to install the tool
```

The CLAUDE.md template the consumer mentioned needs the same one-line
strip.

## Impact

- Breaking change. Consumers carrying the flag (a2web CLAUDE.md
  template + likely others) get a loud `TypeError` on first import
  after bumping.
- One spec requirement updated, one CHANGELOG block reshaped.
- The hard-crash + hint pattern matches v0.33's footgun-guard
  ergonomics, so consumers who already migrated through v0.33 see
  a familiar shape.

## Why not DeprecationWarning?

Project principle: no soft deprecations. `DeprecationWarning` is
optional reading; `TypeError` blocks startup. The release notes plus
the in-error migration hint are sufficient signal. Consumers who
miss both have the same problem either way; the loud version is
fixable in seconds, the soft version festers across releases.

## Coordination with other v0.34 changes

This change pairs naturally with:

- `canonical-api-drift-gate` — would catch any stale
  `health_tool=True` in README/CLAUDE.md before release.
- `loud-error-on-renamed-test-client-method` — same loud-failure
  ethos applied to a different surface.

All three reinforce the same principle: dead surface should crash;
documentation should be the only place rename/removal stories live.
