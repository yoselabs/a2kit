## Context

a2kit today renders tool errors as bare strings: an exception escapes a tool body, `EnricherStage` calls `(exc) -> str | None` enrichers that may rewrite the message, then the MCP/HTTP/CLI surfaces serialize whatever exception comes out. Agents see `KeyError: 'foo'` with no way to decide retry vs adapt vs give up. The framework cannot auto-retry because retryability isn't expressed. HTTP returns whatever `HTTPException` shape the underlying library picked. CLI prints stack traces.

This design replaces that path end-to-end with a typed-error contract that flows from author annotation to wire envelope. The contract is packaged as a standalone library (`a2effect`) so the typed-error layer is independently adoptable, then integrated into a2kit's dispatch pipeline.

Several constraints shape the design:

- Python type-checker landscape (pyright, mypy, TY) gives no checked-exception enforcement and no plugin-based path on pyright. Verification must be either runtime (pay a per-call cost) or build-time (lint). We choose lint.
- Effect-TS guarantees a typed error channel via type-system composition; Python lacks HKTs to model that. We replicate the *guarantee* (declared vocabulary, defect quarantine) without the *mechanism* (Result monad).
- MCP spec only defines `isError: true` + content; structuredContent is under-specified and ignored by Cursor and langchain-mcp-adapters today. We must ship a wire format that works on the lowest-common-denominator client (content[].text) while opportunistically using structuredContent where it adds value.
- FastMCP explicitly rejected its typed-error decorator design (PR #2885 stripped). Anthropic's 2026 MCP roadmap does not mention typed errors. Open runway for 6-12 months.
- 54 tools across a2web/a2atlassian/a2db/a2skill consumers need migration. Per user direction: no soft mode, no permissive default, strict from day 1. Migration is consumer's choice driven by the new thing being worth it.

## Goals / Non-Goals

**Goals:**

- A tool author writes `Annotated[ReturnT, Raises(NotFound, InvalidId)]` and the framework derives MCP wire shape, HTTP status, CLI exit code, envelope rendering, schema discovery (--help, --schema), and lint coverage — with zero further author work.
- The typed-error contract is replicable in any Python framework (FastAPI-only, Litestar, raw): `a2effect` ships independently of a2kit.
- Type checkers verify enricher signatures and the legality of `Raises(...)` members for free (Layer 0 of defense). Runtime verification rejects bad registrations (Layer 1). Lint verifies body raises closure at build time (Layer 2).
- The wire format honors information distinctness: emit `structuredContent` only when it carries fields `content[].text` does not. Zero duplication on the 95% success path; opportunistic mirror on errors.
- Lint rules plug into any conforming runner via Python entry points (no hard a2lint dep on a2effect, no hard a2effect dep on a2lint).

**Non-Goals:**

- Result/Option monads or any non-raise-based error API. Python idiom is raise/except; fighting it costs more than it pays. The `returns` library has 3.5k stars after years; HKT-style sugar is a non-starter for adoption.
- Mypy/pyright plugins. Pyright's no-plugin policy is structural; mypy plugins lock half the user base out. Lint runs in every editor without configuration.
- Generic combinators (`traverse`, `flatMap` over arbitrary containers). Python cannot type them without HKTs and we don't need them for this scope.
- Backward compatibility with the existing string-return enricher signature. Strict break, mechanical migration.
- Typed retries (`@retry_on(InfrastructureError)`) and typed timeouts. Deferred — they ride on this contract once it lands.
- CLI `--retry` and `--explain` flags. Deferred to v1.x; not blocking foundation.
- libCST-based autofix. v1 uses stdlib `ast` for read-only lint; autofix added once rules stabilize.
- OpenAPI → Router codegen. Separate wedge; depends on this contract being stable first.

## Decisions

### Decision 1 — Annotation as canonical contract surface, not decorator kwarg

The error vocabulary lives in the return annotation: `Annotated[ReturnT, Raises(NotFound, InvalidId)]`. Not in a decorator kwarg (`@memory.read(raises=(...))`), not in a docstring `Raises:` section.

**Why annotation:**

- One pattern for everything — tools (which have a decorator) and service methods (which don't). Same syntax everywhere.
- Annotations defer evaluation under PEP 563/649; framework reads via `get_type_hints(include_extras=True)` once at registration. Zero per-call runtime cost.
- Type-checker sees the return correctly (`Memory`, not `Memory + raises stuff`); `Raises(...)` is invisible to pyright/mypy/TY but visible to our lint.
- `Annotated` is stdlib (PEP 593); FastAPI already established the pattern (`Annotated[X, Body(...)]`). We extend, not invent.
- No precedence ambiguity. Single source of truth.
- Decorator stays purely about REGISTRATION (`expose`, `authorize`, `visibility`); annotation carries the CONTRACT (return + raises). Two orthogonal concerns, two mechanisms.

**Alternatives rejected:**

- Decorator kwarg `@memory.read(raises=(...))`: duplicates the annotation surface; tools and services use different forms; precedence rules needed. Discoverability claim is weak — annotation is more discoverable at the function signature.
- Custom return wrapper `Raises[Memory, NotFound | InvalidId]`: needs special-case handling in pyright (no plugin path) or unwrap magic. Effectively a worse `Annotated`.
- Docstring `Raises:`: needs pydoclint dep; lives outside the type system; not standard across Sphinx/Google/Numpy styles.

### Decision 2 — `AppError` ClassVar metadata with per-instance override

```python
class AppError(Exception):
    kind: ClassVar[ErrorKind]
    retryable: ClassVar[bool] = False
    hint: ClassVar[str | None] = None
    http_status: ClassVar[int | None] = None    # derived from kind if None
    cli_exit_code: ClassVar[int | None] = None  # derived from kind if None
```

Subclasses declare class-level defaults; instances may override per-raise (e.g., `InfrastructureError("conn refused", retryable=True)` vs `InfrastructureError("syntax error", retryable=False)`).

**Why this shape:**

- ClassVar gives the type-checker enough information without instance access (used by lint and by `@router.enricher`'s narrow form).
- Per-instance override allows the rare case where the same exception class can be retryable in one context and not another.
- HTTP status / CLI exit code derive from `kind` by default; per-class override hook (`http_status: ClassVar[int] = 404`) for the `NotFound`-shaped exceptions where the convention diverges from the kind default.

**Alternatives rejected:**

- Pure-instance fields: loses the ClassVar inspection enrichers and lint depend on.
- Single-flat field for kind+retryable+hint (e.g., a `Meta` dataclass): more types, no win.
- Dataclass-based `AppError`: clashes with Exception's `__init__` chain; messy MRO.

### Decision 3 — Closed taxonomy of 5 kinds with open extension via `base_kind`

Core kinds: `input | auth | policy | infra | bug`. Frozen for v1. Consumers extending the taxonomy register a derived kind via `app.register_error_kind(name="rate_limit", base="infra", retryable=True)`. Wire envelope carries both `kind` (specific) and `base_kind` (fallback).

**Why bounded extension:**

- Five kinds is the right richness — HTTP managed with 4xx/5xx (effectively two). Adding many risks no agent generalization.
- Bounded set lets agents (Claude, GPT) train against a stable contract. Extensions stay agent-readable via `base_kind` fallback.
- Frozen core means we never break the contract by adding a kind in v2; consumers' agents can rely on the five.

**Alternatives rejected:**

- Fully open (string enum, any value): agents can't generalize; every server invents its own.
- Fully closed: blocks legitimate consumer needs (rate-limit, quota-exceeded).
- Hierarchy of kinds: complexity exceeds value at this size.

### Decision 4 — Enricher returns `AppError | None`; two type-checked forms

The `@router.enricher` decorator accepts callables with `Exception -> AppError | None`. Two forms:

- **Wide**: `def f(exc: Exception) -> AppError | None` — called for every exception, author matches inside.
- **Narrow**: `def f(exc: asyncpg.PostgresError) -> InfrastructureError | None` — framework introspects the first parameter type and only calls when `isinstance(exc, that_type)`.

Type-checker (pyright/mypy/TY) enforces the return type at decoration — bad enrichers (returning `str`, returning `RuntimeError`) fail type-check without any plugin.

**Why both forms:**

- Wide form is familiar (one function handles many cases via match).
- Narrow form gets you Effect-style typed dispatch via native isinstance, with sharper typing on both sides.
- Framework reads parameter annotation at registration — zero per-call cost, decided once.

**Alternatives rejected:**

- Wide-only: forces match-blocks for cases where one type maps to one translation. Verbose.
- Narrow-only: forces split across multiple enricher functions even when not natural.
- Effect-TS `catchTag` literal-tag dispatch: requires tag fields on AppError; less Pythonic than isinstance.

### Decision 5 — Single wire-format rule: structuredContent only when info differs

Success cases: `content[].text` only. structuredContent omitted entirely. Zero duplication.

Error cases: `content[].text` carries human prose (LLM-readable); `structuredContent` carries the machine envelope (kind, retryable, details — fields not in the prose).

**Why this rule:**

- No configuration knob, no per-app mode. One predictable shape.
- LLM context never billed twice — text and structuredContent always carry different information when both present.
- Success path zero-cost (the 95% case). Error path opportunistic mirror.
- Tests/proxies/our future smart client read structuredContent on errors for typed access; parse content[].text JSON on success (trivial).
- Works for clients that ignore structuredContent today (Cursor, langchain-mcp-adapters) AND clients that read it tomorrow.

**Alternatives rejected:**

- Always dual-write (Mode C in exploration): 2x token cost in any client that surfaces both. Designs around an assumption we don't control.
- Text-only (Mode A): loses zero-cost structured access for tests/proxies; ships envelope JSON inside text fence (cluttered, harder to parse robustly).
- Configurable mode: complexity exceeds value; one right answer.
- structuredContent-only: model can't reason (content[] is the LLM channel); breaks every client today.

### Decision 6 — outputSchema auto-generated as `oneOf[Bare, ErrorEnvelope]`

Framework computes `outputSchema = {oneOf: [BareReturnSchema, ErrorEnvelopeSchema]}` at tool registration. `ErrorEnvelopeSchema` defined once in a2effect, referenced via JSON-Schema `$ref` so per-tool descriptors stay compact.

**Why auto-generate:**

- Authors write annotations; framework writes JSON Schema. Zero JSON-Schema labor.
- Lint rule `A2K-OUTPUT-SCHEMA-COMPAT` catches manual overrides that contradict the annotation (escape hatch on the decorator) so the auto-derived shape stays load-bearing.
- `$ref` keeps token cost bounded — one `ErrorEnvelope` definition in `components`, every tool refers.

**Alternatives rejected:**

- Don't declare outputSchema: loses success-case validation; ContextForge gateways still accept but lose client-side benefit.
- Author-written union: tedious, error-prone, defeats the typed-contract promise.
- Wrap success and error in a discriminated `result/error` object: changes serialization shape for every successful response (wire-breaking, agent-relearning).

### Decision 7 — Three-package architecture with entry-point lint discovery

```
   a2effect    standalone, pydantic-only, defines types + helpers + rules
   a2kit       depends on a2effect; integrates into dispatch + surfaces
   a2lint      independent runner (DEFERRED to follow-up change);
               existing a2kit rules port over via entry point later
```

a2effect's lint rules ship inside a2effect under `[project.entry-points."a2lint.rules"]`. Any conforming runner (the future a2lint, or a Ruff plugin once their API matures) discovers and runs them. **a2effect has no dep on a2lint.**

**Why this split:**

- a2effect adoptable independently (FastAPI-only project gets typed errors).
- a2kit doesn't conflate "typed errors" with "MCP dispatch fabric" — separable concerns.
- Entry-point discovery is zero-coupling and Python-standard (pytest plugins, Sphinx extensions use the same pattern).
- a2lint extraction is its own concern; foundation lands without waiting for it. Existing a2kit lint rules continue running through their current mechanism in v1; migration is a follow-up.

**Alternatives rejected:**

- All-in-a2kit: typed-error layer locked to the framework; no FastAPI-only adoption path.
- a2effect imports a2lint: circular concern; a2lint becomes mandatory dep.
- Custom rule-discovery format: reinvents entry points for no gain.

### Decision 8 — Defect quarantine for cancellation and any escape

`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`, and any exception not handled by the enricher chain get wrapped in `UnexpectedDefect(original)` at the dispatch boundary. Always `kind="bug"`, `retryable=False`. Original exception preserved on `__cause__`; full stack trace logged server-side with a correlation ID; wire envelope carries only the typed boundary + correlation ID (never the raw trace).

**Why bury cancellation as defect in v1:**

- Cancellation is rarely something the agent should reason about — it's usually a framework or user-initiated stop, not a tool semantic.
- Promoting to a dedicated `kind="cancelled"` later is additive (extension via Decision 3); demoting is not. Pick the conservative direction.
- One quarantine path simplifies the dispatch pipeline.

**Alternatives rejected:**

- Dedicated `kind="cancelled"` from v1: no proven use case; adds taxonomy weight.
- Let CancelledError propagate untouched: breaks the contract "no untyped exceptions on the wire."

### Decision 9 — Ship Pydantic ValidationError default enricher in a2effect

a2effect registers a default enricher (importable, opt-in) that translates `pydantic.ValidationError` into `InputError` with `details.fields` carrying the pydantic error list (loc, msg, type, input).

**Why:**

- Universal — every consumer using pydantic benefits without writing the same enricher.
- The pydantic ValidationError structure has fields the agent finds actionable (which field, why invalid).
- Opt-in (consumer enables it on their app) so consumers who handle validation differently aren't surprised.

**Alternatives rejected:**

- Don't ship: every consumer copy-pastes. Tax on adoption.
- Ship on by default: surprises consumers who already have validation translation. Opt-in is safer.

## Risks / Trade-offs

- **Lint registry maintenance for known-throwing functions** → stub set for httpx/asyncpg/redis/sqlalchemy/fastapi ships in a2effect. Drift risk: when those libs add functions, our stubs don't. Mitigation: extension via pyproject + inline `# a2effect: may-raise X` annotation; community PRs to the stub file; lint emits `A2K-RAISES-UNCOVERED` with the specific function name so the gap is visible.
- **`raises_as(coro, mapping)` evaluates the call expression eagerly** → sync raises from the call itself (not from awaiting the coroutine) escape the wrapper. Real but rare. Mitigation: lint also scans inside `raises_as` first-arg call for known-throwing sync functions; doc warning.
- **Multi-raise composition across helper calls is body-only in v1 lint** → transitive raise tracking through helper functions requires either annotation reading on every callee or full call-graph traversal. Mitigation: helpers carry their own `Raises` annotation, lint reads it cross-module (Pattern A from exploration); transitive into unannotated helpers stays best-effort with `# a2effect: may-raise X` escape.
- **Token cost on outputSchema** when clients surface tool schemas to the LLM → `ErrorEnvelopeSchema` is `$ref`'d once in components, not inlined per tool. Per-tool cost is ~50 tokens for the ref entry. Most clients (Claude Desktop, Claude Code) do NOT pass outputSchema to the LLM; cost is wire-only for them.
- **Cursor + langchain ignore `structuredContent`** → our single-mode rule makes structuredContent purely opportunistic; the contract holds entirely through `content[].text`. Even if every client deleted structuredContent support tomorrow, the typed-error story works.
- **`UnexpectedDefect` swallows the original exception class on the wire** → debugging gets harder without server-side log access. Mitigation: every defect emits a structured server-side log entry with full trace + correlation ID; envelope carries the correlation ID for cross-reference.
- **Migration to typed errors is opt-in per consumer** → some consumers may stay on v0.x indefinitely. Per user direction, this is fine — consumers migrate when the new thing is worth it. a2kit core dogfoods strict on its own tests to prove the value.
- **A future MCP spec change could invalidate the wire format** → research confirms 6-12 month runway; design forward-compatibility by keeping the envelope schema versioned and parseable structurally. If Anthropic ships a competing convention later, our envelope maps cleanly to most likely shapes (kind/retryable/hint are universal categories).

## Migration Plan

a2effect ships v0.1.0 as a new package. a2kit upgrades to depend on it in the integration commit. Consumers migrate at their own pace:

1. Bump a2kit to the version that takes a2effect dep.
2. Update enrichers: change `(exc) -> str | None` signatures to `(exc) -> AppError | None`. Mechanical (regex-shaped).
3. Add `Annotated[ReturnT, Raises(...)]` to every tool. Lint surfaces tools missing the annotation as error.
4. Run `contract_tests(app)` in pytest; fix any envelope shape mismatches.
5. Verify CLI exit codes and HTTP status codes match expectations in integration tests.

No rollback plan beyond `pip install a2kit==<previous-version>`. The old enricher path is removed cleanly; no shim mode.

## Open Questions

- **Package layout: monorepo workspace vs separate repo for a2effect?** Monorepo (sibling directory under a2kit's git tree) keeps cross-iteration tight; separate repo signals stronger independence but slows joint development. Lean monorepo for v1, extract if traction demands.
- **`ErrorEnvelope` schema version field placement** — top-level (`{version: "1", error: {...}}`) or out-of-band (header / spec)? Top-level adds bytes; out-of-band needs spec-text. Going with top-level `envelope_version: "1"` in v1; reconsider if it bloats.
- **Whether `Raises(...)` markers on service methods are required for full lint accuracy** — Pattern A (service has its own annotation) is supported but transitive lint trust depends on it. Should we lint *require* service methods called from tools to declare `Raises`? Probably yes, with `A2K-RAISES-HELPER-UNTYPED` warning rather than error. Decide during specs.
- **Should `outputSchema` be omitted for tools where the bare return is also `None` AND raises is empty?** Such tools have nothing meaningful to validate. Probably yes; emit nothing in that case. Decide during implementation.
