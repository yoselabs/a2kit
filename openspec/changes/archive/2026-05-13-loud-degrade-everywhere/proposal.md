## Why

The `cleanup-round-5-6-code-shape` change just replaced two `contextlib.suppress(Exception)` swallows in the docstring-pull path with a `_WARN_ONCE`-deduped WARN-log pattern, on the principle that framework-internal introspection failures must be observable to tool authors rather than silently degrade the user-visible surface. A grep of `src/a2kit/` finds five more sites in the same family that still silently swallow. They all have the same shape: decoration-time or middleware-path introspection that cannot raise (or it breaks the user's app boot / request handling), so the original author reached for `except Exception: pass`, and the user pays in lost output schema, missing list-view projection, missing OTel attributes.

(A sixth sibling in `routers.py:_collect_methods` was originally in scope, but the parallel `explicit-router-surface` change deletes `_collect_methods` outright in favour of an explicit `tools = (...)` class attribute. Any WARN_ONCE added here would become dead module-level state within days, so that site is dropped from this proposal.)

The same recipe lifted from round 5/6 — `_WARN_ONCE: set[str]` per module, dedupe by `fn.__qualname__` (or equivalent identity for the site), one `logging.warning(...)` on first failure, then continue with the documented fallback — applies cleanly to each site. This proposal extends the contract that round 5/6 sealed for the docstring-pull path to cover the other five framework-internal introspection failures, so the policy is uniform: **any decoration-time or middleware-path introspection failure SHALL emit one observable WARN per offender per process and proceed with the documented fallback**.

## What Changes

Apply the round-5/6 `_WARN_ONCE` recipe at the following sites, or convert genuinely-silent paths to explicit raise where the original `except` is not actually needed:

- **L1. `src/a2kit/packages/mcp/server.py:198`** — the return-annotation copy inside `_wrap_with_dispatch_hook`. Silent today; on failure FastMCP gets no output schema and the user never sees why. WARN_ONCE per `fn.__qualname__`, continue with the wrapper missing its return annotation.
- **L2. `src/a2kit/tool.py:97`** — `_resolve_return_annotation`'s `except Exception: return None`. Silent today; downstream `_check_return_scope` / `_derive_selectable_fields` cannot distinguish "no annotation" from "couldn't resolve". WARN_ONCE per `fn.__qualname__`, return `None`.
- **L3. `src/a2kit/tool.py:400`** — `_derive_selectable_fields`'s `except Exception: return ()` (outer) **and** the inner `contextlib.suppress(Exception)` around the dataclass branch. WARN_ONCE for the outer `get_type_hints` failure; verify-by-removal for the inner suppress (see tasks for the exact evidence rule).
- **L4. `src/a2kit/packages/mcp/listview.py:74` and `:96`** — two `except Exception: return result` blocks in `ListViewMiddleware.on_call_tool`. Silent today; on failure the user sees the unprojected payload with no signal that their `list_view=` directive was dropped. WARN_ONCE keyed by composite string (see Decision D3 in design.md), continue returning the unmodified result.
- **L5. `src/a2kit/packages/otel/middleware.py:34`** — `_meta_a2kit`'s `except Exception: return {}` around `server.get_tool(tool_name)`. Silent today; OTel spans lose `a2kit.verb` / `a2kit.router` / `a2kit.tags`. WARN_ONCE keyed on `tool_name`, continue with empty metadata.

In every case the semantic outcome is unchanged: decoration / middleware / router-init does not raise, and the user-visible surface degrades the same way it does today. The only change is that the first failure for each offender emits one WARN-level log line, so the bug is discoverable from a process tail rather than from staring at an empty schema field.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `tool-description-contract`: extend the "decoration SHALL NOT raise on docstring parse or hint-resolution failure" clause to cover two more decoration-time introspection sites: the return-annotation copy in `_wrap_with_dispatch_hook` and the `get_type_hints` calls in `_resolve_return_annotation` and `_derive_selectable_fields`. Same `_WARN_ONCE`-dedupe-by-qualname semantics as the round-5/6 docstring sites. (Sequenced AFTER `align-with-pydantic-and-stdlib` — see design.md for the rebase note.)
- `operational-contracts`: add a new requirement codifying the uniform "fail-observable, not silent" policy for framework-internal introspection failures: any decoration-time or middleware-path introspection (`get_type_hints`, return-annotation copy, list-view projection, MCP metadata lookup) SHALL emit one WARN per offender per process and proceed with the documented fallback, and SHALL NOT use bare `contextlib.suppress(Exception)` / `except Exception: pass`.
- `otel-adapter`: add scenarios covering the metadata-lookup failure mode — when `server.get_tool(tool_name)` raises, the span SHALL still be created with the `a2kit.tool_name` attribute and SHALL NOT raise out of the middleware; one WARN per `tool_name` is emitted.

## Impact

- Affected code:
  - `src/a2kit/packages/mcp/server.py:194-206` — add `_WARN_ONCE: set[str]` at module scope, replace `contextlib.suppress(Exception)` with try/except + WARN_ONCE.
  - `src/a2kit/tool.py:82-98` — add to existing module-level `_WARN_ONCE` (or new set), replace the bare `except Exception: return None`.
  - `src/a2kit/tool.py:392-418` — replace outer `except Exception` and inner `contextlib.suppress`; verify and remove the inner catch if `is_dataclass` / `fields` do not raise.
  - `src/a2kit/packages/mcp/listview.py:50-100` — add module-local `_WARN_ONCE: set[str]`, replace the two `except Exception: return result` blocks.
  - `src/a2kit/packages/otel/middleware.py:25-40` — add module-local `_WARN_ONCE: set[str]`, replace `_meta_a2kit`'s `except Exception` with WARN_ONCE.
- Tests:
  - One unit test per site asserting (a) the documented fallback still applies on failure, (b) exactly one WARN line is emitted per offender, (c) a second failure for the same offender in the same process does not emit a second line.
  - The listview / OTel sites need fixtures that force `server.get_tool` to raise; reuse the existing FastMCP middleware test harness.
- No public-API breakage: every site keeps its current behaviour on the success path and its current return value on the failure path. Only the silence is replaced with one observable WARN.
- Documentation: `OPERATIONAL_CONTRACTS.md` adds a short clause naming the policy. No change to user-facing API docs.
- Sibling proposals: this change is sequenced AFTER `align-with-pydantic-and-stdlib` (which lands first and rewrites `tool-description-contract` to drop the `a2kit.Param` wrapper in favour of `pydantic.Field` directly). The spec delta here is rebased against that post-state. The parallel `explicit-router-surface` change is independent and removes `routers.py:_collect_methods` outright, which is why the originally-planned L6 site was dropped from this proposal — see the Why section.
