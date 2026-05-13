# Tasks — align Context method signatures

## 0. Prerequisites

- [x] 0.1 Baseline green: `make lint` + `make test` post
      `field-logging-via-ldd`. Record test count.
- [x] 0.2 Recommend (not strictly required) that
      `rebuild-test-client-on-real-context` lands first — its
      real-transport client surfaces behavioural drift this change
      can't catch with sig-binding alone.
- [x] 0.3 Re-run the signature-drift scan to confirm the 13-method
      inventory hasn't shifted since `field-logging-via-ldd` shipped:
      `uv run python -c "<paste sig_diff.py>"` (per the original
      explore-mode scan). Document any new drifts.

## 1. Treatment 1 — `read_resource` + `elicit`

- [x] 1.1 `read_resource`: narrow stub signature to
      `(uri: str | AnyUrl) -> ResourceResult` (or a duck-typed
      `_StubResourceResult` per D-TREATMENT-1 if upstream type is heavy).
- [x] 1.2 Body wraps file-content `str`/`bytes` in the result type.
      Existing CLI behaviour (file:// only, raise on other schemes)
      preserved.
- [x] 1.3 Test in `test_context.py`: `ctx.read_resource("file:///tmp/x")`
      returns the wrapped result; `.content` matches the file bytes.
- [x] 1.4 `elicit`: narrow stub signature to fastmcp's exact form
      (`response_type: type[T] | list[str] | dict[...] | None`).
- [x] 1.5 Body validates `response_type` against the documented
      overload union upfront; raises `MCPOnlyError` for unsupported
      forms with a pointer at the documented set.
- [x] 1.6 Test in `test_context.py`: existing CLI scenarios (str,
      int, float, bool, list[str]) pass; new dict-form raises
      `MCPOnlyError` cleanly.

## 2. Treatment 2 — signature-mirror-then-raise

- [x] 2.1 `sample(messages, *, system_prompt=None, temperature=None, ...)`
      — copy fastmcp's signature verbatim. Body: single-line raise.
- [x] 2.2 `sample_step(messages, *, system_prompt=None, ...)` — same.
- [x] 2.3 `get_prompt(name, arguments=None)` — narrow to fastmcp's
      `dict[str, Any] | None`. Body: raise.
- [x] 2.4 `list_resources() -> list[SDKResource]` — narrow return
      type. Body: raise.
- [x] 2.5 `list_prompts() -> list[SDKPrompt]` — same.
- [x] 2.6 `list_roots() -> list[Root]` — same.
- [x] 2.7 `send_notification(notification)` — narrow argument to
      `mcp.types.ServerNotificationType`. Body: raise.
- [x] 2.8 Add `test_stub_signature_matches_fastmcp` parametrized
      over these 7 methods + the Treatment-1 methods. Asserts
      `inspect.signature(StderrToolContext.<m>) ==
      inspect.signature(fastmcp.Context.<m>)`.

## 3. Treatment 3 — delete `send_log_message`

- [x] 3.1 Grep `src/` `tests/` `examples/` for any
      `ctx.send_log_message`. Confirm zero call sites.
- [x] 3.2 Delete the method from `StderrToolContext`.
- [x] 3.3 Update `MCP_ONLY` allowlist in `test_context_surface.py` if
      needed (it currently isn't; the method was stub-only, so it's
      not in the upstream `dir(Context)`).
- [x] 3.4 ANTIPATTERNS.md entry per design D-TREATMENT-3.

## 4. Treatment 4 — pin `log` in `CTX_CALL_SHAPES`

- [x] 4.1 Add `("log", ("msg",), {"level": "info"})` and
      `("log", ("msg",), {"level": "warning", "extra": {"k": 1}})`
      to `CTX_CALL_SHAPES`.
- [x] 4.2 Run `test_ctx_call_shapes_bind_against_both_contexts`;
      should pass without code changes.

## 5. Signature-test registry — full extension

- [x] 5.1 Extend `CTX_CALL_SHAPES` per D-SIGTEST-REGISTRY:
      `read_resource` (2 forms), `elicit` (2 forms), `get_prompt`,
      `list_resources`, `list_prompts`, `list_roots`, `sample`,
      `sample_step`. Skip `send_notification` per D-SIGTEST-REGISTRY
      / Open Question 3.
- [x] 5.2 Test passes against both impls.

## 6. Spec edits

- [x] 6.1 `openspec/changes/align-context-method-signatures/specs/mcp-context-passthrough/spec.md`
      — modify the existing "CLI stub supplies a fastmcp.Context-shaped
      stub" requirement to add the new clause: "every public method's
      runtime signature SHALL match `inspect.signature` of its
      `fastmcp.Context` counterpart exactly (modulo `self`)."
- [x] 6.2 Add scenarios for `read_resource` returning `ResourceResult`,
      `elicit` raising for unsupported `response_type` forms.
- [x] 6.3 Remove the `send_log_message` scenario from the existing
      spec (Treatment 3 deletion).

## 7. Documentation

- [x] 7.1 ANTIPATTERNS.md: "Don't call `ctx.send_log_message`"
      entry per D-TREATMENT-3.
- [x] 7.2 If `rebuild-test-client-on-real-context` landed, no extra
      docs needed; sig-test registry is the discoverable contract.
      If it didn't land, add a note in README pointing at the
      sig-test registry as the source of truth.

## 8. Verification

- [x] 8.1 `make lint` green.
- [x] 8.2 `make test` green; new sig-match tests pass.
- [x] 8.3 The `field-logging-via-ldd` repro
      (`tests/test_field_logging_mcp_path.py`) still passes —
      regression check.
- [x] 8.4 Manual: run `examples/sampling`, `examples/elicitation`
      through CLI + MCP; verify behavioural parity for the narrowed
      methods.

## 9. Out-of-scope follow-ups

- [x] 9.1 Filed separately: tighten `log`'s `level` parameter to
      `LoggingLevel` literal on the stub. Cosmetic; low priority.
- [x] 9.2 Filed separately: add a CI job that pins fastmcp version
      and fails when its Context signatures change, alerting us to
      re-sync the stub. Today this is implicit (sig-test fails on
      upgrade); making it an explicit pin step shortens the loop.
