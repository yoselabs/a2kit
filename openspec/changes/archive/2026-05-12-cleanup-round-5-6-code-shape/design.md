## Context

Five round-5/6 changes shipped over the last sprint sealed the LDD ambient-context contract, the in-process TestClient, async-singleton factories, and the docstring-driven Param pull. Post-shipping review found four small code-shape issues that are too local to deserve their own change but matter enough to bundle: a three-way transport inconsistency on LDD binding, three SLF001 leaks in `TestClient.override`, a wrong function-name in `AmbientContextMissing` from LDD shorthands, and two silent `contextlib.suppress(Exception)` swallows in the docstring pull.

All four are clean-ups against contracts that round 5/6 already framed, not new behaviour.

## Goals / Non-Goals

**Goals:**

- Make `await ldd.event(...)` from a no-ctx tool behave uniformly across MCP / CLI / TestClient — raising `AmbientContextMissing` on all three rather than working silently on two and raising on one.
- Move the three-attribute "swap a DI binding" mutation from `TestClient.override` (which reaches into Container privates) into `Container._override`, owned by the container.
- Make `await a2kit.ldd.info(...)` outside a dispatch report `"a2kit.ldd.info called outside an active tool dispatch"` instead of `"a2kit.ldd.log ..."`.
- Replace silent `contextlib.suppress(Exception)` in the docstring pull with one warn-once-per-qualname log so a malformed docstring or forward-reference issue surfaces in stderr instead of silently dropping descriptions.

**Non-Goals:**

- Re-shaping the LDD ambient-context contract itself (rounds 5/6 settled it).
- Touching the Container's public surface — `_override` is a single-underscore test-seam, same convention as `_snapshot`/`_restore`.
- Migrating round-5 examples or example projects (they already declare `ctx`).
- Adding new logging knobs or a configurable warn-or-raise mode for L.

## Decisions

### A. Tighten CLI / TestClient, do not loosen MCP

The MCP behaviour is the correct one — fail loud when a tool calls LDD primitives but didn't declare `ctx`. The alternative (synthesize a default ctx on every transport so it never raises) was considered and rejected: it hides the bug that the tool author forgot the `ctx` parameter, conflicts with the "fail-loud" framing the round-5 proposal sealed, and breaks the documented contract `OPERATIONAL_CONTRACTS.md` Q8 already states. Tightening matches the spec rather than rewriting it.

Concretely:

- CLI runtime (`src/a2kit/packages/cli/runtime.py:48-50`) drops the `if ctx_param_name and ctx_param_name not in call_kwargs: call_kwargs[ctx_param_name] = StderrToolContext()` synthesis branch and passes `ctx=None` to `ldd_state_for_call` (or skips the scope entirely) when `ctx_param_name` is falsy.
- TestClient (`src/a2kit/packages/testing/client.py:218-228`) likewise gates the `_CapturingContext` binding on `meta.context_param_name`.
- Both transports continue to bind ctx when the tool declared one — that path is unchanged.

### B. Container._override owns the three-attribute mutation

A single `_override(self, type_, instance)` method on `Container` replaces the three `# noqa: SLF001` lines in `TestClient.override`. The method:

1. Sets `_providers[type_] = lambda: instance` (a constant factory).
2. Sets `_singletons[type_] = instance`.
3. Calls `_async_factories.discard(type_)` to clear any async-factory marker that would block sync `resolve`.

This is feature-agnostic (same constraint the spec already places on `_snapshot`/`_restore`) and underscore-prefixed (same "test-only, not part of public surface" signalling). The existing di-container-package spec's clause "override semantics are implemented entirely by mutating `_providers` and `_singletons`" is amended to acknowledge the third attribute (`_async_factories`).

### F. Each shorthand identifies itself

The four shorthand functions (`debug`, `info`, `warning`, `error`) each call `_require_ambient_state("a2kit.ldd.<own_name>")` before delegating into `log`. The check happens once per call and only when the ambient state is `None` (the common path is unchanged). The exception message becomes accurate for the function the user actually called.

### L. WARN_ONCE pattern, qualname-deduped

The two `contextlib.suppress(Exception)` swallows are replaced with a `try/except` that logs at WARN level (once per `fn.__qualname__`) and continues with the same fallback as today (empty descriptions / no augmentation). Reuse the exact pattern from `src/a2kit/signature.py:32-38`:

```python
except Exception as exc:
    name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
    if name not in _WARN_ONCE:
        _WARN_ONCE.add(name)
        _log.warning("...failed for %s: %s", name, exc)
```

Each module gets its own `_WARN_ONCE: set[str]` to keep dedupe scopes local; cross-module noise is not a real concern at decoration-time.

The semantic outcome — decoration never raises, malformed docstring degrades to no description — is unchanged. Only the silence is replaced with a single observable line per offender.

## Risks / Trade-offs

- **Tightening A may surface latent test fixtures.** Tools that call LDD primitives without declaring `ctx` worked on CLI / TestClient but will now raise. Mitigation: in-repo examples already declare `ctx`; the test-suite will catch any stragglers and the fix is one-line (add `ctx: ToolContext` to the tool signature, or call from `null_context()` if it was a unit-style test). The breakage surfaces a real bug — the tool author forgot the contract.
- **L could noise up logs for libraries that intentionally have malformed docstrings.** Mitigation: WARN_ONCE per qualname caps each offender at one line per process lifetime; users who don't want any docstring pull at all can use explicit `Annotated[T, Param(description=...)]` and the parser short-circuits on the empty-descriptions early return.
- **F's per-shorthand check adds one dict lookup on the success path.** Negligible; the existing `_require_ambient_state` is already on the hot path inside `log` and we'd be moving (not duplicating) the failure-message resolution.

## Migration Plan

Single PR, no flag. Round 5/6 are already archived and shipped; this is a follow-up clean-up against their specs.

Roll back by reverting the PR — none of the four sub-changes touches a persisted artifact or wire format.

## Open Questions

None. The four items are mechanical given the decisions above.
