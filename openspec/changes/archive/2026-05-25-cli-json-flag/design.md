## Context

The typed-error wedge made CLI errors carry the same envelope as MCP/HTTP
in principle, but rendering on the CLI surfaces stayed prose-on-stderr.
That asymmetry forces machine consumers (jq pipelines, CI scripts,
subprocess.run callers, agent-driving-agent subprocesses) to regex-parse
the prose. `--json` switches the CLI to a machine-readable end-to-end
mode without changing the typed-error contract.

## Goals / Non-Goals

**Goals:**
- Add `--json` to per-tool CLI subcommands.
- Success: emit `json.dumps(model_dump())` to stdout, one line.
- Error: emit the typed envelope JSON to stdout, exit kind-mapped code.
- Mutually exclusive with `--format` — clear error if both passed.

**Non-Goals:**
- Changing default CLI behaviour (prose stays the default).
- Adding `--json` to meta tools (`list-tools`, per-tool `--schema`) —
  they already have machine-readable shapes.
- `--retry` / `--explain` — separate v1.x follow-ups.
- Implementing `--json` on `serve` / `run` / `code` subcommands —
  per-tool invocation only.

## Decisions

### D1. ContextVar plumbing for the json-mode flag

Per-invocation flag, not per-build. Use a `ContextVar[bool]` set by the
per-tool callback before `invoke_tool_sync` is called. `CliErrorRenderStage`
reads the var at error time and branches:
- `True`: emit envelope JSON to stdout via `typer.echo`, no traceback.
- `False`: today's behavior — prose to stderr, traceback to stderr under
  debug.

Alternative considered: thread `json_mode: bool` as an explicit kwarg
through `invoke_tool_sync` → spec → stage. Rejected — the spec already
has many transport-neutral fields; per-call flags like this don't belong
on it. ContextVar matches the existing pattern (e.g.,
`TypedErrorEnvelopeMiddleware` uses one for the envelope slot).

### D2. Bypass format-routing on success when --json

The format-routing layer is for human/LLM-facing compression (TSV/page-tsv).
`--json` is the machine channel; it should produce raw `model_dump()`
JSON regardless of plan. Implementation: when `--json` is set, the per-tool
callback skips `format_response(...)` and emits `_json.dumps(raw, default=str)`
directly. `raw` is the tool's return value (after dispatch pipeline),
not the post-format-routing string.

This requires returning the *raw* value from `invoke_tool_sync` when
`--json` is set, OR doing the format inside the callback. Cleanest:
add a `raw_passthrough: bool` parameter to `invoke_tool_sync` (or a
sibling function) that returns the raw value. Pick the sibling-function
path to keep `invoke_tool_sync`'s string-return contract pure.

### D3. Mutual exclusion with --format

If both `--json` and `--format=<x>` (anything except the implicit
`auto`) are passed, raise `typer.BadParameter`. Reason: the two flags
encode incompatible intents. `--format=json` (today) compresses through
the formatter pipeline and ends as JSON; `--json` (new) bypasses the
pipeline entirely and emits raw `model_dump()` JSON plus changes error
rendering. Having both would be ambiguous.

### D4. Success-side JSON shape — `model_dump()` of the raw return

For Pydantic models: `model.model_dump()`.
For lists of models: `[m.model_dump() for m in items]`.
For primitives (str/int/etc): the value itself.
For `None`: literal `null`.
For dict: pass through.

Serialized via `json.dumps(..., default=str, separators=(",", ":"))` —
compact, one-line, machine-friendly. Mirrors the MCP wire's compact form.

### D5. Error-side JSON shape — the AppError envelope

Reuse `app_error.to_envelope_dict()` (already used by HTTP + MCP paths).
The CLI renderer wraps it in `{"error": envelope}` to match the MCP
`structuredContent` shape, so consumers can parse identically across
transports:

```json
{"error": {"type":"NotFound","kind":"input","retryable":false,"hint":"...","details":{},"envelope_version":1}}
```

Exit code unchanged: per-class `cli_exit_code` ClassVar wins; otherwise
the base-kind default per sysexits.h.

### D6. Don't auto-detect (no `isatty`-based switching)

Some CLIs auto-emit JSON when stdout is piped. Tempting but error-prone:
test runners pipe stdout; users sometimes want prose under pipes. Keep
behavior explicit; `--json` is opt-in.

## Risks / Trade-offs

- **Risk**: Tools that return non-serializable objects (e.g., a custom
  class without `model_dump`) crash under `--json`.
  **Mitigation**: `default=str` in `json.dumps` is a permissive fallback.
  Tools returning non-Pydantic objects already round-trip through
  `format_response` on the default path; `--json` mirrors that with a
  simpler shape.

- **Risk**: ContextVar leakage if the var isn't reset between invocations.
  **Mitigation**: Use `var.set(True)` + `var.reset(token)` in a try/finally
  around `invoke_tool_sync`. Per-call scope; cannot leak.

- **Risk**: Format mutual-exclusion is surprising for users who scripted
  `--format=json` previously.
  **Mitigation**: `--format=json` keeps working (success-only-JSON via the
  formatter); `--json` is the new end-to-end flag. The BadParameter
  message names both flags.

## Migration Plan

1. Add ContextVar to `cli/runtime.py`.
2. Branch in `CliErrorRenderStage` based on the var.
3. Add a `raw_passthrough` sibling (or kwarg) to `invoke_tool_sync` for
   the success path.
4. Per-tool callback in `cli/builder.py`: declare `--json` Typer Option,
   validate mutual exclusion, set the ContextVar (with try/finally to
   reset), emit JSON on success.
5. BDD suite — success, error, mutual exclusion, ctx propagation.
6. README CLI section gains the worked example.

## Open Questions

None.
