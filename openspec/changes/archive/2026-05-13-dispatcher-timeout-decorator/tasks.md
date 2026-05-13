# Tasks — dispatcher-timeout-decorator

## 0. Prerequisites

- [x] 0.1 Baseline: `make lint` + `make test` green.

## 1. Parse + meta

- [x] 1.1 Add `_parse_timeout(value) -> float | None` helper in
      `src/a2kit/tool.py` per design D-PARSE.
- [x] 1.2 Add `timeout_seconds: float | None = None` field to
      `A2KitMetaExtras` in `src/a2kit/metadata.py`.
- [x] 1.3 Add `timeout=` kwarg to `read`, `write`, `list_`
      decorators in `src/a2kit/tool.py`. Each parses via
      `_parse_timeout` and stamps `extras.timeout_seconds`.

## 2. Wrapper

- [x] 2.1 Add `_wrap_with_timeout(fn, *, seconds)` to
      `src/a2kit/packages/mcp/server.py` per design D-WRAPPER.
- [x] 2.2 Install as innermost wrapper (between
      `_wrap_with_router_enrichers` and `fn`) when
      `meta.extras.timeout_seconds is not None`.
- [x] 2.3 CLI parity: install the same timeout wrap at
      `cli/runtime.py:_invoke_tool_in_process` after dispatch-hook
      resolves kwargs, before invoking `fn`.

## 3. Meta surface

- [x] 3.1 `A2KitMeta.annotations_as_dict()` includes
      `timeout_seconds` in the `a2kit` extras namespace when set.

## 4. Tests

- [x] 4.1 `tests/test_timeout_decorator.py`: parse forms (float,
      int, "60", "60s", "2m", "500ms"); invalid form raises
      TypeError at decoration time.
- [x] 4.2 MCP transport: tool with `timeout=0.05` and a body that
      sleeps 0.5s — assert wire envelope
      `{"class": "TimeoutError", "message": ...}` via
      `raise_on_error=False`.
- [x] 4.3 CLI transport: same tool via in-process CLI — assert
      `TimeoutError` is raised.
- [x] 4.4 No timeout (default `None`): tool runs to completion
      regardless of duration.
- [x] 4.5 Meta surface: `meta.annotations_as_dict()["a2kit"]
      ["timeout_seconds"]` reflects the set value.

## 5. OPERATIONAL_CONTRACTS

- [x] 5.1 Update Q2 (per-tool timeouts) to describe the new
      built-in mechanism. The `anyio.fail_after`-in-body pattern
      becomes a fallback for non-uniform timeouts inside a single
      tool body.

## 6. Spec delta

- [x] 6.1 `openspec/changes/dispatcher-timeout-decorator/specs/verb-decorators/spec.md`
      — add `## ADDED Requirements: Verb decorators accept timeout=`.

## 7. Verify

- [x] 7.1 `make lint` green.
- [x] 7.2 `make test` green; new tests pass.
