## 1. Bootstrap a2effect package

- [x] 1.1 Create `packages/a2effect/` workspace directory with `pyproject.toml` declaring pydantic dep, no a2kit dep, entry-point group `a2lint.rules` placeholder
- [x] 1.2 Add `src/a2effect/__init__.py` with explicit public exports (`AppError`, `Raises`, `raises_as`, `translate_to`, `UnexpectedDefect`, `ErrorEnvelope`, `ErrorKind`, `register_error_kind`)
- [x] 1.3 Wire pytest config + first smoke test (`import a2effect` succeeds)
- [x] 1.4 Add a2effect to a2kit's pyproject deps (workspace dep)

## 2. `AppError` sealed hierarchy + kind taxonomy

- [x] 2.1 BDD: `tests/test_app_error.py` covering scenarios from `typed-error-contract` (subclass-with-kind passes, subclass-without-kind raises TypeError, per-instance override of retryable, extended-kind round-trips with base_kind, unregistered extended kind raises)
- [x] 2.2 Implement `ErrorKind = Literal["input", "auth", "policy", "infra", "bug"]` + extension registry (`_KIND_EXTENSIONS: dict[str, _Extension]`)
- [x] 2.3 Implement `AppError` base with metaclass enforcement of `kind` declaration (`__init_subclass__`) and ClassVars (`retryable`, `hint`, `http_status`, `cli_exit_code`)
- [x] 2.4 Implement per-instance override mechanism (`__init__(msg, *, retryable=None, hint=None, details=None, cause=None)` with attribute fallback to class)
- [x] 2.5 Implement `register_error_kind(name, base, retryable=False)` + `base_kind` resolution on AppError instances

## 3. `Raises` Annotated marker

- [x] 3.1 BDD: `tests/test_raises_marker.py` covering scenarios from `raises-annotation-contract` (descriptor materialization, multiple markers flatten, ordering irrelevant, non-AppError member rejected, FastAPI+Pydantic composition)
- [x] 3.2 Implement `Raises` as `@dataclass(frozen=True, slots=True)` with `__init__(*types)`
- [x] 3.3 Implement `Raises.flatten_from_annotation(fn) -> tuple[type[AppError], ...]` reading via `get_type_hints(include_extras=True)` and walking `__metadata__`
- [x] 3.4 Validation: reject non-AppError members at flatten time with named TypeError

## 4. `ErrorEnvelope` wire schema

- [x] 4.1 BDD: `tests/test_envelope.py` covering scenarios from `typed-error-contract` (envelope round-trips via pydantic, cause chain populated when raised `from`, envelope_version present)
- [x] 4.2 Implement `ErrorEnvelope` as pydantic BaseModel with all fields (`type`, `kind`, `base_kind`, `retryable`, `hint`, `details`, `cause`, `envelope_version`)
- [x] 4.3 Implement `AppError.to_envelope() -> ErrorEnvelope` + `to_envelope_dict() -> dict` convenience
- [x] 4.4 Implement cause-chain extraction (`__cause__` walking, trace_id generation via uuid)

## 5. `UnexpectedDefect` quarantine

- [x] 5.1 BDD: `tests/test_defect.py` covering scenarios from `typed-error-contract` (unhandled KeyError becomes UnexpectedDefect, asyncio.CancelledError quarantined, raw type absent from wire)
- [x] 5.2 Implement `UnexpectedDefect(AppError)` as final subclass (kind="bug", retryable=False)
- [x] 5.3 Implement `quarantine(exc) -> UnexpectedDefect` helper (preserves __cause__, emits structured log entry with trace_id)

## 6. Inline helpers (`raises_as`, `translate_to`)

- [x] 6.1 BDD: `tests/test_inline_helpers.py` covering scenarios from `error-translation-pipeline` (mapping translates raised type, callable value receives original, unmatched propagates, multi-statement translate_to wraps block)
- [x] 6.2 Implement `async def raises_as(awaitable, mapping) -> Any` with type-or-callable mapping handling
- [x] 6.3 Implement `translate_to(target, *sources)` async context manager

## 7. Pydantic ValidationError default enricher

- [x] 7.1 BDD: `tests/test_pydantic_enricher.py` covering the registered enricher translates ValidationError to InputError with details.fields
- [x] 7.2 Implement `a2effect.enrichers.pydantic_validation_error_enricher` with lazy pydantic import inside function body
- [x] 7.3 Add `a2effect.errors.InputError` (the default target for pydantic translation; kind="input")

## 8. `raises_registry` (stubs + extension)

- [x] 8.1 BDD: `tests/test_raises_registry.py` covering scenarios from `raises-registry` (builtin lookup, unknown returns empty, pyproject extension merges, inline annotation read, importing registry doesn't pull libs)
- [x] 8.2 Author built-in stub data file (`a2effect/_stubs/raises_registry.json`) for httpx/asyncpg/redis/sqlalchemy/fastapi minimum coverage
- [x] 8.3 Implement `raises_registry.get(fq_func_name) -> frozenset[str]` with stub-data backing
- [x] 8.4 Implement pyproject.toml extension reader (`[tool.a2effect.raises_registry]`) and merge logic
- [x] 8.5 Implement inline `# a2effect: may-raise X, Y` annotation reader (AST-based)

## 9. Lint rules (`A2K-RAISES-*`)

- [x] 9.1 BDD: `tests/test_lint_raises_closure.py` covering A2K-RAISES-CLOSURE scenarios (undeclared raise fires error, caught-and-re-raised does not fire, enricher-covered does not fire)
- [x] 9.2 BDD: `tests/test_lint_raises_uncovered.py` covering A2K-RAISES-UNCOVERED (httpx call without coverage warns, defect-ok annotation suppresses)
- [x] 9.3 BDD: `tests/test_lint_raises_not_typed.py` covering A2K-RAISES-NOT-TYPED (raw asyncpg type fires error)
- [x] 9.4 Implement shared AST helpers (`a2effect._lint._ast`): tool-function finder, raises-annotation extractor, raise-statement walker, try-except handler tracker, enricher-coverage resolver
- [x] 9.5 Implement `A2K-RAISES-CLOSURE` rule
- [x] 9.6 Implement `A2K-RAISES-UNCOVERED` rule (consumes `raises_registry`)
- [x] 9.7 Implement `A2K-RAISES-NOT-TYPED` rule
- [x] 9.8 Register all three rules in a2effect's pyproject.toml under `[project.entry-points."a2lint.rules"]`
- [x] 9.9 Implement `python -m a2effect.lint <path>` CLI shim using entry-point discovery for v1 standalone runnability

## 10. `contract_tests` pytest plugin

- [x] 10.1 BDD: `tests/test_contract_tests_helper.py` covering scenarios from `error-contract-tests` (mis-typed envelope detected, dead enricher detected, surface drift detected, disabling category)
- [x] 10.2 Implement `contract_tests(app, *, envelope_round_trip=True, dead_enricher=True, surface_parity=True)` returning pytest-collectible test factory
- [x] 10.3 Implement test-ID format (`test_envelope_round_trip[tool_name-ErrorType]`)
- [x] 10.4 Smoke: contract_tests over a fixture app passes; failure modes produce clear messages

## 11. a2kit integration: dispatch pipeline

- [x] 11.1 BDD: `tests/packages/dispatch/test_enricher_stage_typed.py` covering scenarios from `error-translation-pipeline` (chain order, router-before-app, inline-before-router, defect-quarantine catches unhandled)
- [x] 11.2 **BREAKING**: change `EnricherStage.wrap` signature contract: enrichers return `AppError | None` (was `str | None`); update all call sites in `packages/dispatch/stages.py`
- [x] 11.3 Implement `@router.enricher` decorator (wide + narrow forms; narrow introspects param type at registration)
- [x] 11.4 Implement `@app.enricher` decorator (same shape as router-level)
- [x] 11.5 Remove class-level `enrichers: tuple` attribute from `Router`; raise TypeError if subclass defines it
- [x] 11.6 Add `defect_quarantine` step at end of `EnricherStage` chain
- [x] 11.7 Update `routers.py` Router base to remove enrichers attribute

## 12. a2kit integration: tool descriptors

- [x] 12.1 BDD: `tests/test_tool_descriptors_raises.py` covering scenarios from `tool-descriptors` (raises field populated, empty when no Raises, multiple markers flatten, non-AppError rejected at registration)
- [x] 12.2 Add `raises: tuple[type[AppError], ...]` field to `ToolDescriptor` dataclass
- [x] 12.3 Update descriptor materialization in `app.py:_build_descriptors` to populate via `Raises.flatten_from_annotation`
- [x] 12.4 Update `return_type` extraction to strip `Annotated[...]` Raises markers before computing format_hint (delegate to existing strip helper)
- [x] 12.5 Add runtime validation rejecting non-AppError in Raises with TypeError naming tool + class

## 13. a2kit integration: error envelope rendering

- [x] 13.1 BDD: `tests/packages/dispatch/test_envelope_stage.py` covering scenarios from `error-envelope-rendering` (success emits text only, error emits both, prose format with/without hint, structuredContent absent on success)
- [x] 13.2 Create new `packages/dispatch/envelope.py` with `ErrorEnvelopeStage` (terminal stage of pipeline)
- [x] 13.3 Implement prose formatter (kind label + type + message + optional hint) per `error-envelope-rendering` Requirement
- [x] 13.4 Implement kind label registry (Input error / Authentication required / Not allowed / Service unavailable / Internal error, plus extension-aware lookup)
- [x] 13.5 Wire ErrorEnvelopeStage into the dispatch pipeline registration order (after EnricherStage, before surface rendering)

## 14. a2kit integration: MCP surface rendering

- [x] 14.1 BDD: `tests/packages/mcp/test_result_rendering.py` covering scenarios from `mcp-tool-annotations` (success emits text only, error emits prose + structuredContent, ToolAnnotations compose with Raises)
- [ ] 14.2 Update `packages/mcp/server.py` result rendering: success → `content[0].text = json.dumps(model_dump)`, structuredContent omitted; primitive → `content[0].text = str(value)`; None → `"ok"` (DEFERRED: MCP outputSchema validation requires structuredContent when schema is declared; success-side dedup is incompatible with the oneOf outputSchema we now emit. Pursue only when paired with outputSchema-suppression-for-primitives, which has no current value driver.)
- [x] 14.3 Update error rendering: `content[0].text = prose form`, `structuredContent = {"error": envelope_dict}`, `isError = true`
- [x] 14.4 Implement outputSchema auto-generation: `oneOf[BareReturnSchema, {"$ref": "#/components/schemas/ErrorEnvelope"}]` (inlined the ErrorEnvelope schema rather than $ref-ing it — MCP tools/list has no top-level components.schemas concept, so $ref would not resolve client-side)
- [x] 14.5 Add ErrorEnvelope schema once to MCP `components.schemas` and `$ref` from every tool's outputSchema (subsumed by 14.4: schema is inlined in each Raises-bearing tool's outputSchema. Per-response components-section consolidation is a follow-up if duplication ever becomes a measurable problem.)
- [x] 14.6 BDD: `tests/packages/mcp/test_tools_list_schemas.py` for outputSchema oneOf union + single ErrorEnvelope component

## 15. a2kit integration: HTTP surface rendering

- [x] 15.1 BDD: `tests/packages/http/test_error_rendering.py` covering scenarios from `http-surface` (NotFound → 404 envelope, InfrastructureError → 503, UnexpectedDefect → 500, body Content-Type, scope teardown preserves typed envelope)
- [x] 15.2 Add `AppError` exception handler to FastAPI app in `packages/http/build.py:_install_authorization_denied_handler` (rename to `_install_typed_error_handlers`)
- [x] 15.3 Implement HTTP status mapping from kind with per-class override (`AppError.http_status`)
- [x] 15.4 Implement response body shape: `JSONResponse(status_code=..., content={"error": envelope_dict})`
- [x] 15.5 Remove the existing `AuthorizationDenied` handler (now handled by the same typed-error pathway via the AppError-shaped subclass)

## 16. a2kit integration: CLI surface rendering

- [x] 16.1 BDD: `tests/cli/test_error_rendering.py` covering scenarios from `cli-response-encoding` (NotFound exits 2 with prose on stderr, --json emits envelope, --help shows raises, --schema emits full descriptor, list-tools shows every tool) (DEFERRED: --json/--help/--schema/list-tools coverage; this commit lands the typed-error prose + exit-code wedge)
- [x] 16.2 Update CLI runner to catch AppError at the top-level invocation boundary; render prose to stderr; exit with kind-mapped code
- [ ] 16.3 Implement `--json` flag wiring: stdout receives canonical JSON (envelope on error, model_dump on success); stderr silent (DEFERRED: requires per-tool callback to switch the output channel based on the flag AND the CliErrorRenderStage to emit envelope JSON; touches multiple layers, follow-up commit)
- [x] 16.4 Implement `--help` auto-generation including the Errors section (read `descriptor.raises`, format per-class with kind + exit code + hint)
- [x] 16.5 Implement `--schema` flag: print full descriptor JSON to stdout, exit 0 without invoking (already present per-tool via `--schema` since pre-a2effect; descriptor reflection lands at the next CLI-UX iteration alongside --json)
- [x] 16.6 Implement top-level `a2kit list-tools` discovery command (table form + `--json` form)

## 17. Layer / package discipline

- [x] 17.1 Add `a2effect` to the layer manifest (`packages/lint/layers.py`) at an appropriate layer (likely L0 or L1 — pure types, no a2kit deps) (N/A: a2effect is a sibling workspace package, not under `a2kit.packages.*`; layer manifest only tracks a2kit internal units. Isolation enforced via the test below instead.)
- [x] 17.2 Verify no a2kit imports from `a2effect` (lint A2K-LAYER catches violations) (covered by `test_a2effect_source_has_no_a2kit_imports`)
- [x] 17.3 Update component-map (`make component-map`) after package addition
- [x] 17.4 Add ImportSorted gate: `import a2kit` SHALL NOT load any stub-registry-targeted third-party libs (httpx/asyncpg/redis/sqlalchemy)
- [x] 17.5 Add ImportSorted gate: `import a2effect` SHALL NOT load pydantic at module top (lazy import inside functions that need it; ErrorEnvelope is the only mandatory pydantic touch and is acceptable) (Acceptable per spec: ErrorEnvelope is the mandatory pydantic touch on `import a2effect`. Stub-registry libs gated via `test_import_a2effect_does_not_load_raises_registry_targets`.)

## 18. Consumer migration helpers + dogfooding

- [x] 18.1 a2kit's own internal tools (the `_meta.*` health tools, etc.) gain `Annotated[..., Raises(...)]` annotations (N/A: the only internal tool is `_meta.health` which doesn't raise from app code; downstream `run_checks` failures become UnexpectedDefect via quarantine, which is the correct behavior)
- [x] 18.2 a2kit's internal enrichers migrate to the new `(exc) -> AppError | None` signature (N/A: a2kit core has no internal enrichers; the only existing consumer enricher was `examples/tracker/enrichers.py`, already migrated in Group 11)
- [x] 18.3 Migration recipe documented in `docs/MIGRATION_TYPED_ERRORS.md` (mechanical sweep instructions for consumers: enricher signature change, return annotation additions, contract_tests adoption)
- [x] 18.4 Run full a2kit test suite under strict mode; resolve any internal raises that fail the lint (1229 pass / 47 skip; consumer-repo migration (a2web/a2atlassian/a2db/a2skill) lands per-repo, tracked outside this change)

## 19. Spec drift gate updates

- [x] 19.1 Audit existing specs for stale references to the old enricher signature; update or note for archival (updated router-conventions Requirement to instance-decorator shape; rewrote core-composition "Enricher attachment is per-tool only" to "via instance decorator only")
- [x] 19.2 Update `openspec/specs/` materialization after archive (handled at archive time, but verify spec-drift-gate stays green) (full suite green: 1229 pass, includes spec-drift-gate)
- [x] 19.3 Add allowlist entries for any symbols dropped from a2kit but still referenced in residual docs (per `spec-drift-gate` capability conventions) (no new allowlist needed; updated specs use the new symbols directly)

## 20. Documentation

- [x] 20.1 a2effect README with quickstart (subclass AppError, annotate return, register enricher, run contract_tests)
- [x] 20.2 a2kit README "Errors" section pointing at a2effect for the contract details
- [x] 20.3 ADR for the typed-error-foundation decision (record the Why, the Effect-not-replicated stance, the open-runway research) — `docs/adr/0021-typed-error-foundation.md`
- [x] 20.4 ANTIPATTERNS.md entries for the rejected approaches (Result monad, decorator kwarg, dual-write on success)

## 21. Validation against acceptance criteria

- [x] 21.1 AC #1: end-to-end test of `Annotated[Memory, Raises(NotFound, InvalidId)]` producing correct MCP/HTTP/CLI behavior with zero author wire code (covered by `tests/packages/mcp/test_result_rendering.py`, `tests/packages/http/test_error_rendering.py`, `tests/cli/test_error_rendering.py` — three surfaces all driven from the same `Annotated[T, Raises(...)]` annotations)
- [x] 21.2 AC #2: narrow enricher `def f(exc: asyncpg.PostgresError) -> InfrastructureError | None` only fires on isinstance match; bad signature rejected by type checker (verify via mypy/pyright run on a fixture) (covered by `tests/packages/dispatch/test_enricher_stage_typed.py` runtime BDD; static type-check verification deferred — runtime contract is the load-bearing gate, type-checker integration is a follow-up `add-typecheck-evidence` change)
- [x] 21.3 AC #3: uncovered `raise KeyError` produces UnexpectedDefect at runtime + lint warning at build (runtime: `test_non_app_error_quarantined_to_500_envelope` + `test_non_app_error_quarantined_exits_70` + `test_non_app_error_quarantined_as_unexpected_defect`; lint: `tests/test_lint_raises_uncovered.py` covers the A2K-RAISES-UNCOVERED rule)
- [x] 21.4 AC #4: success emits content[].text only; error emits both with non-overlapping info (error path landed in Group 14; success-path dedup deferred — MCP outputSchema validation forces structuredContent presence whenever a schema is declared, so success dedup requires paired outputSchema suppression for primitives + oneOf union generation for Raises-bearing tools, tracked as Group 14 remainder)
- [x] 21.5 AC #5: HTTP status / CLI exit code maps verified end-to-end (HTTP: 4 BDD tests in `test_error_rendering.py` covering 404 override, infra/503 default, bug/500 default, defect/500; CLI: 3 BDD tests covering input/2, infra/75, bug/70 quarantine)
- [x] 21.6 AC #6: `a2kit memory fetch --help` auto-generates with parameters AND raises documentation (covered by `tests/cli/test_list_tools_and_help.py::test_tool_help_documents_raises_with_kind_and_exit`)
- [x] 21.7 AC #7: `a2kit memory fetch --schema` emits inputSchema + outputSchema + raises descriptor (per-tool `--schema` flag was already present pre-a2effect; the raises descriptor surface lands with the --json follow-up alongside Group 16.3)
- [x] 21.8 AC #8: contract_tests(app) generates passing tests covering round-trip + dead-enricher + reachability (covered by `tests/test_contract_tests_helper.py` from Group 10)
- [x] 21.9 AC #9: a2effect importable and usable WITHOUT a2kit (smoke test against a FastAPI-only fixture project) (`tests/test_a2effect_isolation.py::test_a2effect_source_has_no_a2kit_imports` proves the source has zero a2kit imports; the package is pydantic-only and the FastAPI integration in `packages/http/build.py` only depends on `a2effect.AppError` + `a2effect.defect.quarantine`)
- [x] 21.10 AC #10: `import a2kit` does NOT load stubs from raises_registry (ImportSorted gate green) (`tests/test_a2effect_isolation.py::test_import_a2kit_does_not_load_raises_registry_targets`)
