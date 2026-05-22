## 1. De-risk the gating override point

- [x] 1.1 Extend the spike harness to confirm `A2kitCodeMode` can filter the sandbox catalog via a `CodeMode` subclass — verify the `get_tool_catalog` override point or fall back to a custom `search_fn` + catalog-filtering `call_tool`. Record the chosen point in `design.md` Open Questions.

## 2. Packaging

- [x] 2.1 Add an `a2kit[code-mode]` optional-dependency extra to `pyproject.toml` pinning `pydantic-monty` to a known-good version; refresh `uv.lock`.
- [x] 2.2 Create the `a2kit.packages.codemode` package — the single import site for `pydantic-monty` and FastMCP's `experimental` `CodeMode`.

## 3. Capability gating (BDD-first)

- [x] 3.1 Write failing tests: `destructive` tools absent from the sandbox catalog by default; present under operator grant; `cli`/`hidden` visibility tools always absent; the `execute` tool exposes no per-call destructive-grant argument.
- [x] 3.2 Implement `A2kitCodeMode(CodeMode)` filtering the catalog by the `meta["a2kit"]` semantic flags (`destructive`, `visibility`).
- [x] 3.3 Implement the operator-side destructive grant — default off; opened by `serve --code-mode-allow-destructive` and the mirrored config field.

## 4. Toggle and build wiring (BDD-first)

- [x] 4.1 Write failing tests: `build_mcp_server(app)` default collapses `list_tools` to `search`/`get_schema`/`execute`; `code_mode=False` lists the full real catalog; real tools stay callable by name under code mode.
- [x] 4.2 Add `code_mode: bool = True` to `build_mcp_server`; install `A2kitCodeMode` after the tool-registration loop when enabled.
- [x] 4.3 Add `--code-mode-off` and `--code-mode-allow-destructive` flags to `serve`; map them onto `build_mcp_server` arguments.

## 5. Connection-scoped DI through the sandbox (BDD-first)

- [x] 5.1 Promote the spike into a permanent real-transport test (`fastmcp.Client`): sandboxed `call_tool` with `connection` runs a connection-scoped, DI-wired tool; a missing `connection` fails with a legible validation error. Run it against `A2kitCodeMode` (the gated subclass), not bare `CodeMode`.

## 6. CLI `code` subcommand (BDD-first)

- [x] 6.1 Write failing tests for the global `code` subcommand: runs source from arg/`--file`/stdin, prints the return value, applies the destructive and visibility gates identically to the MCP surface.
- [x] 6.2 Implement the `code` subcommand in the CLI builder, sharing the sandbox and gate with the MCP `execute` path (no duplicated logic — per AGENTS.md no-redundancy rule).

## 7. Cold-start and lazy-import discipline (BDD-first)

- [x] 7.1 Write a failing test: `import a2kit` imports neither `pydantic_monty` nor FastMCP's `experimental` `CodeMode`.
- [x] 7.2 Write a failing test: code mode enabled without `pydantic-monty` installed raises with a message naming the `a2kit[code-mode]` extra.
- [x] 7.3 Implement the loud-crash missing-dependency guard inside `a2kit.packages.codemode`.

## 8. REST exclusion (forward constraint)

- [x] 8.1 Record the "code execution is never exposed on REST" constraint where the future REST surface change will see it — an `ANTIPATTERNS.md` entry and/or a `BACKLOG.md` note referencing the `code-execution` spec requirement. No REST code exists yet.

## 9. ADR, docs, changelog

- [x] 9.1 Write ADR 0013 — adopt FastMCP `experimental` `CodeMode`, the operator-controlled capability-gating model, default-on catalog-collapse as accepted BREAKING, and the `fastmcp<4` churn watch. Run `make adr-index`.
- [x] 9.2 Add a `CHANGELOG.md` `Unreleased` migration row for the default-on catalog-collapse BREAKING change, naming `--code-mode-off` as the opt-out.
- [x] 9.3 Update `OPERATIONAL_CONTRACTS.md` if transport/dispatch semantics shifted; add a `docs/patterns/` entry for code execution if warranted.

## 10. Verification

- [x] 10.1 `make lint`, `make markdown-lint`, and `make adr-check` all green.
- [x] 10.2 `make test` green, including every new code-mode test.
- [x] 10.3 `openspec validate --changes --strict` green.

## 11. Load-timing contract (BDD-first)

- [x] 11.1 Write a failing test: building the CLI and running a non-`code` command (e.g. `--help`) imports none of `a2kit.packages.codemode`, `fastmcp`, or `pydantic_monty`.
- [x] 11.2 Confirm the eager-MCP / deferred-CLI behaviour holds (current implementation already complies; the `code_cmd` callback imports `run_code` lazily, `build_mcp_server` installs the transform eagerly).
