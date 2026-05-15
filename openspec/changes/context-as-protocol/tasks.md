## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint`, `uv run ty check src/`, `uv run pytest -q --no-cov`.
- [ ] 0.2 `relax-ldd-ambient-requirement` shipped (recommended ordering — that change is the user-facing friction fix; this one is architectural cleanup that builds on top cleanly).
- [ ] 0.3 Reading-only check: `_is_fastmcp_context` (`packages/ldd/__init__.py:211-228`) still uses identity check against `fastmcp.Context`, unchanged by this change.

## 1. Define the Protocol

- [ ] 1.1 Create `src/a2kit/_context_protocol.py`:
  - Module docstring explaining the contract.
  - `@runtime_checkable class ToolContext(Protocol)` with the narrow surface (~11 methods + 2 attrs per design.md).
  - `__all__ = ["ToolContext"]`.
  - No imports from `fastmcp` (cold-start preservation).
- [ ] 1.2 Update `src/a2kit/__init__.py` `_LAZY_ATTRS`:
  - `"ToolContext": ("a2kit._context_protocol", "ToolContext")` (was: `("fastmcp", "Context")`).
- [ ] 1.3 Confirm `import a2kit; "fastmcp" not in sys.modules` still holds (cold-start sanity).

## 2. BDD tests for the Protocol identity + structural conformance

- [ ] 2.1 Create `tests/test_context_protocol.py`:
  - `test_a2kit_toolcontext_is_protocol` — `isinstance(a2kit.ToolContext, type)` is False; introspection confirms Protocol class.
  - `test_a2kit_toolcontext_not_fastmcp_context_identity` — `a2kit.ToolContext is not fastmcp.Context` (the identity changes).
  - `test_fastmcp_context_satisfies_protocol` — lazy-import fastmcp.Context; `isinstance(real_ctx, a2kit.ToolContext)` returns True under MCP.
  - `test_stderrtoolcontext_satisfies_protocol` — `isinstance(StderrToolContext(), a2kit.ToolContext)` returns True.
  - `test_cold_start_unchanged` — fresh subprocess running `import a2kit` does not load fastmcp (existing `tests/test_cold_start.py` pattern).
- [ ] 2.2 Update / retire any test that asserts `a2kit.ToolContext is fastmcp.Context`. Identify via `grep -rn "ToolContext is fastmcp\|ToolContext is Context" tests/`.

## 3. Update `find_context_param` to match the Protocol

- [ ] 3.1 Update `_is_tool_context` in `src/a2kit/signature.py`:
  - Primary check: `ann is a2kit.ToolContext` (the Protocol).
  - Secondary check (backward-compat): `ann is fastmcp.Context` — when fastmcp is loaded, still match consumers who annotated directly against the third-party class.
  - Add a comment explaining both paths.
- [ ] 3.2 Verify `_is_optional_tool_context` continues to handle `Optional[ToolContext]` correctly with both paths.

## 4. Update StderrToolContext docstring

- [ ] 4.1 `packages/cli/context.py:1-11` module docstring: rewrite from "CLI fastmcp.Context-shaped stub" → "CLI implementation of `a2kit.ToolContext` Protocol."
- [ ] 4.2 `packages/cli/context.py:74-87` class docstring: rewrite from "stub mimicking fastmcp.Context's public interface" → "Implementation of `a2kit.ToolContext` Protocol for the CLI transport."
- [ ] 4.3 DO NOT rename `StderrToolContext` → `CliToolContext` in this change (deferred per design.md).

## 5. Update `_is_fastmcp_context` documentation

- [ ] 5.1 The function itself doesn't change. Update its docstring (`packages/ldd/__init__.py:211-228`) to clarify it's about *wire-format dispatch* (real fastmcp uses `ctx.log(extra=...)`; other impls use `_emit`), not about contract identity.

## 6. Update `a2kit.ToolContext`-related docstrings / references

- [ ] 6.1 Sweep `src/a2kit/**/*.py` for "fastmcp.Context" references in docstrings; update to "`a2kit.ToolContext` (a Protocol; concrete impl depends on transport)" where it describes the contract rather than the wire-format detail.
- [ ] 6.2 Specific files (from grep): `signature.py:47`, `packages/cli/context.py:1`, `packages/mcp/server.py:69`, `packages/testing/client.py:6`, `packages/testing/null_context.py:32`.

## 7. Spec delta

- [ ] 7.1 `MODIFIED` requirement in `mcp-context-passthrough`: "`a2kit.ToolContext` is a re-export of `fastmcp.Context`" → "`a2kit.ToolContext` is a Protocol satisfied by `fastmcp.Context` and the CLI's `StderrToolContext`."
- [ ] 7.2 Update related scenarios in the same spec.
- [ ] 7.3 Confirm no other capability specs reference ToolContext identity directly (grep `openspec/specs/` for "fastmcp.Context").

## 8. Documentation

- [ ] 8.1 `CHANGELOG.md` Unreleased entry under "Changed" — describe the shift (identity changes; structural conformance preserved; no consumer code migration needed).
- [ ] 8.2 `OPERATIONAL_CONTRACTS.md` — update Q-Ctx (Context binding invariants) to reflect Protocol shape.
- [ ] 8.3 Update memory `project_a2kit_design_state.md` with the dispatch ambient mental model + new ToolContext Protocol shape.
- [ ] 8.4 Update `docs/feedback-responses/v0.38-a2web-round-10.md` — short addendum noting the architectural cleanup followed the friction fix.

## 9. Validate + archive

- [ ] 9.1 `openspec validate context-as-protocol --strict` passes.
- [ ] 9.2 Full gate green.
- [ ] 9.3 Archive: `openspec archive context-as-protocol -y`.

## 10. Sanity / non-tasks

- [ ] 10.1 No subclassing `fastmcp.Context` from `StderrToolContext` — hard no, cold-start breaker.
- [ ] 10.2 No removing `_is_fastmcp_context` — still needed for wire-format dispatch.
- [ ] 10.3 No feature Protocols (`Elicitable`, `Samplable`, etc.) — parked.
- [ ] 10.4 No capability system — parked.
- [ ] 10.5 No generic parameterization — plain non-generic Protocol; future ergonomic.
- [ ] 10.6 No renaming `StderrToolContext` — bikeshed; future cleanup.
