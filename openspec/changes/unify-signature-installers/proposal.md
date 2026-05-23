## Why

ADR 0020 explicitly notes: "two FastMCP code paths (projection through the dispatch pipeline; substrate-native through `install_substrate_signature`) as the price of preserving the byte-for-byte MCP test guarantee while making `@app.mcp.tool` a real first-class surface." A docstring comment at `packages/mcp/_wrappers.py:99` flags the pending migration.

This is the canonical AGENTS §2 violation in the framework: two implementations of the same operation. `install_mcp_signature` (`packages/mcp/_wrappers.py:65`) and `install_substrate_signature` (`packages/dispatch/substrate.py:320`) both rewrite `__signature__` + `__annotations__`, split params into reserved/container-known/wire buckets, and re-derive the return annotation. The classifier was already shared in `add-multi-surface`; only the wrapper-emission stayed forked.

Under §1 (no backward compat) the byte-for-byte MCP test guarantee is **not a protected invariant**. We accept the test churn instead of preserving the shim. Under §2 (no redundancy) the duplication must end. Discharge the debt note; supersede the relevant clause of ADR 0020.

## What Changes

- **BREAKING**: `install_mcp_signature` removed from `packages/mcp/_wrappers.py`. Replaced by `install_substrate_signature(fn, surface=mcp_surface, ...)` — the same one-true installer the FastAPI path uses.
- **`install_substrate_signature` gains the `substrate-dep` 4th class** (added by `bridge-di-to-substrate-native`) and is parameterized by `Surface` (added by `add-surface-protocol`). No per-substrate branches inside the installer; surface-attributes drive everything.
- **Projection tools** (registered via `@app.read/list/write`) and **substrate-native registrations** (registered via `@app.mcp.tool` / `@app.api.get`) now go through the **same** wrapper-emission path. The "two MCP code paths" of ADR 0020 collapse to one.
- **BREAKING**: ADR 0020's "byte-for-byte MCP test guarantee" clause is superseded. The MCP wire output may differ in cosmetic ways (parameter ordering inside the synthesized `__signature__`, `__annotations__` dict ordering, generated wrapper `__name__`). Functional MCP behavior — schema, tool call dispatch, Context detection, ldd events — is preserved and asserted by the existing `test_mcp_*` suite.
- **BREAKING**: `packages/mcp/_wrappers.py` shrinks to hold only `McpErrorRenderStage` and any MCP-only render concerns. The signature install logic vanishes from this module.
- **BREAKING**: any test asserting the exact bytes of the synthesized MCP `__signature__` is updated to assert behavior (e.g. "param X is at position 2, has annotation T, default Y") rather than the exact `str(__signature__)`. No test that previously snapshotted the wrapper source survives unchanged.
- **Lint rule `A2K-ONE-SIGNATURE-INSTALLER`** (new): only one symbol named `install_*_signature` may exist anywhere under `packages/`. Catches accidental re-divergence.
- **ADR 0020 amendment**: a successor note marks the Option-B clause superseded; the trade-off is reversed (we chose §1+§2 compliance over wire-byte stability).

## Capabilities

### Modified Capabilities

- `multi-surface-authoring`: removes the "two MCP code paths" exception; substrate-native and projection registrations share one signature installer.
- `mcp-context-passthrough`: detection still works (it's annotation-based, not byte-position-based) but the surrounding wrapper bytes may shift.
- `module-layout-discipline`: adds `A2K-ONE-SIGNATURE-INSTALLER` lint rule.

## Impact

- `packages/mcp/_wrappers.py`: ~145 LOC removed (the `install_mcp_signature` body + helpers). File shrinks toward ~60 LOC (render stage only).
- `packages/mcp/server.py`: call sites to `install_mcp_signature` replaced with `install_substrate_signature(fn, surface=mcp_surface, container=runtime.container)`.
- `packages/dispatch/substrate.py`: `install_substrate_signature` becomes the single installer; per-substrate behavior driven by the `Surface` object passed in (added by `add-surface-protocol`).
- Test churn: byte-exact snapshot tests in `tests/packages/mcp/` rewrite to behavioral assertions. Estimated ~10 tests. The MCP test suite as a whole — schema correctness, Context detection, tool-call dispatch, error envelope, ldd ambient — continues to pass.
- Depends on `add-surface-protocol` (passing a `Surface` to the installer) and `bridge-di-to-substrate-native` (the `substrate-dep` 4th class the unified installer handles).
- ADR 0020 updated with supersedence note + cross-link to this change.
- Cold-start unaffected: the unified installer already lives at L4 (dispatch); no L5 imports change.
- After this lands the framework has **one** signature-wrapper-emission path. Future substrates plug in via the `Surface` Protocol, automatically using the same installer.
