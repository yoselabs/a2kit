## 1. BDD specs (write tests first)

- [ ] 1.1 `tests/capabilities/error_envelope_rendering/test_rendered_state_not_on_exception.py` — after the dispatch pipeline runs, the raised `AppError` instance has NO `rendered_prose` or `rendered_envelope_dict` attribute (the side channel carries them, not the exception).
- [ ] 1.2 `tests/capabilities/error_envelope_rendering/test_rendered_state_present_for_readers.py` — `McpErrorRenderStage` and `CliErrorRenderStage` retrieve a `RenderedError` via `get_rendered_error(exc)` after `ErrorEnvelopeStage` ran. Assert: returned `RenderedError` matches the prose and envelope that `format_error_prose` / `to_envelope_dict()` produced.
- [ ] 1.3 `tests/capabilities/error_envelope_rendering/test_missing_render_state_raises.py` — if a transport render stage is wired without `ErrorEnvelopeStage` upstream, calling the render stage with an `AppError` produces a precise `RuntimeError` naming the missing precondition (no silent `str(exc)` fallback in this test mode).
- [ ] 1.4 `tests/capabilities/error_envelope_rendering/test_side_channel_isolated_per_call.py` — two concurrent calls each raising `AppError` get distinct `RenderedError` rows in the side channel; one call's render state never leaks to the other.
- [ ] 1.5 `tests/capabilities/error_envelope_rendering/test_side_channel_cleared_on_scope_exit.py` — after `call_scope` exits, the side channel for that call is empty (no leak across calls within one process).
- [ ] 1.6 `tests/capabilities/error_envelope_rendering/test_ty_no_ignore_in_envelope.py` — `grep` test asserting `packages/dispatch/envelope.py` contains zero `ty: ignore[unresolved-attribute]` comments.

## 2. The render-state side channel

- [ ] 2.1 New private module `src/a2kit/packages/dispatch/_render_state.py`:
  - Frozen dataclass `RenderedError(prose: str, envelope: dict[str, Any])`.
  - Module-private `_render_state: ContextVar[dict[int, RenderedError] | None]`.
  - `open_render_state() -> Token` / `close_render_state(token)` opened/closed by `Container.call_scope` (or by the dispatch pipeline entry, design.md decides).
  - `set_rendered_error(exc: BaseException, rendered: RenderedError) -> None` — writes by `id(exc)`.
  - `get_rendered_error(exc: BaseException) -> RenderedError | None` — reads by `id(exc)`.
- [ ] 2.2 Wire `open_render_state` / `close_render_state` into the dispatch pipeline so the slot exists for every dispatched call.

## 3. Writer migration

- [ ] 3.1 In `packages/dispatch/envelope.py:99-100`, replace the two attribute assignments with `set_rendered_error(exc, RenderedError(prose=format_error_prose(exc), envelope=exc.to_envelope_dict()))`.
- [ ] 3.2 Delete the two `# ty: ignore[unresolved-attribute]` comments.
- [ ] 3.3 Update the module docstring to point at the new side channel.

## 4. Reader migration

- [ ] 4.1 In `packages/mcp/_wrappers.py:129-130`, replace `getattr(exc, "rendered_prose", None) or str(exc)` with explicit `RenderedError` lookup: `rendered = get_rendered_error(exc); prose = rendered.prose if rendered else str(exc); envelope = rendered.envelope if rendered else exc.to_envelope_dict()`. The `else` branches are defensive fallbacks for non-`AppError` exceptions slipping through the pipeline; document this inline.
- [ ] 4.2 In `packages/cli/runtime.py:84`, same migration.

## 5. Middleware bridge consolidation

- [ ] 5.1 Audit `packages/mcp/_wrappers.py:35` (`_pending_typed_envelope` ContextVar) — does it become redundant once `get_rendered_error(exc)` works inside the FastMCP middleware? If yes, retire it in this change (preferred — collapses two bridges into one). If no, document why in design.md and keep it (then file a follow-up).

## 6. Docs

- [ ] 6.1 Update the `error-envelope-rendering` capability spec inline (see `specs/` in this change).
- [ ] 6.2 ANTIPATTERNS.md — add an entry "Don't mutate exception instances to carry rendering state. Use the explicit side channel in `_render_state.py`."
- [ ] 6.3 `CHANGELOG.md` `[Unreleased]` — short entry; flag no public API change.
- [ ] 6.4 BACKLOG: add an entry "Investigate CLI builder callback attribute attachment for side-channel migration. Triggered by the 2026-05-26 audit: `packages/cli/builder.py:333,337` attaches `callback.__signature__` and `callback._a2kit_short_help` as untyped attributes (two `# ty: ignore[unresolved-attribute]` comments). Same shape as the envelope-mutation antipattern this change fixed. Trigger to pick up: after this change lands and we have lived experience with the `_render_state.py` pattern. Decide whether the CLI builder uses the same side-channel or a callable-attribute Protocol typing fix."

## 7. Verification

- [ ] 7.1 `make test` green.
- [ ] 7.2 `grep -rn "rendered_prose\|rendered_envelope_dict" src/a2kit/` returns matches ONLY in `_render_state.py` (the canonical home).
- [ ] 7.3 `grep -rn "ty: ignore\[unresolved-attribute\]" src/a2kit/packages/dispatch/envelope.py` returns nothing.
- [ ] 7.4 An MCP tool body raising `InvalidInput("x")` produces the same wire envelope shape and prose as before this change (no consumer-visible behaviour change).
- [ ] 7.5 A CLI tool raising the same error produces the same stderr output and exit code as before this change.
