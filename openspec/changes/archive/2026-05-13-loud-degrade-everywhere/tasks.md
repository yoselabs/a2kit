## 1. L1 — Return-annotation copy in `_wrap_with_dispatch_hook`

- [x] 1.1 In `src/a2kit/packages/mcp/server.py`, add a module-local `_WARN_ONCE: set[str] = set()` and `_log = logging.getLogger(__name__)` near the existing imports.
- [x] 1.2 Replace the `contextlib.suppress(Exception):` block at `src/a2kit/packages/mcp/server.py:198` with an explicit `try/except Exception as exc:` around the `get_type_hints(fn).get("return")` call. On failure, dedupe by `fn.__qualname__` and emit one `_log.warning("_wrap_with_dispatch_hook: failed to copy return annotation for %s: %s", name, exc)`. The wrapped fn keeps its current (annotation-less) state on failure.
- [x] 1.3 Drop the `import contextlib` line at `src/a2kit/packages/mcp/server.py:196` if it becomes unused after the replacement.

## 2. L2 — `_resolve_return_annotation` in `tool.py`

- [x] 2.1 At `src/a2kit/tool.py:97`, replace `except Exception: return None` with an explicit `try/except Exception as exc:` that dedupes by `fn.__qualname__` against a module-local `_WARN_ONCE_RESOLVE_RETURN: set[str]` and emits one `_log.warning("_resolve_return_annotation: get_type_hints failed for %s: %s", name, exc)` before returning `None`.
- [x] 2.2 Reuse the existing `tool.py` module-level `_log = logging.getLogger(__name__)` if present; otherwise add it once at module scope. Keep the dedupe set distinct from the docstring-pull set installed by round 5/6.

## 3. L3 — `_derive_selectable_fields` outer and inner catches

- [x] 3.1 At `src/a2kit/tool.py:400`, replace the outer `except Exception: return ()` with an explicit `try/except Exception as exc:` that dedupes by `fn.__qualname__` against a module-local `_WARN_ONCE_SELECTABLE: set[str]` and emits one `_log.warning("_derive_selectable_fields: get_type_hints failed for %s: %s", name, exc)` before returning `()`.
- [x] 3.2 Remove the inner `with contextlib.suppress(Exception):` at `src/a2kit/tool.py:413`. **Verification rule (evidence-pinned, not vibes):** run the full pytest suite (`pytest`) after the removal. If the suite is fully green, commit the removal as the suppress was dead code. If any test fails, do not restore the bare `contextlib.suppress(Exception)` — instead narrow the catch to the *specific* exception type(s) raised by the failing path, and add an inline comment naming the failing test (e.g. `# tests/test_tool.py::test_xyz exercises this — dataclasses.fields raises TypeError on subclassed dataclass without __fields__`) plus WARN_ONCE keyed on `getattr(inner, "__qualname__", repr(inner))`. A "feels like it might fail one day" justification is not accepted; every retained `except` SHALL cite an actual failing test. **Verified green: full suite (788 tests) passed after removing the inner suppress; the dataclass branch is now unguarded.**
- [x] 3.3 Drop the local `import contextlib` at `src/a2kit/tool.py:394` if it becomes unused.

## 4. L4 — `ListViewMiddleware` two silent returns

- [x] 4.1 In `src/a2kit/packages/mcp/listview.py`, add a module-local `_WARN_ONCE: set[str] = set()` and `_log = logging.getLogger(__name__)` near the imports.
- [x] 4.2 At `src/a2kit/packages/mcp/listview.py:74`, replace `except Exception: return result` with `except Exception as exc:` that dedupes by `tool_name` and emits one `_log.warning("ListViewMiddleware: server.get_tool failed for %s: %s", tool_name, exc)` before returning the unmodified `result`.
- [x] 4.3 At `src/a2kit/packages/mcp/listview.py:96`, replace `except Exception: return result` with `except Exception as exc:` that dedupes by `tool_name` (use the same `_WARN_ONCE` set; the keys are distinct from L4.2 only when both fail for the same tool — that case should emit two distinct WARN lines for the two distinct failure modes, so key by `f"{tool_name}::project"` for the projection site and `f"{tool_name}::get_tool"` for the lookup site). Emit `_log.warning("ListViewMiddleware: result reconstruction failed for %s: %s", tool_name, exc)`.

## 5. L5 — `_meta_a2kit` in OTel middleware

- [x] 5.1 In `src/a2kit/packages/otel/middleware.py`, add a module-local `_WARN_ONCE: set[str] = set()` and `_log = logging.getLogger(__name__)` near the imports.
- [x] 5.2 At `src/a2kit/packages/otel/middleware.py:34`, replace `except Exception: return {}` with `except Exception as exc:` that dedupes by `tool_name` and emits one `_log.warning("otel._meta_a2kit: server.get_tool failed for %s: %s", tool_name, exc)` before returning `{}`. Span construction in the caller proceeds with only `a2kit.tool_name` set; that is the documented fallback.

## 6. Tests

- [x] 6.1 Add unit test in `tests/test_decoration_warn_once.py` (or appropriate existing test module) covering L1: a tool with an unresolvable forward-ref return annotation goes through `_wrap_with_dispatch_hook`; assert exactly one WARN is emitted via `caplog`; assert a second decoration of a function with the same `__qualname__` emits no further line; assert the wrapped fn has no `return` annotation.
- [x] 6.2 Add a unit test covering L2: a tool whose annotations cause `get_type_hints` to raise; assert `_resolve_return_annotation` returns `None`; assert exactly one WARN via `caplog`.
- [x] 6.3 Add a unit test covering L3 outer: a tool with `list[ForwardRef('Unresolved')]` return annotation goes through `_derive_selectable_fields`; assert returns `()`; assert exactly one WARN. Re-run after removing the inner suppress to confirm the test suite stays green.
- [x] 6.4 Add a unit test covering L4: stub `fastmcp_ctx.fastmcp.get_tool` to raise; invoke the middleware against a tool with `list_view` metadata; assert the original `result` is returned; assert exactly one WARN keyed on `f"{tool_name}::get_tool"`. Add a second test that drives the result-reconstruction failure (e.g. by making `type(result)(...)` raise via a result subclass that rejects the constructor) and asserts the second WARN keyed on `f"{tool_name}::project"`.
- [x] 6.5 Add a unit test covering L5: same fixture as 6.4 but driving the OTel middleware; assert the span is still created with `a2kit.tool_name` set and without `a2kit.verb`/`a2kit.router`/`a2kit.tags`; assert exactly one WARN per `tool_name`.

## 7. Documentation

- [x] 7.1 Update `OPERATIONAL_CONTRACTS.md` to add a clause naming the policy: "Framework-internal introspection failures during decoration or middleware dispatch emit one WARN per offender per process and proceed with the documented fallback. Bare `contextlib.suppress(Exception)` / `except Exception: pass` is not used in introspection paths reachable from decoration or middleware."
- [x] 7.2 Cross-reference the round-5/6 docstring-pull sites and this change's five sites (L1–L5) in the contract doc, so the policy has a concrete index of where it applies.
- [x] 7.3 Add a CHANGELOG entry under the `## 0.30.x` heading (whichever patch this lands in — likely the v0.31.0 bundle) noting the WARN_ONCE policy and naming the five sites covered (L1 server.py return-annotation copy, L2 `_resolve_return_annotation`, L3 `_derive_selectable_fields`, L4 listview middleware, L5 OTel middleware metadata lookup).

## 8. Validation

- [x] 8.1 Run `openspec validate loud-degrade-everywhere --strict` and resolve any reported issues.
- [x] 8.2 Run the full pytest suite locally; fix any latent breakages surfaced by the WARN_ONCE rewires (none expected — failure-path behaviour is preserved).
- [x] 8.3 Grep `src/a2kit/` for any remaining `contextlib.suppress(Exception)` or bare `except Exception:` in decoration / middleware paths and either justify or convert. Report findings in the PR description.
