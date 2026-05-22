## Context

`A2K-PKG-FRONT-DOOR` requires cross-package imports to target the package `__init__.py`. The implicit intent is that `__init__.py` is a *boundary* — a re-export surface — with implementation in submodules. Most packages honour this; `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, and `testing` do not. The fix is mechanical (relocate code, keep re-exports) and an enforcing rule so the discipline holds.

The original proposal scoped the split to three packages but the rule it adds flags any package `__init__.py` carrying implementation. An audit found seven offenders, not three. Scoping the split to three would leave the new rule with four standing violations — the rule could not report clean. The split is therefore expanded to all seven so the rule has zero violators and needs no allowlist.

## Goals / Non-Goals

**Goals:**

- All seven init-heavy packages (`ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, `testing`) have a re-export-only `__init__.py`.
- A lint rule prevents new implementation from accreting in any package `__init__.py`, and reports zero findings against `src/a2kit/` once the splits land.
- Zero consumer-facing import breakage.

**Non-Goals:**

- The `otel` package reshape (separate change); `otel` is already a clean lazy-`__getattr__` facade.
- Any behaviour change. This is pure relocation.

## Decisions

**1. `ldd` splits by concern.**
The 580-line `ldd/__init__.py` exposes logging primitives (`event`, `report`, `log`, `info`, `warning`, `error`, `debug`), the ambient call-context manager (`ldd_state_for_call`), the typed event registry (`EventRegistry`), a formatter (`format_ldd_line`, `TEXT_CAP`), and sink-author types (`LddEmission`, `LddSink`, `_AppLdd`). A concern-aligned split — e.g. `emission.py`, `ambient.py`, `events.py`, `sinks.py` — is the suggested shape; the apply phase finalises the exact submodule boundaries. `__init__.py` keeps only the re-exports.

**2. The other six packages split the same way.**
Each relocates its `__init__.py` implementation into named submodule(s); `__init__.py` becomes re-exports only. The apply-phase shapes:

- `context` → `stderr.py` (`StderrToolContext`, `MCPOnlyError`, the stub-result + helper types).
- `health` → `probe.py` (`HealthRegistry`, `HealthResult`, `run_checks`, `app_version`, the `_meta.health` constants).
- `codemode` → `transform.py` (`A2kitCodeMode`, `build_code_mode_transform`, `_require_monty`, `_is_destructive`) — joins the existing `marshal`/`runtime`/`stubs` submodules.
- `connections` → `install.py` (`install_connections`).
- `formatter` → `truncation.py` (`truncate` + caps) and `hint.py` (`format_response`, `_plan_for_hint`). Two submodules: `format_response` imports `render`, which imports `response`, so it cannot live in `response.py` without a cycle.
- `testing` → `seams.py` (`lazy`, `peek`, `resolve` — the DI test seams).

**3. The re-export-only rule is lint-enforced.**
A new static rule, `A2K-PKG-INIT-IMPL`, flags a package `__init__.py` that defines implementation — a top-level `class` or `def` / `async def`. The only exempt definitions are a lazy re-export `__getattr__` / `__dir__` pair (the `otel` lazy-facade pattern stays allowed, since it *is* re-export plumbing). Module-level constants, imports, and `__all__` are unaffected. Modelling it on the existing `A2K-PKG-FRONT-DOOR` rule and housing it in `rules/importing.py` keeps the `A2K-PKG-*` rule family consistent.

**4. Tests mirror the new structure.**
`module-layout-discipline` already requires `tests/` to mirror `src/`. New submodules get matching `tests/packages/<pkg>/test_<submodule>.py` files; existing tests that import via the package root are unaffected.

## Risks / Trade-offs

- **The lazy `__getattr__` facade must not be mis-flagged** → packages like `otel` use a lazy `__getattr__` / `__dir__` in `__init__.py` for cold-start deferral. That is re-export plumbing, not implementation. Mitigation: the rule exempts top-level functions named exactly `__getattr__` or `__dir__`.
- **Shared spec with `split-app-runtime`** → both changes touch `module-layout-discipline`. This change only ADDs a requirement; it does not modify the requirements `split-app-runtime` modifies, so they are independent. Archive order is not constrained, but the wave-ordering rule should be checked at archive time.
- **Choosing submodule boundaries** → an over-fine split trades one problem for many tiny files. Mitigation: split by genuine concern, not by line budget; the apply phase reviews the boundaries against the package's actual cohesion.
