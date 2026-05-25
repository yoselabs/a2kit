## Why

a2kit promises "write one typed function, get every transport." Errors break that promise today: tools ship raw stringified exceptions on the wire, agents cannot reason about retryability, the framework cannot auto-retry, the CLI has no exit-code discipline, and infrastructure errors leak `asyncpg.PostgresError`-shaped strings to the LLM. The MCP ecosystem has an open runway — Anthropic's 2026 roadmap does not mention typed errors, FastMCP explicitly rejected its typed-error decorator design (PR #2885), and no competing convention has converged. First mover wins. We replicate Effect's *guarantee* (declared error vocabulary, framework quarantines everything else) using Python-native tools (Annotated metadata, AST lint, isinstance dispatch) rather than its mechanism (HKTs, Result monad, fiber runtime) which Python cannot carry.

## What Changes

- **NEW package `a2effect`**: standalone, depends only on pydantic, adoptable by any Python framework. Provides `AppError` sealed base, `Raises(...)` Annotated marker, `raises_as` / `translate_to` helpers, `UnexpectedDefect` quarantine, `ErrorEnvelope` pydantic schema, `contract_tests` pytest plugin, `raises_registry` stub library.
- **a2kit takes hard dep on a2effect** and integrates: `EnricherStage` signature becomes `(exc) -> AppError | None` (was `-> str | None`); `ErrorEnvelopeStage` renders typed envelope to MCP / HTTP / CLI per single-mode rule (structuredContent only when info differs from `content[].text`); tool descriptors gain `raises` field populated from `Annotated[ReturnT, Raises(...)]` on the return annotation.
- **`@router.enricher` decorator** replaces today's class-level `enrichers` tuple. Two type-checked forms: wide (`exc: Exception`) and narrow (`exc: SomeSpecific`, framework introspects and dispatches by isinstance).
- **Output rendering rule (locked, no config)**: success cases emit `content[].text` only (zero duplication); error cases emit prose to text AND structured envelope to `structuredContent` (different views, both add value). HTTP status from `kind` (input=400, NotFound-subclass=404, auth=401, policy=403, infra=503, bug=500). CLI exit from `kind` (sysexits.h: input=2, auth=77, infra=75, bug=70).
- **CLI gains schema discovery**: `--help` auto-generated from annotations (parameters AND expected errors with kinds/exit-codes/hints); `--schema` emits full `ToolDescriptor` as JSON; `--json` flag mirrors MCP structuredContent envelope to stdout.
- **outputSchema auto-generation**: framework computes `oneOf[BareReturnSchema, ErrorEnvelopeSchema]` from the Annotated return type. Author writes no JSON schema. `ErrorEnvelopeSchema` defined once and `$ref`'d to keep tool descriptors compact.
- **Three lint rules** in a2effect registered via Python entry points: `A2K-RAISES-CLOSURE` (declared ⊇ body raises ∪ enricher coverage), `A2K-RAISES-UNCOVERED` (registry-driven uncovered detection), `A2K-RAISES-NOT-TYPED` (`Raises(...)` accepts AppError subclasses only).
- **Pydantic ValidationError default enricher** ships in a2effect: translates to `InputError` with `details.fields` carrying the pydantic error list. Universal for every consumer using pydantic.
- **BREAKING — enricher signature**: `Callable[[Exception], str | None]` → `Callable[[Exception], AppError | None]`. ~54 tools across a2web/a2atlassian/a2db/a2skill consumers migrate; no soft mode, no permissive default, strict from v1 day 1 per user direction.
- **BREAKING — wire format**: error responses now carry the prose+envelope shape on MCP and JSON envelope body on HTTP. Consumers parsing error strings via regex must switch.
- **BREAKING — return annotations**: tools that can fail SHALL declare `Annotated[ReturnT, Raises(...)]`. Tools without `Raises` are treated as raising nothing typed; any escape becomes `UnexpectedDefect` quarantine.

## Capabilities

### New Capabilities
- `typed-error-contract`: the `AppError` sealed base class, the five-kind taxonomy (`input | auth | policy | infra | bug`) with open extension via `base_kind` fallback, the `ErrorEnvelope` wire schema (versioned, pydantic), the `UnexpectedDefect` quarantine wrapper. Defines *what a typed error is* across the framework.
- `raises-annotation-contract`: the `Raises(*types)` frozen-dataclass marker placed inside `Annotated[...]` return annotations. Composition rule (multiple `Raises` markers flatten additively, ordering irrelevant). Reading semantics (framework via `get_type_hints(include_extras=True)`, lint via AST). Zero per-call runtime cost. Constraints (members must be `AppError` subclasses).
- `error-translation-pipeline`: the dispatch-time chain that turns raised exceptions into the envelope. Order: per-tool inline (`raises_as`, `translate_to`) → router enricher → app enricher → defect quarantine. `@router.enricher` decorator with wide and narrow signatures both type-checked. Replaces the existing `EnricherStage`'s string-return signature.
- `error-envelope-rendering`: the projection of the envelope onto MCP / HTTP / CLI wire shapes. Single-mode rule (structuredContent only on errors). HTTP status / CLI exit code maps from `kind` with per-class override. Prose format `"{Kind} error ({Type}): {message}\n\nHint: {hint}"`. Pure rendering, no policy.
- `raises-closure-lint`: the three build-time rules (`A2K-RAISES-CLOSURE`, `A2K-RAISES-UNCOVERED`, `A2K-RAISES-NOT-TYPED`). Stdlib `ast`-based, no libCST in v1. Plug-and-play via Python entry points under the `a2lint.rules` group.
- `raises-registry`: the registry of known-throwing functions (`httpx.AsyncClient.get → httpx.RequestError | httpx.HTTPStatusError`, etc.). Built-in stubs for httpx / asyncpg / redis / sqlalchemy / fastapi. Extension via `pyproject.toml [tool.a2effect.raises_registry]` and inline `# a2effect: may-raise X` annotations.
- `error-contract-tests`: the `contract_tests(app)` pytest plugin. Auto-generates per-tool tests covering (a) every `Raises` member round-trips to a valid envelope, (b) every registered enricher's output type appears in some tool's raises set (dead-enricher detection), (c) envelope renders identically across MCP / HTTP / CLI projections.

### Modified Capabilities
- `tool-descriptors`: descriptor gains a `raises: tuple[type[AppError], ...]` field populated by reading `Raises` markers from the return annotation at registration time.
- `tool-return-type-discipline`: return annotations MAY (and for tools that fail, MUST) be `Annotated[ReturnT, Raises(...)]`. The bare return type (`ReturnT`) drives serialization; `Raises` drives error contract.
- `mcp-tool-annotations`: tool result rendering follows the single-mode rule (success: `content[].text` only; error: prose in `content[].text` + envelope in `structuredContent`). Replaces today's stringified-exception behavior.
- `http-surface`: error responses emit `{"error": <envelope>}` JSON body with status mapped from `kind`. Replaces today's `HTTPException` defaults / plain text.
- `cli-response-encoding`: error responses render prose to stderr with kind label + hint; exit code mapped from `kind`; `--json` mirrors structuredContent envelope to stdout; `--help` and `--schema` auto-include `raises` metadata.

## Impact

- **New package**: `a2effect` ships as a separate publishable package in the a2kit repo (pyproject workspace or sibling directory; layout decided in design.md). Pure pydantic dep, no a2kit dep.
- **a2kit modules touched**: `packages/dispatch/stages.py` (EnricherStage signature), new `packages/dispatch/envelope.py` (ErrorEnvelopeStage), `packages/mcp/server.py` (renderer), `packages/http/build.py` (renderer + status map), CLI rendering path, `runtime.py` (ToolDescriptor.raises field), `routers.py` (enricher decorator + class-attribute removal).
- **Consumer migration**: ~54 tools across a2web (3), a2atlassian (39), a2db (5), a2skill (7). a2sdlc-engine unaffected (raw FastAPI). One PR per consumer, ~3 hours total work.
- **Existing capabilities retired or significantly reshaped**: enricher class-attribute on `Router` (replaced by decorator); today's string-return enricher path.
- **Wire-format break**: any external consumer parsing a2kit error strings via regex needs to switch to the envelope shape.
- **Spec drift gate impact**: several existing specs reference enricher / error semantics implicitly; touched specs listed under Modified Capabilities receive delta files.
- **Token cost on the wire**: ~150-300 extra bytes per error response (prose framing). Zero added cost on success path.
- **Build-time cost**: lint rules add seconds per CI run on a 50-tool codebase. Negligible.
- **Risk surface**: live probe confirmed `Annotated[X, Raises(...)]` composes with FastAPI `Body(...)` and Pydantic `Field(...)` cleanly. MCP `structuredContent` reality assessed (Cursor ignores, langchain ignores) — our single-mode rule sidesteps the issue. Open runway confirmed via ecosystem research.
