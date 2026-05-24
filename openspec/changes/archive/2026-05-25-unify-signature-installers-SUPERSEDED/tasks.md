# Tasks — unify-signature-installers

> Tier 1, depends on `add-surface-protocol` (the unified installer takes a `Surface` parameter) and `bridge-di-to-substrate-native` (the `substrate-dep` 4th class). Discharges ADR 0020 Option-B debt.

## 1. Remove `install_mcp_signature`

- [ ] 1.1 Delete the body of `install_mcp_signature` in `src/a2kit/packages/mcp/_wrappers.py` (lines 65-…). Replace the public symbol with a migration-hint raise: `def install_mcp_signature(*a, **kw): raise TypeError("install_mcp_signature removed in unify-signature-installers — use install_substrate_signature(fn, surface=mcp_surface, container=...) from a2kit.packages.dispatch.substrate")`.
- [ ] 1.2 Delete supporting helpers (`_ensure_ctx_in_rewritten_signature`, `_ctx_annotation_passthrough`, anything else internal to the removed installer that is not used by `McpErrorRenderStage`).
- [ ] 1.3 `packages/mcp/_wrappers.py` shrinks to hold only `McpErrorRenderStage` and MCP-only render concerns.

## 2. Migrate `mcp/server.py` to the unified installer

- [ ] 2.1 Replace every `install_mcp_signature(fn, ...)` call site in `mcp/server.py` with `install_substrate_signature(fn, surface=SURFACE_REGISTRY.get("mcp"), container=runtime.container)`.
- [ ] 2.2 Verify Context detection still works: the unified installer consumes `surface.reserved_types = frozenset({Context})`, so Context-typed params still take the reserved-passthrough path.
- [ ] 2.3 Verify schema generation: pydantic reads `__annotations__`, not `__signature__`. The unified installer must sync both (the existing `_install_rewritten_signature` invariant carries over).

## 3. Reconcile the dispatch path

- [ ] 3.1 Projection tools (`@app.read/list/write`) and substrate-native tools (`@app.mcp.tool` etc.) now both produce wrappers via `install_substrate_signature`. The "two MCP code paths" of ADR 0020 collapse to one.
- [ ] 3.2 The dispatch-pipeline fold continues to apply to projection tools (`McpErrorRenderStage` appended last). Substrate-native tools route through their Surface adapter, which may or may not fold the pipeline — Surface's `bind` decides. Document the rule in `surface-protocol` spec.

## 4. Test churn (byte-snapshot → behavior)

- [ ] 4.1 Audit `tests/packages/mcp/` for any test asserting exact `str(__signature__)` / wrapper source / parameter order bytes. List in PR description.
- [ ] 4.2 Rewrite each to behavioral assertion: "param X at position Y has annotation T and default Z", "Context detected", "wire schema has properties [...]". The behavior is what matters; bytes are not.
- [ ] 4.3 If any test cannot be rewritten behaviorally (truly asserts unmaintained-bytes), delete with justification.

## 5. `A2K-ONE-SIGNATURE-INSTALLER` lint rule

- [ ] 5.1 AST rule scanning `src/a2kit/packages/`: at most one symbol matching `install_*_signature` may be defined. Migration-hint raises don't count.
- [ ] 5.2 Rule test.

## 6. ADR 0020 amendment

- [ ] 6.1 Edit `docs/adr/0020-multi-surface-authoring.md`: add an "Amended" section noting that the Option-B clause ("two FastMCP code paths…") is superseded by `unify-signature-installers`. Cross-link to the archive entry once landed.
- [ ] 6.2 Regenerate `docs/adr/INDEX.md` via `scripts/adr_index.py`.

## 7. Spec deltas

- [ ] 7.1 Modify `openspec/specs/multi-surface-authoring/spec.md`: drop the "two MCP code paths" exception; assert single signature installer.
- [ ] 7.2 Modify `openspec/specs/mcp-context-passthrough/spec.md`: clarify Context detection survives via Surface.reserved_types.
- [ ] 7.3 Modify `openspec/specs/module-layout-discipline/spec.md`: add `A2K-ONE-SIGNATURE-INSTALLER`.

## 8. Final gates

- [ ] 8.1 `make lint` / `make test` green.
- [ ] 8.2 Cold-start budget verified (unchanged — substrate.py is L4 dispatch, already imported lazily).
- [ ] 8.3 MCP behavioral parity: the full `tests/packages/mcp/` suite passes; the public MCP contract (schema, tool/call, Context, error envelope, ldd) is preserved.
- [ ] 8.4 `packages/mcp/_wrappers.py` final LOC ≤ 70.
