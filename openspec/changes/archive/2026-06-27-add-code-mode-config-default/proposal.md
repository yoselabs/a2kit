# add-code-mode-config-default

## Why

`code_mode` is a per-server-**shape** decision — the same category as
`McpConfig.instructions` and `McpConfig.structured_output`, which already live
on that model. Yet `code_mode` has no config seam: it is frozen at
`build_mcp_server(..., code_mode=True)` (`packages/mcp/server.py`) and movable
**only** per-invocation via the one-directional `serve --code-mode-off` CLI flag
(`packages/cli/_serve.py`). An App cannot declare its own default.

The global default (ON) is correct for many-tool / big-payload servers (a2db,
a2atlassian) where the sandbox earns its keep: progressive schema disclosure
across dozens of tools, and large intermediate payloads kept out of the calling
model's context. It is the **wrong** default for a2web's shape — three tools
(`ask` / `fetch_raw` / `refresh`), tiny schemas, payloads already distilled
server-side into lean envelopes. There the sandbox is pure tax on the ~95%
single-`ask` path: an extra `search` / `get_schema` round-trip plus sandbox
conventions the caller must get right.

Because there is no config field, a2web's only ways to change its own default
are a forgettable per-client `args` flag repeated in every `~/.claude.json`
mount, or argv-munging before `a2kit.run(app)`. Neither is a *declared* default
— the decision wants to live with the App, beside the other `McpConfig` shape
knobs. Captured from a2web feedback round 14 (`A2KIT_FEEDBACK_v0.44.md`).

## What Changes

### 1. `McpConfig.code_mode: bool = True` (the config seam)

Add `code_mode` to `McpConfig`, mirroring `structured_output` /
`instructions`: a consumer-owned shape knob, env-settable as
`A2KIT_MCP__CODE_MODE`, env-beats-code per ADR 0022. The framework default
stays `True`, so a2db / a2atlassian are untouched; a2web declares
`code_mode=False` once and becomes the documented outlier.

### 2. `build_mcp_server(code_mode: bool | None = None)` resolves from config

The `code_mode` parameter becomes tri-state. `None` (the new default) means
"consult `runtime.config.mcp.code_mode`"; an explicit `True`/`False` wins. This
mirrors how `structured_output` is already read from `runtime.config.mcp` inside
the function. The resolved value drives both the `FormatRoutingMiddleware`
consumer regime and the code-mode transform install.

### 3. The serve CLI gains a bidirectional override pair

Replace the one-directional `--code-mode-off` boolean with an
`Optional[bool]` `--code-mode / --no-code-mode` pair (Typer default `None`).
`--code-mode` forces ON, `--no-code-mode` forces OFF, neither falls through to
config then the built-in default. A flag means the same thing on every server
(absolute, not relative to config), and an operator can force-on a
config-off server to debug — capabilities the old `--code-mode-off` lacked.

Resolution order, end to end:

```
CLI flag (explicit --code-mode/--no-code-mode)
  > McpConfig.code_mode   (env A2KIT_MCP__CODE_MODE > code)
  > built-in default True
```

### Non-goals

- `code_mode_allow_destructive` stays CLI/operator-only (security-sensitive);
  this change does not move it to config.
- The `a2kit code` subcommand (`run_code`) stays hard `code_mode=True` —
  invoking the sandbox is the explicit point of that command; config must not
  disable the thing the operator just typed.

## Impact

- **Specs:** `runtime-config` (new `McpConfig.code_mode` requirement),
  `code-execution` (modify the default-on + toggle requirements).
- **Code:** `config.py` (field), `packages/mcp/server.py` (tri-state resolve),
  `packages/cli/_serve.py` (flag rename).
- **Breaking:** the `--code-mode-off` flag spelling is **removed** (replaced by
  `--no-code-mode`), per AGENTS.md §1 no-graceful-shims. Safe: the sole live
  consumer (a2web) drops the flag entirely and uses `code_mode=False` in config.
- **Back-compat for the default path:** no config set + no flag = today's
  behavior (`True`). Additive at the config layer.
