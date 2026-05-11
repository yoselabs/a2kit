## 1. BDD-first scenarios

- [x] 1.1 Write scenarios in `tests/test_typed_emit.py` covering: dataclass instance → name+payload, pydantic BaseModel → name+payload, Enum field coerced via `.value`, kwargs form still works, instance + name override.
- [x] 1.2 Write scenarios in `tests/test_null_context.py` covering: all `fastmcp.Context` public methods exist and no-op, `ldd.event(null_ctx, X)` does not raise, can be passed where `ToolContext` is annotated.
- [x] 1.3 Write scenarios in `tests/test_param_shorthand.py` covering: `Param("text")` equivalent to `Param(description="text")`, mixed positional + kwargs valid, schema output identical.

## 2. Typed free-function emit

- [x] 2.1 In `src/a2kit/ldd.py`, extend `event(ctx, ...)` to detect an instance second positional. Branch: instance path serializes via `dataclasses.asdict` / `model_dump` / `vars` fallback; kwargs path unchanged.
- [x] 2.2 Add enum coercion: any field whose value is an `Enum` instance is replaced by `value.value` before emit.
- [x] 2.3 Optional `name=` keyword overrides `type(payload).__name__`.
- [x] 2.4 All scenarios in 1.1 pass.

## 3. Null context

- [x] 3.1 Create `src/a2kit/packages/testing/null_context.py` exporting `null_context() -> ToolContext`.
- [x] 3.2 Implementation: a class with every public method of `fastmcp.Context` defined as a no-op coroutine (logging methods, `report_progress`, `read_resource`, etc.). `request_id` and similar properties return fixed sentinel values.
- [x] 3.3 Re-export from `a2kit.testing`: `from a2kit.testing import null_context`.
- [x] 3.4 All scenarios in 1.2 pass.

## 4. Param positional shorthand

- [x] 4.1 Update `src/a2kit/params.py` `Param` factory to accept an optional positional first arg interpreted as `description`.
- [x] 4.2 Validation: if both positional and `description=` are given, raise `TypeError` with a clear message.
- [x] 4.3 All scenarios in 1.3 pass.

## 5. a2web migration

- [x] 5.1 Delete `_event_payload` and `_emit` from `src/a2web/fetcher.py`. Replace call sites with `await a2kit.ldd.event(ctx, event)` directly.
- [x] 5.2 Convert phase function signatures from `ctx: a2kit.ToolContext | None` to `ctx: a2kit.ToolContext`. Remove `if ctx is None` guards. Internal phase tests construct via `null_context()`.
- [x] 5.3 Tighten verbose `Param(description=...)` in `WebRouter.fetch` where appropriate by using the positional shorthand for short descriptions.

Note: a2web `pyproject.toml` pins `a2kit = { git = ..., tag = "v0.26.0" }`. The migration above compiles against the unreleased a2kit; a2web's test suite will go green once a2kit releases and a2web's pin bumps. This is the expected "release a2kit → update a2web" sequencing.

## 6. Docs

- [x] 6.1 README "Tool description contract" gains a note on long-vs-short Param descriptions and the positional shorthand.
- [x] 6.2 README "Testing" section documents `a2kit.testing.null_context()` as the no-op alternative to `a2kit.testing.client`.
- [x] 6.3 README "LDD events" section shows typed emit shape: `await a2kit.ldd.event(ctx, MyEvent(...))`.

## 7. Release

- [x] 7.1 Version bump appropriate to scope (likely patch alongside the next minor cut). Bumped to 0.26.1 (additive patch).
- [x] 7.2 CHANGELOG entry under "Additive ergonomics".
