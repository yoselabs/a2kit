# Tasks — mcp-server-instructions

BDD-first / TDD red → green. Small additive change: prove the field is
absent and untreaded today, then add it and thread it.

## 1. Prove the gap (RED)

- [x] 1.1 Add a test: construct `McpConfig(instructions="Use entity_* for
      memory ops.")` and assert `cfg.instructions == "Use entity_* for
      memory ops."`. Confirm it FAILS today (no such field — pydantic
      either ignores or rejects it). → `test_mcp_config_has_instructions`.
- [x] 1.2 Add a test: build an App whose `config.mcp.instructions` is set,
      call `build_mcp_server(app)`, and assert the returned FastMCP
      server's `instructions` equals that string. Confirm it FAILS today
      (the builder never threads it). → `test_build_threads_instructions`.

## 2. Add the field + thread it (GREEN)

- [x] 2.1 `src/a2kit/config.py`: add `McpConfig.instructions: str | None =
      Field(default=None, description=…)` documenting it as the
      server-level natural-language guidance shown to MCP clients,
      settable via `A2KIT_MCP__INSTRUCTIONS` (env beats code, ADR 0022).
- [x] 2.2 `src/a2kit/packages/mcp/server.py`: at the
      `FastMCP(name=runtime.name, **fastmcp_kwargs)` construction (~`:284`),
      thread `runtime.config.mcp.instructions` into `instructions=` —
      omit/leave `None` when absent, and do NOT override an explicit
      caller-supplied `fastmcp_kwargs["instructions"]` (escape hatch wins).

## 3. Verify (GREEN)

- [x] 3.1 New tests from §1 pass.
- [x] 3.2 Default-None test: an App with no `instructions` set builds a
      server whose instructions behavior is unchanged from today
      (FastMCP default preserved). → `test_default_none_preserves_today`.
- [x] 3.3 Env-override test: `A2KIT_MCP__INSTRUCTIONS=…` beats a code
      default per ADR 0022 (rides the existing runtime-config env chain).
- [x] 3.4 Full suite green, output pristine; lint / `ty check src/` /
      a2kit-static / ruff gates green on the two touched files.

## 4. Close out

- [x] 4.1 Confirm additive/non-breaking: no existing wire shape, field, or
      env var changed; default behavior byte-for-byte preserved.
