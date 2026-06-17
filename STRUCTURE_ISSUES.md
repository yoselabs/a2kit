# a2kit structure issues

Running ledger of architectural smells, redundancies, and pattern gaps
identified by structured audits. Each entry is **falsifiable**, **traced
to file:symbol**, and tagged with **status** so we don't re-investigate
resolved issues.

Last audit: **2026-05-27** (snapshot-based, aider repo-map 24k budget,
tests/evals/examples/docs excluded; 119 src .py files reviewed).

## Status legend

- **OPEN** — confirmed by trace, no proposal filed
- **PROPOSED** — openspec change drafted, see `openspec/changes/<name>/`
- **IN-FLIGHT** — openspec change being implemented
- **ARCHIVED** — resolved, see git log for the change
- **ALLOWLISTED** — confirmed but parked in `policies/data.json`
  pending a follow-up consolidation; the Rego policy layer prevents
  regression while the consolidation is deferred
- **FALSIFIED** — investigated, not a real issue (recorded so we don't
  re-litigate)
- **DEFERRED** — confirmed but explicitly parked; see reason

## Policy enforcement (since 2026-05-27, change `adopt-rego-policy-layer`)

Two Rego policies in `policies/` now enforce non-regression on the
audit findings:

- **`body_dup.rego`** (`REGO-BODY-DUP`) — flags cross-file function
  body duplication using a normalized AST hash. Catches the
  `_format_condensed_line`-style finding even when names differ.
- **`name_collision.rego`** (`REGO-NAME-COLLISION`) — flags cross-file
  `_`-prefixed (non-dunder) function name reuse outside the allowlist.

Bundle A (R2, R7, R8, R9) was drained in the same change as a
worked-example sweep — the audit-specified consolidations all landed
along with R6 and R1. The remaining allowlist entries in
`policies/data.json` are 7 entries (1 body_dup, 6 name_collision), all
genuine intentional convergences (Python idioms, Protocol contracts,
ADR-0019-accepted mirrors, coincidental shapes across different
domains). See ADR 0024 + `docs/dev/rego-toolchain.md`.

Each entry also tags the relevant ADR(s) so context survives drift.

---

## 1. Code smells

### S1. God-class `Container` — OPEN — HIGH
**Where**: `src/a2kit/packages/di/container.py` (645 LOC, ~38 methods)
**Claim**: mixes four orthogonal concerns:
1. **Registry** — `provide`, `has_provider`, `providers_view`, `register_wire_scope`
2. **Resolver** — `get`, `aresolve`, `_build_singleton`, `_build_scoped`, `_construct*`
3. **ScopeGraph validator** — `seal`, `_validate_scope_graph`, `_collect_reachable`
4. **Lifecycle / call boundary** — `call_scope`, `child`, `aclose`, `__aenter__`/`__aexit__`

A `Resolver` Protocol exists at `src/a2kit/packages/di/resolver.py:18` that
already names the seam — but `Container.resolve` and friends are tombstoned
via `_retired` and the live methods on the same class (`aresolve` /
`resolve_params`) bypass the Protocol.

**ADRs**: 0015 (layer manifest), 0019 (App/Runtime split — rationale extends here)
**Trace**: `grep -c '    def ' src/a2kit/packages/di/container.py`
**Resolution shape**: facade-over-collaborators, one per concern; keep
`async with container:` ergonomic at the facade. Substantial but bounded.

### S2. God-module `_verbs.py` — OPEN — HIGH
**Where**: `src/a2kit/_verbs.py` (508 LOC)
**Claim**: holds three public decorators (`read`/`write`/`list_`), a private
`_read_internal`, plus ~120 LOC of mutually-exclusive-flag validation:
`_stamp`, `_compute_report_schema`, `_kwargs_for`, `_reject_read_shaped_kwargs`,
`_reject_annotations_flag_conflict`, `_build_annotation_kwargs`. The
annotation-kwarg arithmetic belongs next to `metadata.py` (which owns
`A2KitMeta`).

**ADRs**: 0003 (semantic-flag vocabulary — locks the four flags, but says
nothing about implementation locality)
**Resolution shape**: extract annotation-kwargs to `_annotation_kwargs.py`
beside `metadata.py`; `_verbs.py` keeps the decorator surface only.

### S3. Magic-string discriminators across formatter + mcp + dispatch — OPEN — HIGH
**Where**: 5+ sites consume the same closed `Literal` set:
- `src/a2kit/packages/formatter/inference.py:144` declares
  `kind: Literal["tsv","page-tsv","json","envelope"]`
- `src/a2kit/packages/formatter/render.py:122,125,129,174,178,184` branches
  on `plan.kind == "tsv"|"page-tsv"|"envelope"` (6 sites)
- `src/a2kit/packages/mcp/format_routing.py:69` re-branches on `plan.kind == "tsv"`
- `src/a2kit/packages/mcp/server.py:184-188` branches on
  `reg.kind == "tool"|"prompt"|"resource"`

**Resolution shape**: `{kind: Encoder}` strategy registry; encoders implement
a small Protocol. Open-Closed for future kinds (`page-jsonl`, etc.).

### S4. `isinstance` ladder in `formatter/render.py` — OPEN — HIGH
**Where**: ~18 branches across `_json_default`, `_to_plain`, `_derive_columns`,
`render_plain`, `render_execute`, `_is_flat_record` (lines 31-206)
**Claim**: dispatches on `BaseModel | dict | list | tuple | Page | dataclass`.
The kink is `Page[T]` (generic), but `_page_item_type` already exists.
**Resolution shape**: `functools.singledispatch` renderer or small Visitor.

### S5. Two parallel signature-installers — DEFERRED (per ADR-0020)
**Where**:
- `src/a2kit/packages/mcp/_wrappers.py::install_mcp_signature` (projection path)
- `src/a2kit/packages/dispatch/substrate.py::install_substrate_signature` (substrate-native path)

**ADRs**: 0020 explicitly accepts this as the "byte-for-byte MCP test
guarantee" price.
**Why deferred**: collapse needs `ToolDescriptor` projection (S15) to land
first, then MCP byte-for-byte test suite rebaseline.

### S6. Hidden state machine in `Container` (sealed/lazy/per-call) — DEFERRED
**Where**: `Container.seal()`, `_request_scope` contextvar, `call_scope`
**Claim**: "compose → seal → call" phases encoded via method side-effects,
not as types. ADR-0019 addressed the outer-level phase but did not extend
down into the container.
**Why deferred**: no live footgun; ADR-0019 deliberately kept this informal.
Revisit only if a silent-mutation bug surfaces.

### S7. DecoratorSurface template extracted too shallow — OPEN — MEDIUM
**Where**: `src/a2kit/packages/dispatch/surface.py:DecoratorSurface[R]`
**Claim**: template owns only `registrations` accumulator. The actual
`_decorator(...)` + `_wrap(...)` logic in `mcp/surface.py` and `http/api.py`
is ~90% the same shape.
**Resolution shape**: lift the per-verb `_record_with_kwargs` shape into
the template; subclasses provide only the substrate-specific kwargs handling.

### S8. Duck-typed Router contract — OPEN — MEDIUM (AGENTS.md §3 violation)
**Where**: `src/a2kit/packages/dispatch/stages.py:128` uses
`hasattr(router, "__aenter__")`; `app.py` does similar attribute lookups
for `router.enrichers`, `router.slug`, `router.tools`.
**Claim**: `Router` is a framework-owned type defined at
`src/a2kit/routers.py:11`. AGENTS.md §3 forbids defensive `hasattr` against
types the framework owns.
**Resolution shape**: lift `Router` to a `Protocol` with `__aenter__`
optional via a sibling `EnterableRouter`, or make `__aenter__` mandatory
(default no-op). Lint rule can then enforce.

### S9. Naming inconsistency on registration hooks — DEFERRED
**Where**: `app.provide(T, factory)`, `app.add_router(r)`, `app.add_cli(cmd)`,
`app.add_mcp_middleware(mw)`, `app.log.add_sink(s)`, `app.mcp.tool()`,
`app.api.get(path)`, `app.health_check(fn)`, `app.enricher(fn)`, `app.auth(spec)`
**Claim**: three verb shapes (`provide`, `add_*`, bare verb) for one
concept (add to a registry).
**Why deferred**: wait for `adopt-plugin-manifests` (in-flight) to
converge; one rename pass after manifests will be cheaper than two.

### S10. `Substrate` literal removal incomplete — OPEN — MEDIUM
**Where**: `src/a2kit/packages/dispatch/substrate.py:535+`
**Claim**: deprecation comment about retiring `Literal["fastapi","fastmcp"]`
still present; `_foreign_surface_owning`, `_reject_substrate_dep_on_alien_surface`,
`fastapi_reserved`, `fastmcp_reserved` still string-compare surface names
despite `Surface` Protocol carrying `reserved_types` / `substrate_dep_markers`
directly.
**Resolution shape**: consumers walk the registered surfaces via
`SurfaceRegistry` instead of calling helper functions named for two specific
substrates.

### S11. HTTP transport missing the typed-render-stage pattern — ARCHIVED (2026-05-27, `dispatch-pipeline-parity-on-http`) — MEDIUM
**Where**:
- MCP path uses `dispatch/envelope.py:ErrorEnvelopeStage` → side-channel
  `get_rendered_error` → `mcp/_wrappers.py:McpErrorRenderStage` (read pattern)
- CLI path uses the same side-channel → `cli/runtime.py:CliErrorRenderStage`
- HTTP path uses `http/build.py:_install_typed_error_handlers` (separate
  FastAPI `@app.exception_handler(AppError)` that re-derives the envelope)
  + `http/build.py:_apply_authorize_gate` (parallel impl of authorize gate)

**Claim**: HTTP regressed/never adopted the side-channel pattern introduced
by commit `1101d05` (refactor(dispatch): explicit side channel for
ErrorEnvelopeStage render state).
**Resolution shape**: add `HttpErrorRenderStage` mirroring `McpErrorRenderStage`
and `CliErrorRenderStage`; codify "every transport adapter appends exactly
one render stage" as an invariant + lint rule.

### S12. `**_kw` chain compliance drift — OPEN — LOW
**Where**:
- `App.__init__(**_kw)` raises loudly (per AGENTS.md §1) ✓
- `Router.__init__(**_kw)` swallows without the parallel loud-crash ✗
- `provide(**_kw)` swallows without the parallel loud-crash ✗

**Resolution shape**: fold into next AGENTS.md audit sweep; not a
structural change.

### S13. `AuthorizeGateStage` duplicated on HTTP path — ARCHIVED (2026-05-27, `dispatch-pipeline-parity-on-http` — HTTP now folds `DISPATCH_PIPELINE` per tool; `_apply_authorize_gate` deleted) — MEDIUM
**Where**:
- Pipeline stage at `dispatch/stages.py:206` — self-skips when
  `spec.meta.extras.authorize is None`
- `http/build.py:_apply_authorize_gate` re-implements the gating around
  the FastAPI wrapper

**Claim**: same intent in two implementations.
**Resolution**: pairs with S11 — when HTTP adopts the typed-render-stage
pattern, the authorize-gate handling collapses too.

---

## 2. Confirmed redundancies (traced 2026-05-27)

All entries below were verified by ripgrep against the working tree.

### R1. Two identical `_call` helpers in dispatch — ARCHIVED (2026-05-27, `adopt-rego-policy-layer`) — HIGH
**Where**:
- `src/a2kit/packages/dispatch/envelope.py:69` — `async def _call(fn, *args, **kwargs)`
- `src/a2kit/packages/dispatch/stages.py:33` — `async def _call(fn, *args, **kwargs)`

**Trace**: same signature; body delta is one docstring line.
**Resolution shape**: one `_call` in `packages/dispatch/_invoke.py`; both
stages import.

### R2. Two `resolve_hints` functions — ARCHIVED (2026-05-27, `adopt-rego-policy-layer` Bundle A drain) — HIGH
**Where**:
- `src/a2kit/signature.py:22`
- `src/a2kit/packages/di/_hints.py:22`

**Trace**: same signature, different layer ownership.
**Resolution shape**: collapse to `packages/di/_hints.py` (lower layer);
`signature.py` imports it.

### R3. Two `_edit_distance` functions — ARCHIVED (2026-05-27, residue drain — lifted to `packages/lint/_distance.py`) — HIGH
**Where**:
- `src/a2kit/packages/lint/runtime.py:103`
- `scripts/find_similar.py:21`

**Resolution shape**: lift to `packages/lint/_distance.py`; script imports it.

### R4. Two `_list_tool_names` functions — ARCHIVED (2026-05-27, residue drain — promoted to public `list_tool_names` in `packages/lint/runtime.py`) — HIGH
**Where**:
- `src/a2kit/packages/lint/runtime.py:38`
- `scripts/find_similar.py:36`

**Resolution shape**: keep in `packages/lint/runtime.py`; script imports it.

### R5. Two `_import_target` functions — ARCHIVED (2026-05-27, residue drain — lifted to `packages/lint/_import.py`; CLI wraps for Click) — HIGH
**Where**:
- `src/a2kit/packages/lint/cli.py:37`
- `scripts/find_similar.py:44`

**Resolution shape**: lift to `packages/lint/_import.py`.

### R6. Two log line-formatter triples — ARCHIVED (2026-05-27, `adopt-rego-policy-layer`) — HIGH (drift-risk closed)
**Where**:
- `src/a2kit/packages/log/wire.py:19-32` — `_cap_text`, `_format_kv`, `format_condensed_line`
- `src/a2kit/packages/context/stderr.py:336-348` — `_cap_text`, `_format_kv`, `_format_condensed_line`

**Trace**: same shapes, constant `TEXT_CAP` (wire) vs `_TEXT_CAP` (stderr)
with the same value. Per the log wire-format invariant, drift between
these two is a wire-shape bug.
**Resolution shape**: canonical formatter in `packages/log/wire.py`;
`stderr.py` imports it. Add a lint check (or property test) asserting the
two output identically for the same input.

### R7. Five `_is_basemodel*` variants — ARCHIVED (2026-05-27, `adopt-rego-policy-layer` Bundle A drain — runtime variants collapsed to canonical `is_basemodel` in formatter/inference; AST variants collapsed via R9) — HIGH
**Where**:
- `src/a2kit/packages/formatter/inference.py:42` — `_is_basemodel(tp) -> bool`
- `src/a2kit/packages/cli/builder.py:84` — `_is_basemodel(ann) -> type[BaseModel] | None`
- `src/a2kit/packages/codemode/marshal.py:26` — `_is_basemodel(tp) -> bool`
- `src/a2kit/packages/lint/rules/local_return_model.py:26` — `_is_basemodel_base(base: ast.expr) -> bool`
- `src/a2kit/packages/lint/rules/local_return_model.py:39` — `_is_basemodel_classdef(cls: ast.ClassDef) -> bool`
- `src/a2kit/packages/lint/rules/no_dict_str_any.py:44` — `_is_basemodel_base(base: ast.expr) -> bool`

**Trace**: three signatures across two axes (runtime type vs AST node;
returns bool vs the class).
**Resolution shape**: one `is_basemodel(tp) -> type[BaseModel] | None` in
`packages/formatter/inference.py` (lowest layer) for the runtime variants;
one shared AST helper in `packages/lint/rules/_ast_helpers.py` for the
lint variants. Five → two.

### R8. Two `_validate_key` functions in connections — ARCHIVED (2026-05-27, `adopt-rego-policy-layer` Bundle A drain) — HIGH
**Where**:
- `src/a2kit/packages/connections/config.py:45`
- `src/a2kit/packages/connections/store.py:28`

**Trace**: same signature, same package.
**Resolution shape**: lift to `packages/connections/_validation.py`.

### R9. Four verb-decorator detectors in lint — ARCHIVED (2026-05-27, `adopt-rego-policy-layer` Bundle A drain — verb-decorator detector collapsed to `detect.is_a2kit_verb_decorator`; AST `_is_basemodel_base` lifted to `packages/lint/rules/_ast_helpers.py`) — HIGH
**Where**:
- `src/a2kit/packages/lint/rules/detect.py:15` — `is_a2kit_tool_decorator(dec) -> bool` (public)
- `src/a2kit/packages/lint/rules/log.py:29` — `_is_a2kit_verb_decorator(dec) -> bool`
- `src/a2kit/packages/lint/rules/log.py:83` — `_has_a2kit_verb_decorator(fn) -> bool`
- `src/a2kit/packages/lint/rules/surface.py:45` — `_is_a2kit_verb_decorator(dec) -> ast.Call | None`
- `src/a2kit/packages/lint/rules/substrate_dep.py:28` — `_is_verb_decorator(node) -> tuple[bool, ast.Call | None]`

**Trace**: three different return shapes for one detection job.
**Resolution shape**: one `detect.is_a2kit_verb_decorator(dec) -> ast.Call | None`
— callers either truthy-check or unpack the Call. The tuple-returning
variant collapses to `(call is not None, call)`.

### R10. Lazy `__getattr__` pattern duplicated 7× — ARCHIVED (2026-05-27, residue drain — 5 lazy loaders consolidated onto `a2kit._lazy_module.lazy_attr` / `lazy_dir`; the 2 tombstones at `packages/cli/context.py` + `packages/dispatch/substrate.py` are migration-hint sites, separate smell) — MEDIUM
**Where**:
- `src/a2kit/__init__.py`
- `src/a2kit/packages/auth/__init__.py`
- `src/a2kit/packages/cli/context.py`
- `src/a2kit/packages/dispatch/substrate.py`
- `src/a2kit/packages/http/__init__.py`
- `src/a2kit/packages/mcp/__init__.py`
- `src/a2kit/packages/otel/__init__.py`

**Trace**: same table-lookup-then-import-then-cache pattern hand-rolled
per module.
**Resolution shape**: `from a2kit._lazy_module import lazy_attr` helper;
each module declares its `_LAZY_ATTRS` table and binds
`__getattr__ = lazy_attr(_LAZY_ATTRS)`. Test that cold-start cost is
unchanged.

### R11. Two MCP lifespans for a binary flag — ARCHIVED (2026-05-27, residue drain — collapsed to `_build_mcp_lifespan(*, own_app_lifecycle)`) — LOW
**Where**: `src/a2kit/packages/mcp/server.py`:
- `_build_mcp_mount_lifespan(app, user_lifespan)` — multiplexed
- `_build_standalone_lifespan(app, user_lifespan)` — stdio

`build_mcp_server` already takes `own_app_lifecycle: bool = True`.
**Resolution shape**: collapse to `_build_mcp_lifespan(app, user_lifespan, *, own_app_lifecycle)`.

### R12. Two Page→TSV encoders — ARCHIVED (2026-05-27, residue drain — shared `assemble_page_envelope` helper; entry points kept for typed vs dict-after-FastMCP semantics) — LOW
**Where**:
- `src/a2kit/packages/formatter/page.py:encode_page_tsv(page: Page)` — typed input
- `src/a2kit/packages/formatter/render.py:encode_page_tsv_dict(payload: dict)` — dict input

**Resolution shape**: dict path coerces to Page (`Page.model_validate`) and
delegates to the typed encoder. Falsifies if the dict path receives
genuinely partial / non-Page data legitimately — verify call-sites.

### R13. Substrate-reserved resolver pattern, copied per substrate — ARCHIVED (2026-05-27, residue drain — surfaces call canonical `fastapi_reserved` / `fastmcp_reserved` / `fastapi_dep_markers` from dispatch front door; new `_FASTAPI_DEP_MARKER_SPECS` in dispatch/substrate.py mirrors the markers; turned out to be 3 inline copies of an existing canonical helper, no substrate-front-door refactor needed) — LOW
**Where**:
- `src/a2kit/packages/http/api.py` — `_resolve_api_reserved()`, `_resolve_api_substrate_dep_markers()`
- `src/a2kit/packages/mcp/surface.py` — `_resolve_mcp_reserved()`

**Trace**: same lazy-import-then-frozenset shape.
**Resolution shape**: shared
`_lazy_reserved(import_specs: tuple[tuple[str,str], ...]) -> frozenset[type]`
helper.

### R14. `RequestScopeMissing` vs `RuntimeError` for same condition — OPEN — LOW
**Where**:
- `src/a2kit/packages/context/request_scope.py:RequestScopeMissing(LookupError)` — canonical
- `src/a2kit/packages/di/_fastapi_bridge.py` raises plain
  `RuntimeError("a2kit Depends resolver called outside call_scope...")`

**Resolution shape**: raise `RequestScopeMissing` from both paths; transport
handlers translate as needed. Falsifies if FastAPI middleware swallows
`LookupError` specifically.

### R15. CLI invoke fan-out: 5 entry points — OPEN — MEDIUM
**Where**: `src/a2kit/packages/cli/runtime.py`:
- `_invoke_tool_in_process(fn, kwargs, *, fmt='auto', spec)`
- `_invoke_tool_in_process_raw(fn, kwargs, *, spec)`
- `invoke_tool_sync(fn, kwargs, *, fmt='auto', spec) -> str`
- `invoke_tool_sync_raw(fn, kwargs, *, spec) -> Any`
- `invoke_tool_sync_json(fn, kwargs, *, spec)` + `serialize_for_json_mode(raw)`

**Claim**: 3-mode (formatted / raw / json) × 2-shape (sync wrapper / async body)
matrix; could collapse to `invoke_tool_sync(..., mode: Literal[...])`.
**Resolution shape**: one async `_invoke_tool` returning a `Rendered`-union;
one sync wrapper; callers pass `mode`.

### R16. `enter_lifecycle` vs `register_instance_cleanup` cross-module — OPEN — LOW
**Where**:
- `src/a2kit/packages/di/_helpers.py:enter_lifecycle(result)` — handles
  `__aenter__`/`__aexit__` only
- `src/a2kit/_lifecycle_helpers.py:register_instance_cleanup(stack, instance)` —
  extends to `aclose()` / `close()`

**Claim**: probably complementary, not duplicate — but split across
`a2kit/` (root) and `packages/di/` muddles ownership.
**Resolution shape**: consolidate into `packages/di/_lifecycle.py`;
`_lifecycle_helpers.py` becomes a thin re-export or goes away.

### R17. `_principal_placeholder` inline in `App.__init__` — OPEN — LOW
**Where**: `src/a2kit/app.py:_default_dispatch_hook` block has an inline
`_principal_placeholder()` factory; the real `Principal` lives at
`src/a2kit/packages/context/principal.py`.
**Resolution shape**: extract `EmptyPrincipal` singleton to
`packages/context/principal.py`; `app.py` imports it.

---

## 3. Falsified hypotheses (do not re-investigate)

### F1. `ToolDescriptor` is broadly bypassed — FALSIFIED 2026-05-27
**Original claim**: 8+ substrate consumers re-derive their tool view from
`A2KitMeta` via `get_meta(fn)` instead of using a `ToolDescriptor` projection.
**Trace verdict**: `ToolDescriptor` is imported by 4 substrate consumers
(`app`, `runtime`, `testing/client`, `cli/builder`) — usage is fine. `get_meta`
is called from 5 authoring-side files (`schema`, `tool`, `routers`, `app`,
`metadata`) — that's correct usage at stamp time. The real gap is narrow:
**`mcp/server.py:_meta_to_dict(meta)` is the only substrate-side projection
bypass**. See R18 (replacement, bounded).

### F2. `dispatch/substrate.py:__getattr__` is a backcompat shim — FALSIFIED 2026-05-27
**Original claim**: module-level `__getattr__` is a suspect AGENTS.md §1
violation.
**Trace verdict**: it raises `AttributeError` with a migration hint for
the removed `Substrate` Literal, per AGENTS.md §4 ("errors carry migration
hints"). Compliant — could be cited as a canonical example.

### F3. `exceptions.py` is a god-module — FALSIFIED 2026-05-23
**Original claim** (from pyan3 spike): 20+ importers, candidate for splitting.
**Trace verdict**: actual import count is 10 files, and the module is
cohesive by audience (typed-error catalogue with shared `A2KitError` base).
Do not split.

---

## 4. Narrow follow-ups (from falsified-but-real-underneath)

### R18. `mcp/server.py:_meta_to_dict` is the projection bypass — OPEN — LOW
**Where**: `src/a2kit/packages/mcp/server.py:_meta_to_dict(meta: A2KitMeta)`
**Claim**: MCP server re-derives a dict view from `A2KitMeta` while CLI,
HTTP, and testing already consume `ToolDescriptor` cleanly. Bounded
single-file change — route through `ToolDescriptor` instead.

---

## 5. Tombstone / hygiene audits

### T1. Container tombstones lack ADR-0018 death dates — OPEN
**Where**: `src/a2kit/packages/di/container.py` carries 7 tombstoned methods
that raise via `_retired(...)`:
- `register`, `register_singleton`, `resolve`, `aresolve`, `has`,
  `has_async_singleton`, `has_any_async_singletons`

**Claim**: ADR-0018 (tombstone lifecycle) defines "birth, shape, **death**".
Each tombstone should have a planned death version. Audit current entries;
sweep ones past their sunset.

### T2. `_StubResourceResult` scope verification — OPEN — LOW
**Where**: `src/a2kit/packages/context/stderr.py:1816` — duck-types
`mcp.types.ResourceResult` to avoid heavy `mcp.types` import on CLI cold start.
**Verify**: confirm `mcp.types.ResourceResult` is never imported on the CLI
path. If it is, this stub is dead code.
**Trace**: `rg -n 'from mcp\.types' src/a2kit/packages/cli/ src/a2kit/packages/context/`

---

## 6. Missing / under-applied patterns

### P1. Pipeline ordering invariants are not codified — OPEN — LOW
**Where**: `src/a2kit/packages/dispatch/pipeline.py:DISPATCH_PIPELINE` tuple
declares stage order; constraints (EnricherStage inside ErrorCaptureStage
inside ErrorEnvelopeStage; TimeoutStage innermost; ErrorEnvelopeStage
terminal) live in stage docstrings, not in verifiable code.
**Resolution shape**: add `DispatchStage.position` enum
(`INNERMOST | EARLY | LATE | OUTERMOST_NEUTRAL | TERMINAL`); `fold_pipeline`
asserts the partial order at build time. Defer until a real ordering bug
lands.

### P2. App vs AppRuntime mirrored read-side surface — DEFERRED
**Where**: `App` and `AppRuntime` both expose ~10 mirrored properties
(`routers`, `tools`, `cli_extras`, `mcp_middlewares`, `dispatch_hook`,
`has_default_dispatch_hook`, `container`, `_resolver`, `log_reports`,
`log_events`).
**Claim**: a `RuntimeView` Protocol could de-dup the read-side surface.
**Why deferred**: ADR-0019 explicitly accepts this as the price of "one
public type" + sealed runtime. Low payoff vs amendment cost.

### P3. Per-call contextvar map — OPEN — DOC-ONLY
**Where**: at least four per-call contextvars exist:
- `_request_scope` (`packages/context/request_scope.py`)
- `_a2kit_request_scope` (`packages/di/_fastapi_bridge.py`)
- `_render_state` (`packages/dispatch/_render_state.py`)
- log ambient `_CallScope` (`packages/log/ambient.py`)

**Claim**: each is justified; the count and disjoint ownership warrant a
map (who reads each, who writes, lifecycle order).
**Resolution shape**: `docs/per-call-contextvars.md` ASCII diagram. Not a
code change.

### P4. Capability-typed handles beyond `Lazy[T]` — DEFERRED
ADR-0008's `Lazy[T]` is the pattern; obvious next candidates are
`PerCall[T]` (declarative `provide(..., per_call=True)`) and `Scoped[T]`.
Defer until a real consumer asks; ADR-0009's kwarg works.

---

## 7. Proposed change bundles

### Bundle A: `consolidate-utility-duplications` — ready to propose
Folds **R1, R2, R3, R4, R5, R6, R7, R8, R9, R10** into one openspec
change. Codifies AGENTS.md §2 ("no multiple ways of doing the same
thing"). Low risk, mechanical. Should also add a lint rule (jscpd-style or
a custom AST check) to prevent regression.

### Bundle B: structural improvements — propose individually
- `split-di-container-by-responsibility` (S1)
- `strategy-registry-for-formatter-kinds` (S3 + S4 + P1 alignment)
- `complete-transport-render-stage-pattern` (S11 + S13)
- `extract-substrate-literal-residue` (S10)
- `lift-decorator-surface-template` (S7)
- `route-mcp-server-through-tooldescriptor` (R18) — bounded one-file fix
- `unify-signature-installers` (S5) — **DEFERRED** until R18 + ADR-0020
  byte-for-byte test rebaseline path is ready

### Bundle C: hygiene sweep
**R11, R12, R13, R14, R15, R16, R17, S8, S12, T1, T2, P3** — small,
mechanical. Could land as one `2026-Q3-hygiene-sweep` or trickle in as
incidental fixes.

---

## 8. Cross-reference: active openspec changes

These are in flight (as of 2026-05-27) — proposals here must not duplicate
or contradict:

- **`the log-handler fan-out work`** — owns log-area concerns. R6
  (log line-formatter consolidation) should coordinate with this change
  to avoid spec-delta conflict.
- **`adopt-plugin-manifests`** — already partially on disk
  (`packages/_plugin.py`, `packages/auth/_providers/api_key.py`). S9
  (registration verb naming) **must wait** for this to converge.

## 9. Methodology

Two-pass audit:
1. **Parallel-agent structural audit** (2026-05-23) — 4 agents on distinct
   axes (aider repo-map / repomix / pyan3+code2flow / tach). 10 smells, 6
   cross-confirmed, 3 OpenSpec proposals queued. Recorded at
   `Researches/132-a2kit-structural-audit/`.
2. **Snapshot-grounded re-analysis** (2026-05-27) — aider repo-map at 24k
   token budget excluding tests/evals/examples/docs, read end-to-end, then
   each hypothesis traced by ripgrep against working tree. Falsified two
   prior findings (F1, F2) and confirmed 17 new redundancies (R1-R17).

## 11. Composition / coupling audit (2026-05-29)

4-agent parallel audit (coupling-hotspot / missing-pattern / recent-deltas /
layering-seam axes) on the post-v0.41 surface. Lens: composition + layering +
tight-coupling, NOT duplication (§1-§6 covered that). The recent wave (config
engine, surfaces-passive, request_scope unification, plugin manifests, Rego,
HTTP-folds-pipeline) introduced **little new debt** — it mostly CLOSED prior
smells (S11/S13) and applied sound patterns. The real coupling is OLDER and
deeper. Cross-confirmed findings (≥2 agents), ranked:

### C1. `ToolBuildSpec` carries the concrete `AppRuntime` — OPEN — HIGH (3-agent confirmed)
**Where**: `dispatch/spec.py:ToolBuildSpec.app`; read across `dispatch/stages.py`
(`spec.app._resolver`, `spec.app._ensure_router_entered()`, `spec.app.config.log`,
`spec.app.has_default_dispatch_hook()` — `# noqa: SLF001` seams).
**Claim**: the transport-NEUTRAL dispatch pipeline (the crown-jewel abstraction,
ADR 0019/0025) depends on the runtime-LAYER concrete type via PRIVATE attributes.
Blocks unit-testing stages in isolation; blocks an alternative runtime. A
`Resolver` Protocol already exists at `packages/di/resolver.py` but the stages
bypass it for `app._resolver`. This is the ROOT of several symptoms (the
App/AppRuntime mirror surface P2, the `_resolver` back-door).
**Resolution shape**: Dependency Inversion — shrink `ToolBuildSpec` to carry the
narrow Protocols each stage declares (`Resolver`, a `RouterLifecycle` seam),
not the whole `AppRuntime`. The Protocol is drawn; the stages just don't use it.
**Note**: collides with ADR 0027 (which rewrites
`CallScopeStage` + how config flows in). Sequencing: do C1's `LogConfig`-injection
slice WITH the refound (same code, avoids rewriting the stage twice).

### C2. The `Surface` Protocol is half-built — OPEN — MED (2-agent confirmed)
**Where**: `dispatch/surface.py:Surface` owns marker types + reserved-type
allowlists, but NOT the per-tool wrapping sequence. Each transport re-implements:
error-render (`cli/runtime.py:CliErrorRenderStage`, `mcp/_wrappers.py:McpErrorRenderStage`,
`http/_error_render_stage.py:HttpErrorRenderStage` — ~90% same shape), tool-wrap
(fold_pipeline + render-stage + sig-install, 3 hand-codings), tool-filter
(expose+visibility loop — and **HTTP DRIFTED**: `http/build.py:83` filters `expose`
but skips the `visibility != hidden` check the other two do — latent bug).
**Resolution shape**: Template Method / Strategy — `Surface` mandates
`error_render_stage()` + the canonical wrap sequence; "every transport appends
exactly one render stage, folds in canonical order" becomes type-enforced, not
convention. Natural sequel to ADR 0025.

### C3. `build()` stores list references then mutates post-construction — OPEN — MED (latent bug)
**Where**: `runtime.py` — `build()` passes `routers`/`descriptors` lists to
`AppRuntime.__init__` BY REFERENCE, then (for the `_meta` health router)
`routers.append(...)` / `descriptors.extend(...)` AFTER construction, mutating
the lists the sealed runtime holds. Violates the sealed-runtime immutability
ADR 0019 promises.
**Resolution shape**: build the full descriptor/router set BEFORE constructing
`AppRuntime`; pass `list(...)` copies; no post-init mutation. Small, real,
fixable independently.

### C4. Container compose→seal→call is an implicit state machine — DEFERRED (was S6)
**Where**: `di/container.py` `_sealed` flag + contextvar phases.
**Status**: prior audit (S6) deferred "no live footgun." C3 IS arguably that
footgun surfacing. Revisit alongside C1/C3 if the seam is touched; otherwise
ADR-0019-accepted.

**Methodology note**: this audit was SCOPED by the user to inform the
log/logging work first; C1's `LogConfig`-injection slice is folded into
ADR 0027. C1 (full), C2, C3 are recorded here as
falsifiable findings, NOT yet proposed — pick up post-refound.

## 10. Maintenance

Append entries; do not edit accepted ADRs in place. When an entry moves
to `PROPOSED` or `IN-FLIGHT`, link the openspec change name. When
`ARCHIVED`, link the merge commit. Falsified entries stay in §3 forever
so we don't re-investigate.
