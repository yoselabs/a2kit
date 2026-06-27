# Design — add-code-mode-config-default

## Decision 1: tri-state at the function boundary (`bool | None`)

`build_mcp_server`'s `code_mode` becomes `bool | None = None`. `None` is the
"unspecified — consult config" sentinel; an explicit `True`/`False` wins. This
is the exact shape already used for the *escape-hatch* pattern elsewhere in the
function (`instructions` config field vs explicit `instructions=` kwarg), and it
keeps the resolution in one place:

```python
runtime = build(app)
effective_code_mode = (
    code_mode if code_mode is not None else bool(runtime.config.mcp.code_mode)
)
```

`effective_code_mode` then drives the two existing call sites verbatim:
`FormatRoutingMiddleware(consumer="code" if effective_code_mode else "llm", …)`
and `if effective_code_mode: server.add_transform(…)`.

Alternative considered: read config *only* (drop the param, like
`structured_output`). Rejected — `run_code` and a large body of tests pass
`code_mode=` explicitly, and the `a2kit code` subcommand needs a hard `True`
that config cannot override. Keeping the param, with `None` meaning "consult
config," serves both.

## Decision 2: absolute flag pair, not a relative invert toggle

The CLI override is `--code-mode / --no-code-mode` (`Optional[bool] = None`),
**not** a single toggle that inverts the configured default.

```
MODEL A — absolute pair (CHOSEN)        MODEL B — invert toggle (rejected)
  --code-mode    → force ON               --code-mode-off → flips author default
  --no-code-mode → force OFF              no flag         → author default
  no flag        → config → True
  ✓ same flag = same effect everywhere   ✗ same flag = opposite effect per server
  ✓ can force ON a config-off server     ✗ "off" toggle can't force ON
```

The invert model's relativity is a footgun: an operator who learns
"`--code-mode-off` turns it off" is surprised when it turns code mode *on*
against a server whose author already defaulted it off. Absolute flags are the
conventional Typer tri-state and compose predictably across a fleet.

## Decision 3: remove `--code-mode-off`, do not alias it

Per AGENTS.md §1 (no graceful backward-compat shims), the old spelling is
deleted, not kept as a hidden alias for `--no-code-mode`. This is safe because
the only live consumer is a2web, on another machine, and post-change a2web
drops the flag from its mounts entirely in favor of `code_mode=False` in config
— landing the removal on zero live callers.

## Resolution order (single source of truth)

```
explicit --code-mode / --no-code-mode      (operator, per-invocation)
   ▼ if neither flag given
runtime.config.mcp.code_mode               (author; env A2KIT_MCP__CODE_MODE > code)
   ▼ field default
True                                       (framework default — unchanged)
```

`run_code` ("`a2kit code`") sits outside this chain: it always passes
`code_mode=True` explicitly, so it wins at the top regardless of config.
