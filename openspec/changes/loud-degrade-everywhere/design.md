## Context

`cleanup-round-5-6-code-shape` shipped the `_WARN_ONCE` recipe for the docstring-pull path (sites L in that change's tasks file). The principle it sealed: framework-internal introspection failures during tool decoration must remain non-raising (decoration runs at app boot — raising breaks the user's process startup) but must also remain observable (silent degrade is how authors lose half-a-day debugging an empty MCP schema field).

A grep of `src/a2kit/` for `contextlib.suppress(Exception)` and bare `except Exception:` finds five direct siblings of the original two sites. They all have the same shape:

- The code is on a path that cannot raise without breaking something external (FastMCP tool registration, MCP middleware dispatch, OTel span construction).
- The introspection it performs is best-effort: `get_type_hints`, `server.get_tool`, dataclass field walking.
- The failure mode is "degrade silently" — return `None`, return `()`, return the unmodified payload, skip the attribute.

### Ordering relative to sibling changes

This change is **sequenced AFTER `align-with-pydantic-and-stdlib`**, which lands first and rewrites `tool-description-contract` to remove the `a2kit.Param` wrapper in favour of `pydantic.Field` directly. The spec delta in this change is rebased against that post-#1 state of `tool-description-contract`: the decoration-time-introspection clause we extend here applies to the same decoration pipeline that #1 just clarified to use `pydantic.Field` for parameter description resolution. The two changes touch disjoint sentences of the same requirement (Param removal vs. `_WARN_ONCE` extension), so there is no overlapping text — but the prose mentions "Param" only in the historical sense of the round-5/6 sites, never as a current surface.

This change is also **disjoint from `explicit-router-surface`**, which deletes `routers.py:_collect_methods` outright. The originally-planned L6 WARN_ONCE on that site was dropped from scope — adding module-level state to a function that gets deleted within days is dead work.

The right answer for every one of them is the same as the round-5/6 answer: keep the non-raise, replace the silence with one WARN-level log per offender per process, deduped by a module-local `set[str]`.

## Goals / Non-Goals

**Goals:**

- Apply the round-5/6 `_WARN_ONCE` recipe uniformly across the five sibling sites.
- Codify the policy in `operational-contracts` so future framework-internal introspection points start with the recipe rather than reaching for `except Exception: pass`.
- Extend `tool-description-contract`'s existing "decoration SHALL NOT raise" clause to cover the two more decoration-time introspection sites in `tool.py` (return-annotation resolution, selectable-fields derivation) and the return-annotation copy in `server.py`.
- Add OTel-adapter scenarios for the metadata-lookup failure mode so the span construction contract is explicit about what happens when `server.get_tool` raises.

**Non-Goals:**

- Adding a configurable "warn-or-raise" mode. Failure mode is fixed: WARN + continue with the documented fallback. Users who want strict mode can set the log handler to raise on WARN themselves; not a framework concern.
- Adding structured-event emission (LDD) for these failures. The whole point is these sites run outside ambient LDD context (decoration time / middleware-init time / pre-dispatch); LDD is not available. Stderr WARN is the lowest-friction observable.
- Changing the semantic outcome at any site. Every site keeps its current fallback (no return-annotation on the wrapped fn, `None` from `_resolve_return_annotation`, `()` from `_derive_selectable_fields`, unprojected listview payload, empty OTel attributes, skipped router method).
- Touching the docstring-pull sites that round 5/6 already converted. Those are already on the recipe.
- Migrating tests for the sibling proposals (`align-with-pydantic-and-stdlib`, `explicit-router-surface`).

## Decisions

### D1. Stderr WARN, not structured event

LDD's structured event channel would be the ideal sink — but every one of these sites runs without an active `ldd_state_for_call` ambient context, by design. They run either at decoration time (well before any tool dispatch begins) or inside middleware on the pre-tool-body half of the call where the LDD scope has not yet been pushed. The fallback `stderr` WARN via `logging.getLogger(__name__)` is the lowest-friction observable: it costs zero infrastructure, it shows up in every operator's existing tail, and it composes with whatever log filtering the host app already does.

A future change can lift these to LDD if the LDD ambient ctx is pushed earlier in the request lifecycle, but that is a separate move and out of scope here.

### D2. WARN_ONCE, not WARN-every-call

Logging every failure makes the channel useless: a single tool with an unresolved forward reference would emit one WARN per request (for listview) or per server startup (for decoration), drowning real signal. Dedupe-per-offender-per-process keeps each problem to one line, which is enough to find and fix the bug.

The dedupe key varies per site:

- **Decoration-time sites** (server.py wrap, tool.py resolve / derive): `fn.__qualname__`. Same key the round-5/6 sites use; consistent across the codebase.
- **Middleware sites** (listview, otel): `tool_name` (the FastMCP tool name string). The site failure is about a specific registered tool, not a specific Python function, and `tool_name` is the user-visible identifier in operator logs.

### D3. WARN_ONCE per module, not per process

Each module gets its own `_WARN_ONCE: set[...]` at module scope. No shared registry. This matches the existing pattern in `src/a2kit/signature.py:resolve_hints`, `src/a2kit/_docstring.py`, and `src/a2kit/tool.py:_augment_annotations_from_docstring` (all installed by round 5/6).

The downside — same `fn.__qualname__` could emit one WARN per site that touches it — is a feature, not a bug: each site is a different code path failing for a different reason, and the operator wants to see all three reasons, not just the first. The line prefix (`logger name = module path`) tells them which site complained.

### D4. Verify-and-remove the inner `contextlib.suppress` in `_derive_selectable_fields`

`_derive_selectable_fields` has two layers:

```python
try:
    hints = get_type_hints(fn)
except Exception:
    return ()
...
with contextlib.suppress(Exception):
    import dataclasses
    if dataclasses.is_dataclass(inner):
        return tuple(f.name for f in dataclasses.fields(inner))
```

The outer is a real failure mode (`get_type_hints` can raise on forward refs, unresolvable names) and gets the WARN_ONCE treatment. The inner is suspicious: `import dataclasses` won't raise (it's stdlib), `dataclasses.is_dataclass(inner)` does not raise on any input (it's a `hasattr`-style check), and `dataclasses.fields(...)` raises `TypeError` only when called on a non-dataclass — but the `is_dataclass` guard already prevents that path.

The right move is to verify by removing the inner suppress and running the test suite. If the suite stays green, leave it removed (less code, no silent path). If a real failure mode appears, narrow the catch to the actual exception type (likely `TypeError`) and add WARN_ONCE there too. The proposal commits to the removal-after-verification, with the narrowing fallback as the documented path if verification surfaces a hit.

### D5. One `_WARN_ONCE` set per module, composite keys for multi-site modules

When a single module has multiple distinct failure sites that share the same natural identity (e.g. `listview.py` has both an `server.get_tool` lookup site at line 74 and a result-reconstruction site at line 96, both naturally keyed by `tool_name`), the module SHALL still hold exactly one `_WARN_ONCE: set[str]` at module scope, and each site SHALL prefix its key with a site tag — `f"{tool_name}::get_tool"` for the lookup site and `f"{tool_name}::project"` for the reconstruction site.

Rationale:

- Keeps module-level mutable state to one set per module, matching the existing pattern in `signature.py` / `tool.py` and avoiding a proliferation of `_WARN_ONCE_FOO`, `_WARN_ONCE_BAR` globals.
- Lets each site tune its dedupe granularity independently without coordinating across sites: if a future maintainer wants to drop the site tag at one of the two listview sites (e.g. because two failures for the same `tool_name` are now considered "one bug"), the change is local to that `except` block.
- Tagging makes the dedupe key self-describing in logs and tests: when a unit test asserts "exactly one WARN per offender per process", it can match against the full composite key and unambiguously identify which site emitted the line.

The naming convention is `f"{natural_key}::{site_tag}"` where `site_tag` is a short stable lowercase string identifying the failure point within the module. The same convention SHALL be adopted by any future multi-site module added under this policy.

### D6. The operational-contracts policy as a new requirement

Round-5/6 covered LDD primitives' "active dispatch" rule (Q8 area). This proposal adds a sibling requirement at the same level of generality:

> Framework-internal introspection failures during decoration or middleware dispatch SHALL emit one WARN per offender per process and proceed with the documented fallback. Bare `contextlib.suppress(Exception)` / `except Exception: pass` SHALL NOT be used in introspection paths reachable from decoration or middleware.

The clause is policy-level, not site-level, so it applies to future sites without needing another spec amendment.

## Risks / Trade-offs

- **WARN noise in CI.** Test fixtures that intentionally exercise the failure paths (e.g. a tool with an unresolved forward reference, used to test the fallback) will emit a WARN line. Mitigation: tests use `caplog` to assert exactly one WARN was emitted; the test capture mode prevents stderr leakage in normal pytest runs.
- **`__qualname__` collisions across modules.** Two `_derive_selectable_fields` calls from two test fixtures that happen to define functions with the same `__qualname__` would dedupe against each other. Acceptable: the WARN_ONCE is per-module, the dedupe is per-`__qualname__`-within-module, and the failure mode is "missed a WARN line for a second offender" — degraded observability, not lost behaviour.
- **Removing the inner `contextlib.suppress` in L3 surfaces a real exception.** Mitigation: D4's verify-then-narrow fallback. If the test suite stays green, the suppress was dead code. If not, narrow to the exact type and add WARN_ONCE there.
- **Listview / OTel WARN keyed on `tool_name` could be noisy in load-test scenarios.** Mitigation: the dedupe is per-`tool_name`-per-process; load testing a single broken tool emits exactly one line, not one per request.

## Migration Plan

Single PR, no flag. The change is purely observability — the failure-path behaviour is identical to today's silent degrade.

Roll back by reverting the PR; no persisted artifacts, no wire format changes.

## Open Questions

None. Five sites, one recipe, applied mechanically.
