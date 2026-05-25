## Why

CLI is today the only transport that's prose-only on errors. MCP carries
a typed envelope (`structuredContent.error`); HTTP carries the same envelope
in the JSON body. The CLI prints `Input error (NotFound): foo` to stderr
and exits with a kind-mapped code. For shell pipelines, CI scripts, and
agent-driving-agent subprocesses, this asymmetry forces consumers to
regex-parse the prose string. The `--json` flag closes the gap.

Carried over from `a2effect-foundation` task 16.3 — deferred while the
typed-error wedge landed across MCP/HTTP. Now picked up.

## What Changes

- **NEW**: `--json` flag on every per-tool CLI subcommand. When set:
  - **Success path**: stdout = JSON-encoded `model_dump()` of the return
    value (compact, one line). Format routing is bypassed (no TSV).
  - **Error path**: stdout = the typed error envelope JSON (same shape as
    the MCP `structuredContent.error` payload). stderr stays empty. Exit
    code is unchanged from prose-mode (kind-mapped per sysexits.h).
- **CONSTRAINT**: `--json` and `--format` are mutually exclusive. Passing
  both raises `BadParameter` ("--json is incompatible with --format=...").
- **NO**: `--json` is NOT added to the meta tools (`list-tools`,
  per-tool `--schema`) — those already have their own `--json` semantics
  (list-tools) or always emit JSON (schema). Scope is per-tool *invocation*.
- **NO**: `--retry` / `--explain` (v1.x follow-ups). This change ships the
  channel only.

## Capabilities

### Modified Capabilities

- `cli-response-encoding`: extend the existing `--json` requirement
  with a mutual-exclusion scenario (`--json` + `--format` raises
  `BadParameter`) — the existing spec defines `--json` semantics but
  doesn't address conflict with `--format`. Otherwise this change is
  pure implementation of the already-locked contract.

## Impact

- **Code**: `src/a2kit/packages/cli/runtime.py` (CliErrorRenderStage
  reads a ContextVar for json-mode and switches output channel);
  `src/a2kit/packages/cli/builder.py` (per-tool callback adds the flag,
  validates mutual exclusion, threads through `invoke_tool_sync`).
- **APIs**: additive (new flag). No breaking changes.
- **Tests**: new BDD suite under `tests/cli/test_json_flag.py`.
- **Docs**: README CLI section gains a worked example showing
  `a2kit <tool> --json | jq` and `--json` exit-code semantics.
