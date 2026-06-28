## 1. Adopt the architecture + invariant (this change)

- [x] 1.1 Record the decision in ADR 0032 (`docs/adr/0032-refound-a2kit-as-fastmcp-helpers.md`, proposed); regenerate `INDEX.md`; `make adr-check` green.
- [x] 1.2 Add a README Direction banner pointing to ADR 0032 (no drift — the framework API is marked the final framework-era surface).
- [x] 1.3 Author this change: proposal + design + the `fastmcp-helper-architecture` spec delta (extractability invariant). `openspec validate --strict` green.
- [ ] 1.4 Human-confirm ADR 0032 (Constitution Phase A). On acceptance, mark ADR 0028 + 0019 superseded (edit their Status lines) and 0031 deprioritized.

## 2. Pilot — port one server to plain FastMCP (follow-on change, migration-first)

- [ ] 2.1 Pick one representative consumer MCP server. Branch it.
- [ ] 2.2 Rewrite it on plain FastMCP: remove `a2kit.App`; where an a2kit feature is missed, write the helper *inline in the server repo* (typed-TSV serializer, error envelope). Server's own tests are the contract (BDD-first).
- [ ] 2.3 Record which helpers were actually reached for and their natural FastMCP-native signatures.

## 3. Extract proven helpers + delete the framework (follow-on change)

- [ ] 3.1 Write the `fastmcp-helper-architecture` lint rule (`AK###`): each `a2kit.*` helper module imports only `fastmcp` / `pydantic` / stdlib — fail on any intra-a2kit core import. (Test-first.)
- [ ] 3.2 Extract `a2kit.tsv` (typed-TSV result type + serializer) as a standalone, `fastmcp`-only module. Snapshot + wire tests.
- [ ] 3.3 Extract `a2kit.errors` (unified error envelope) standalone.
- [ ] 3.4 Extract optional `a2kit.rest` and `a2kit.cli` projections only if step 2.3 showed a consumer needs them (else drop — see design Open question).
- [ ] 3.5 Keep `a2kit.lint` as the standalone static analyzer (now also hosts 3.1).
- [ ] 3.6 Delete redundant surfaces FastMCP now owns: code mode, tool-failure wrapping, transport plumbing, CLI-as-framework (§1 delete-don't-deprecate; CHANGELOG migration rows).
- [ ] 3.7 Retire `a2kit.App` and the composition spine. Rewrite `tests/surface/` snapshots; reconcile the `App`-bearing capability specs (REMOVED/MODIFIED deltas in this change). Supersedes ADR 0028 + 0019.
- [ ] 3.8 Update AGENTS.md "Architecture strategy" (drop "App is the one public type") and ANTIPATTERNS/OPERATIONAL_CONTRACTS to the helper model.

## 4. Migrate remaining consumers (follow-on change)

- [ ] 4.1 Port the remaining MCP servers to FastMCP + the extracted helpers, one at a time.

## 5. Upstream contribution pipeline (ongoing)

- [ ] 5.1 For each surviving helper, write down the FastMCP gap it fills → the upstream-issue backlog (one helper → one scoped proposal).
- [ ] 5.2 Build FastMCP-contributor standing first via small, ritual-following PRs (bug fix / docs / test, issue-first + assigned) before proposing any helper as an enhancement.

## 6. Documentation (after helper code lands)

- [ ] 6.1 Full README rewrite to the "a2kit = FastMCP-extras helper sandbox" positioning (replaces the framework docs; the Direction banner becomes the lede).
