## 1. A — LDD ctx binding consistency across transports

- [x] 1.1 In `src/a2kit/packages/cli/runtime.py:48-50`, drop the `if ctx_param_name and ctx_param_name not in call_kwargs: call_kwargs[ctx_param_name] = StderrToolContext()` synthesis. When `ctx_param_name` is truthy, the kwarg is bound by the dispatch hook or by the CLI invocation path; when it is falsy, the runtime SHALL NOT enter `ldd_state_for_call` at all (mirror the MCP `_wrap_with_ldd_state` gate).
- [x] 1.2 In `src/a2kit/packages/testing/client.py:218-228` (the `invoke` path), gate the `_CapturingContext` binding on `meta.context_param_name`. Do not synthesize a capturing context when the tool did not declare `ctx`.
- [x] 1.3 Ensure the same gating applies in the `call_wire` path (which composes `invoke`); verify no second synthesis happens there.
- [x] 1.4 Update the in-repo test fixtures that called LDD primitives from tools without `ctx`. Expected count: small. Either declare `ctx: ToolContext` on the tool, or call from a `null_context()` shim if the test was unit-style.
- [x] 1.5 Add tests asserting `AmbientContextMissing` is raised on CLI and TestClient when a no-ctx tool calls `await a2kit.ldd.event(...)` — mirror the MCP scenario.

## 2. B — Container._override owns the three-attribute mutation

- [x] 2.1 Add `Container._override(self, type_: type, instance: object) -> None` to `src/a2kit/packages/di/container.py`. Implement the three-attribute mutation (constant factory in `_providers`, `instance` in `_singletons`, `_async_factories.discard(type_)`). Keep the method feature-agnostic and underscore-prefixed.
- [x] 2.2 Replace the three `# noqa: SLF001` lines in `src/a2kit/packages/testing/client.py:158-162` with a single `container._override(type_, fake)` call.
- [x] 2.3 Add a Container unit test covering: override pinning a singleton, override pinning a per-call provider, override clearing an async-factory marker, and override-then-restore returning the container to its pre-snapshot state.

## 3. F — LDD shorthand error fidelity

- [x] 3.1 In the LDD primitives module, change `info`, `warning`, `error`, `debug` so each calls `_require_ambient_state("a2kit.ldd.<own_name>")` before delegating into `log`. The check is short-circuited on the success path.
- [x] 3.2 Verify `_require_ambient_state` (or whatever the gate is named today) accepts a function-name argument and includes it in the `AmbientContextMissing` message.
- [x] 3.3 Add tests asserting the message names the shorthand actually called: `a2kit.ldd.info`, `a2kit.ldd.warning`, `a2kit.ldd.error`, `a2kit.ldd.debug` — not `a2kit.ldd.log`.

## 4. L — WARN_ONCE on silent docstring / get_type_hints failures

- [x] 4.1 In `src/a2kit/_docstring.py:44`, replace `with contextlib.suppress(Exception):` with an explicit `try/except Exception as exc:` block. On failure, dedupe by `fn.__qualname__` via a module-local `_WARN_ONCE: set[str]` and emit one `logging.warning(...)`. Continue with the documented fallback (empty descriptions). Match the pattern in `src/a2kit/signature.py:32-38`.
- [x] 4.2 In `src/a2kit/tool.py:_augment_annotations_from_docstring` (around line 178), apply the same treatment to the `get_type_hints(fn, include_extras=True)` call. Use a separate module-local `_WARN_ONCE` set scoped to `tool.py` to keep dedupe scopes local.
- [x] 4.3 Add tests covering: a tool with a malformed `Args:` block emits exactly one WARN per `__qualname__` and does not raise; a tool whose annotations raise from `get_type_hints` (e.g. unresolved forward reference) emits exactly one WARN per `__qualname__` and does not raise; decorating the same tool twice in the same process emits exactly one WARN total (dedupe holds).

## 5. Documentation and validation

- [x] 5.1 Update `OPERATIONAL_CONTRACTS.md` Q8 (LDD primitives clause) to state explicitly that "active dispatch" requires both an `ldd_state_for_call` scope and a `ctx`-param declaration on the tool. Name the uniform failure mode across transports.
- [x] 5.2 Run `openspec validate cleanup-round-5-6-code-shape --strict` and resolve any reported issues.
- [x] 5.3 Run the full pytest suite locally; fix any latent breakages surfaced by tightening A.
