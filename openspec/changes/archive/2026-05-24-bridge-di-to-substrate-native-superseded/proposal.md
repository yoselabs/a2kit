## Why

a2kit's `Container.call_scope` and FastAPI's `Depends` graph are two parallel universes that meet only inside the substrate wrapper. ADR 0020 explicitly documents the gap: `dependency_overrides[T]` is a no-op for a2kit-resolved types. The cost is structural:

- A FastAPI `Security(...)` guard like `def authorize(*, principal=Depends(oauth2), db: Database)` cannot resolve `db` through a2kit, because FastAPI walks its `Depends` graph **before** the a2kit wrapper runs.
- A tool body cannot mix native FastAPI `Depends(...)`-typed params (third-party FastAPI deps the ecosystem ships) with a2kit `Container`-known types — the signature splitter classifies them all as `wire`, breaking FastAPI's introspection.
- MCP-side: there is no equivalent of `principal` propagation — FastMCP's Context-borne principal never reaches `call_scope`, so an `authorize=` callable taking `principal: Principal` cannot work uniformly across substrates.

The user pin (2026-05-23): **"DI must be available everywhere, compatible with FastAPI DI — security handlers will need to consume some deps."** That requires a bidirectional bridge. This change is the load-bearing mechanism that the Surface protocol, the `add-auth` proposal, and any future substrate addition depend on.

## What Changes

- **New `Principal` type** in `a2kit.packages.context`: opaque record (subject, scopes, claims dict, raw_token reference, issued_by). Substrate-neutral. Both FastAPI middleware and FastMCP auth populate it.
- **New `substrate-dep` 4th class** in the signature splitter. `install_substrate_signature` (`packages/dispatch/substrate.py`) classifies params into `{reserved, container-known, substrate-dep, wire}`:
  - `substrate-dep` = param whose annotation carries a `Depends(...)` / `Security(...)` marker. For `substrate="fastapi"`: pass through to FastAPI's `__signature__`. For `substrate="fastmcp"`: raise `SubstrateSignatureError` (these markers are FastAPI-only).
  - Allowlist-extensible: a substrate can declare additional dep markers via the Surface protocol (added in `add-surface-protocol`).
- **New `Container.expose_as_fastapi_depends()` bridge** on the container: for every provider `T`, generate a FastAPI-compatible `Depends(_a2kit_resolve_T)` callable. `_a2kit_resolve_T` reads the active `_a2kit_scope` contextvar and returns `scope.get(T)`. Registered into FastAPI's `dependency_overrides` map at `build_http_app` time so user code uses ordinary `Annotated[T, Depends(...)]` and gets the a2kit-resolved instance.
- **New `_a2kit_principal_provider` SCOPED provider**: when the substrate wrapper runs, before invoking the tool body, it writes the resolved `Principal` into `call_scope` as a SCOPED `Principal` provider. So `def authorize(*, principal: Principal, db: Database)` resolves both naturally — `principal` from the scoped provider, `db` from the container provider exposed as a FastAPI `Depends`.
- **FastMCP-side principal extraction**: a small middleware in `packages/mcp/` reads the FastMCP `Context.principal` (or equivalent — pinned in design) and writes it into `call_scope` for the same downstream consumption.
- **`authorize=` enforcement wires through DI**: the dispatch pipeline's authorize-gate stage (new) resolves the `authorize` callable's params through `call_scope` exactly like a tool body, then invokes with `(principal=..., **resolved_kwargs)`. False return → transport-appropriate denial (403 / MCP error envelope).
- **BREAKING**: `Container.dependency_overrides` no-op exception removed from ADR 0020. The bridge makes it work properly. Any test relying on the documented "FastAPI overrides do nothing for a2kit types" raises with migration hint pointing to `container.override(T, fake)` (the canonical test seam from ADR 0006).
- **Lint rule `A2K-SUBSTRATE-DEP`** (new): a param typed `Annotated[T, fastapi.Depends(...)]` inside a function exposed to `mcp` (per `expose=`) is a hard error at lint time. Today this would be a silent ValueError at `install_substrate_signature`; promote to build-time.

## Capabilities

### New Capabilities

- `di-substrate-bridge`: bidirectional bridge between a2kit's `Container` and substrate-native DI graphs (FastAPI `Depends`/`Security`, FastMCP Context principal). Allows substrate-native consumers to resolve a2kit deps and vice versa.
- `principal-propagation`: a2kit-owned `Principal` type populated by whichever substrate authenticated the request, available as a SCOPED provider inside `call_scope`.

### Modified Capabilities

- `di-container-package`: `Container` gains `expose_as_fastapi_depends()` and SCOPED-write API for substrate-resolved values.
- `request-scoped-di`: scope now carries an optional `Principal` provider populated before tool body runs.
- `http-surface`: `build_http_app` wires the bridge into FastAPI's `dependency_overrides`; documents that FastAPI `Depends` chains see a2kit deps natively.
- `multi-surface-authoring`: signature splitter learns the `substrate-dep` 4th class; ADR 0020's documented `dependency_overrides[T]` no-op is superseded.
- `module-layout-discipline`: adds `A2K-SUBSTRATE-DEP` lint rule.

## Impact

- `packages/dispatch/substrate.py`: split-signature gains a 4th category; `install_substrate_signature` gains substrate-dep passthrough vs reject branches.
- `packages/di/container.py`: new `expose_as_fastapi_depends()` method; SCOPED-write helper for `Principal`.
- `packages/http/build.py`: wires the bridge at sub-app construction.
- `packages/mcp/`: small middleware extracting FastMCP principal into `call_scope`.
- `packages/context/`: defines `Principal`.
- Dispatch pipeline: new `AuthorizeGateStage` (only inserted if any descriptor declares `authorize=`).
- Cold-start: no new eager imports — FastAPI is already lazy via `packages/http/__init__.py` PEP 562 `__getattr__`; the bridge is only constructed inside `build_http_app`.
- `add-auth` proposal becomes downstream consumer: defines `GoogleAuth/APIKeyAuth/JwtAuth` wrappers that produce `Principal` instances; that proposal updated to remove its own `Principal` definition.
- Test churn: ADR 0020's `test_dependency_override.py` rewritten to assert the bridge works (today it asserts the gap exists).

---

## SUPERSEDED 2026-05-24

This umbrella was reshaped into 4 single-cycle changes before any code was written:

- [[add-principal-type]] — owns the `Principal` dataclass + framework-ownership rule.
- [[add-substrate-dep-class]] — owns the 4th signature class + `A2K-SUBSTRATE-DEP` lint rule.
- [[bridge-container-fastapi-depends]] — owns `Container.expose_as_fastapi_depends` + `build_http_app` wiring + ADR 0020 discharge.
- [[propagate-principal-and-authorize]] — owns the SCOPED Principal write + MCP middleware + `AuthorizeGateStage`.

Same scope, split for single-cycle commits. Apply order: A → B → C (depends on B) → D (depends on A + C). Archive this umbrella alongside the four when the chain completes.
