## 1. Engine

- [x] 1.1 `cli/runtime.py`: add `_cli_json_mode: ContextVar[bool] = ContextVar("cli_json_mode", default=False)`.
- [x] 1.2 `CliErrorRenderStage`: read the var; on True emit `{"error": envelope}` JSON to stdout (no traceback) and `typer.Exit(code)`.
- [x] 1.3 Add a `invoke_tool_raw` sibling (or `raw_passthrough: bool` kwarg) that returns the raw value before format_response. Used by the json-mode success path.

## 2. CLI wiring

- [x] 2.1 `cli/builder.py` per-tool callback: declare `--json` Typer Option (bool, default False).
- [x] 2.2 Mutual-exclusion check: if both `--json` and `--format != auto`, raise `typer.BadParameter` naming both flags.
- [x] 2.3 When `--json` is set: set the ContextVar via try/finally (reset on exit) and emit `json.dumps(raw, default=str, separators=(",", ":"))` of the raw return.
- [x] 2.4 Handle the model_dump / list / None / primitive cases per the design doc D4.

## 3. Tests

- [x] 3.1 `tests/cli/test_json_flag.py`: success emits compact JSON to stdout.
- [x] 3.2 Error emits envelope JSON to stdout; stderr silent; kind-mapped exit code.
- [x] 3.3 `--json --format=json` raises BadParameter mentioning both flags.
- [x] 3.4 `--json` doesn't interfere with default-mode invocations (sanity).

## 4. Docs

- [x] 4.1 README CLI section: add a worked example showing `a2kit <subcmd> <tool> --json | jq`.

## 5. Gates

- [x] 5.1 Full test suite green.
- [x] 5.2 Ruff + type check + mirror lint clean.
- [x] 5.3 `openspec validate cli-json-flag` passes.
- [x] 5.4 Archive.
