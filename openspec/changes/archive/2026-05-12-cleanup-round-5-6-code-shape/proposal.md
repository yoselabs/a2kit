## Why

The four post-shipping reviews of round-5/6 (`ambient-ldd-ctx-binding`, `testing-di-override`, `singleton-async-factories`, `param-docstring-pull`, `testing-client-wire-payload`) surfaced four small code-shape issues that can ride together in a single bundle: a three-way transport inconsistency on LDD binding, three SLF001 leaks in `TestClient.override`, mismatched function-name surfacing in `AmbientContextMissing` from LDD shorthands, and two silent `contextlib.suppress(Exception)` swallows in the docstring-pull path. All four are local clean-ups against contracts that round 5/6 already sealed, none introduce a new feature, and they share the same review window.

## What Changes

- **A. LDD ctx binding consistency.** Tighten CLI runtime and `TestClient.invoke` to only bind `ldd_state_for_call(ctx=...)` when the tool declared a ctx parameter — matching MCP's `_wrap_with_ldd_state` gate (`meta.context_param_name`). A tool that calls `await ldd.event(...)` without declaring `ctx: ToolContext` SHALL raise `AmbientContextMissing` on all three transports, not "works on two, raises on one". No synthesis of a `StderrToolContext` / capturing context when the tool didn't ask for one.
- **B. Container.override surface.** Add `Container._override(self, type_, instance)` — a test-seam method (single-underscore, same convention as `_snapshot`/`_restore`) that owns the three-attribute mutation (`_providers`, `_singletons`, `_async_factories`). `TestClient.override` becomes a one-liner delegate. Closes three `# noqa: SLF001` leaks in `src/a2kit/packages/testing/client.py`.
- **F. LDD shorthand error fidelity.** `a2kit.ldd.{info,warning,error,debug}` SHALL surface their own function name in the `AmbientContextMissing` message rather than the delegated-to `a2kit.ldd.log` name. Cheap traceback fix.
- **L. WARN_ONCE on silent docstring/get_type_hints failures.** Replace the two `contextlib.suppress(Exception)` swallows in `src/a2kit/_docstring.py` (parse path) and `src/a2kit/tool.py:_augment_annotations_from_docstring` (`get_type_hints` path) with a `_WARN_ONCE` dedupe-by-qualname log pattern, mirroring `src/a2kit/signature.py`'s `resolve_hints`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `mcp-context-passthrough`: tighten the "ambient context binding via dispatch contextvar" requirement — CLI and TestClient bind only when the tool declared `ctx`, never synthesize.
- `operational-contracts`: clarify the "LDD primitives require an active tool dispatch" requirement — the "active dispatch" predicate explicitly requires both an `ldd_state_for_call` scope *and* a ctx-param declaration on the tool, so the missing-ctx failure mode is uniform across transports.
- `di-container-package`: extend the "test-only snapshot/restore pair" requirement to also expose `_override(type_, instance)`, owning the three-attribute mutation (`_providers`, `_singletons`, `_async_factories`).
- `in-process-test-client`: amend the "TestClient.override swaps DI-resolved dependencies" requirement so the implementation delegates to `Container._override` rather than reaching into private attributes.
- `tool-description-contract`: amend the "Per-parameter descriptions resolved from the docstring" requirement so silent-degrade is replaced with one warn-once-per-qualname log on parse / `get_type_hints` failure (semantic outcome unchanged: still no exception, still falls back to no description).

## Impact

- Affected code:
  - `src/a2kit/packages/cli/runtime.py:48-50` — drop the synthesizing branch; bind ctx only when declared.
  - `src/a2kit/packages/testing/client.py:158-162, 218-228` — delegate to `Container._override`; gate ctx-binding on `meta.context_param_name`.
  - `src/a2kit/packages/di/container.py` — add `_override`.
  - `src/a2kit/ldd.py` (or wherever the shorthands live) — surface own function name in `_require_ambient_state`.
  - `src/a2kit/_docstring.py:44` and `src/a2kit/tool.py:152-193` — replace suppress with warn-once.
- Existing tests: the LDD-binding tighten may surface latent test fixtures that called LDD primitives from tools without `ctx`. Those tests need either a `ctx` param added or an explicit `null_context` if they were unit-style. Count expected: small (the in-repo examples already declare `ctx`).
- No public-API breakage of the documented surface. The tightening is "fail-loud where today we silently synthesize", which the round-5 proposal's spec already framed as the intended contract.
- Documentation: `OPERATIONAL_CONTRACTS.md` Q8 clause is touched to clarify the predicate.
