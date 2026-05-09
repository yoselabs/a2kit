## Context

The v1.0 thin-core refactor (`simplify-and-thin-core`) shipped a structurally
clean codebase: 9 top-level files, 486 core LOC, 8 plugin packages, 229 tests
passing, cold-start under 100 ms. But the refactor was time-pressured —
written by 8 subagents working in parallel + 2 sequential adapter agents +
integration glue. Each subagent reported 1-3 known blockers in their
hand-off notes; the orchestrator triaged "ship blockers" vs "Phase N+1"
during integration. This change closes the Phase N+1 list before the
v1.0.0 tag goes out.

**Current debt inventory** (sources: subagent reports + post-merge audit):

- **Coupling**: `_APP_CTX` lives in `packages/mcp/cli` (the only fastmcp-bound
  module); `packages/cli/builder.py` lazy-imports it. The asymmetry is
  awkward — cli owns the runtime but mcp owns the context. Same shape
  applies to `compute_schema` (testing owns it, cli imports it).
- **Coverage**: aggregate 77 %. Concentrated in two files: `lint/static.py`
  (69 %, 987 SLOC) and `mcp/listview.py` (36 %). The latter is more
  worrying — middleware result-rewriting is the kind of code that fails
  silently against malformed payloads.
- **Stub code**: A2K010 (legacy `--select` unknown-atom rule) has a
  no-op stub that always returns `None`. Dead code; either retire the
  rule code entirely or port it to CEL atom validation.
- **Test layout asymmetry**: `tests/packages/select/` lacks `__init__.py`
  to dodge stdlib `select` shadowing. Other plugin tests have one.
- **CLI option synthesis**: `Optional[T]` and `T | None` for primitive `T`
  fall through to JSON-decode mode (the "complex" branch). Counter-intuitive
  for the most common nullable-primitive case.
- **Tracker example**: module-level mutable slot (`_impl: Callable | None`)
  with `set_get_conn(...)` from the composition root. Works, but reads as
  legacy ergonomics that v1.0 supposedly cleaned up.
- **Spec drift**: design.md TL;DR cited 9 `__init__.py` files; actual is 10
  (because `lint` was promoted from a subpackage of core into a plugin
  package, adding one). Spec verification 7.4 says ≤ 9. Need either a
  spec amendment or one fewer `__init__.py`.
- **ty type-correctness**: 29-33 errors when the user requested ty as
  a hard CI gate. Currently being fixed by a parallel agent.
- **OTel + LDD**: user-requested follow-ups in flight (parallel agent).
  Folding into this change so review is consolidated.

## Goals / Non-Goals

### Goals

- `uv run ty check src/` exits 0 — type correctness is a hard `make lint`
  gate alongside ruff and `a2kit lint static`.
- Aggregate test coverage ≥ 95 %; reinstate `--cov-fail-under=95` in
  `pyproject.toml`.
- Cross-package coupling reads in one direction: cli imports from mcp at
  the lazy-load boundary, mcp doesn't reach back into cli.
- All examples reflect best-practice ergonomics — no module-level mutable
  slots, no "wire after construction" ceremony.
- Opt-in OTel adapter exists so production users get observability without
  forcing OTel into every install's deps.
- An LDD example exists and is referenced from the README so authors learn
  the streaming-logger pattern from copy-paste-modify.

### Non-Goals

- v0.x compat shims. v1.0 is a clean break (per `simplify-and-thin-core`
  spec). Any "rename" or "relocation" in this change is a clean move with
  no re-exports.
- Adding new core surface. The 9-file core is locked; additions land in
  plugin packages.
- PyPI publish or distribution mechanics. v1.0 stays GitHub-install per
  user direction.
- Performance optimization. Cold-start budgets are met (21.5 / 86 / 340 ms
  vs 100 / 300 / 500 targets); no need to chase further headroom.
- Coverage above 95 %. The spec target is "≥ 95 % (100 % nice-to-have)";
  push for 95 % cleanly, don't game numbers for the last 5 %.

## Decisions

### D-CTX-NEUTRAL: `_APP_CTX` moves to `packages/cli/app_ctx`

A neutral, fastmcp-free location. Both adapters (cli builder + mcp serve
command) import from there. Symmetry reads cleanly: "the CLI package owns
the active-app contextvar; both serve and tool subcommands consume it."

### D-SCHEMA-IN-CLI: `compute_schema` moves to `packages/cli/schemas`

The function is genuinely a CLI concern (it's invoked by `--schema` and
the `schema` subcommand). Testing snapshots reuse it via direct import,
matching the existing read direction from `packages/testing/snapshots`.

Mitigation for circularity: `packages/cli/schemas` must not import from
`packages/testing/`. The dependency stays one-way.

### D-LINT-SPLIT: `packages/lint/static.py` → `packages/lint/rules/`

Currently 987 SLOC; triggers A2K014 against itself. Split by rule family:

```
packages/lint/
├── __init__.py
├── static.py             ← public run_static + dispatch table only (~150 LOC)
├── runtime.py
├── cli.py
└── rules/
    ├── __init__.py
    ├── di.py             ← A2K-DI-* family
    ├── conn.py           ← A2K-CONN-LIST-PLACEHOLDER + connection-shape rules
    ├── importing.py      ← A2K-IMPORT-DISCIPLINE
    ├── shape.py          ← A2K002, A2K003, A2K011, A2K013 (return / docstring)
    ├── budget.py         ← A2K014 file-size budget
    └── select.py         ← A2K010 stub removal note
```

Module-layout-discipline gets a delta: `packages/lint/rules/` is allowed.
`__init__.py` count rises by 1 (to 11) — spec scenario 7.4 amends to
"target: 2 boundary + N=8 plugins + lint rules subdir = 11".

A2K010 retires entirely. Lint rule code removed; CHANGELOG notes it.

### D-TY-GATE: ty as hard gate, with a `[tool.ty.rules]` allowlist

`uv run ty check src/` runs in `make lint`. Configuration in
`pyproject.toml [tool.ty.rules]` lowers severity ONLY for patterns that
require third-party stubs to fix (e.g. `functools.wraps` returning
`_Wrapped` without `__signature__` exposed). Each lowered rule has a
`# why:` rationale comment. No globally disabled rules.

### D-OTEL-OPTIONAL: `a2kit.packages.otel` opt-in

OTel deps under `[project.optional-dependencies] otel = [...]`.
`pip install 'a2kit[otel]'` enables. `import a2kit.packages.otel` lazy-
imports `opentelemetry-api` inside `install()`; missing deps raise an
informative `ImportError` pointing at the install command.

Span attributes pulled from `A2KitMeta`:

- `a2kit.tool_name`
- `a2kit.verb`
- `a2kit.router`
- `a2kit.tags` (sorted, comma-joined)

Span name: `mcp.tool.{tool_name}`. Status: OK on success, ERROR with
`record_exception(exc)` on failure.

Optional metric: counter `a2kit.tool.calls{tool, verb, status}`. Off
by default; user calls `install(server, metrics=True)` to enable.

### D-LDD-EXAMPLE: `examples/streaming_logger/`

Demonstrates Logging-Driven Development. Tools emit `ctx.info()` /
`ctx.warning()` / `await ctx.report_progress()` during execution. Same
code yields:

- MCP wire: protocol notifications via `fastmcp.Context`.
- CLI: stderr lines `[INFO] msg key=value`, line-buffered for real-time
  feel.

Three tools in the example router:

1. `import_csv(file, batch_size)` — batched progress + per-batch info.
2. `long_running(retries)` — `ctx.warning` on retryable errors,
   `ctx.error` then raise on give-up.
3. `quick_status()` — no logging; contrasts with the streamers.

README sketches when to use LDD: long-running operations (>1s),
batched work, retry loops, multi-step orchestrations. Discourage it
for sub-second tools.

### D-OPTIONAL-T: CLI Click option synthesis handles nullable primitives

Map `Optional[int]` / `int | None` / `Union[int, None]` to
`click.IntType()` (or analog) with `default=None`, `required=False`.
Same for `Optional[float]`, `Optional[str]`, `Optional[bool]`. Any
other nullable type still falls to JSON-decode mode.

Implementation: `_click_type_for(annotation)` strips `None` from a
`Union` / `|` type before checking primitive membership.

### D-TRACKER-WIRE: replace tracker `_impl` slot with `app.use_factory`

Add to `a2kit.App`:

```python
def use_factory(self, factory: Callable[..., Awaitable[Any]], *, as_: Callable[..., Awaitable[Any]]) -> "App":
    """Bind a factory under a stable callable identity. Tools that declare
    `Depends(as_)` will resolve through the bound factory."""
```

Replaces module-level mutable slot:

```python
# Before (deps.py):
_impl: Callable | None = None
async def get_conn(*, connection: str): ...
def set_get_conn(fn): global _impl; _impl = fn

# After (deps.py — shrinks to a stub identity for Depends):
async def get_conn(*, connection: str) -> TrackerConn: ...

# After (server.py):
app = a2kit.App("tracker")
app.connect(TrackerConn)
app.use_factory(get_conn_factory(app, TrackerConn), as_=get_conn)
app.use(ProjectsRouter())
```

Mechanism: `App.use_factory` registers `(as_, factory)` in an internal
`_factories` dict. The MCP and CLI adapters apply
`uncalled_for.resolve_dependencies(...)` with that dict so any
`Depends(as_)` resolves through the bound `factory`.

This is a small new core surface (~15 LOC in `app.py`). Spec impact:
`thin-core-surface` "Single-entry `a2kit.run(app)`" requirement gains
a sub-scenario for factory binding.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| Splitting `lint/static.py` causes test regressions if dispatch order changes | Keep `run_static` API stable; rules dispatch in declared order via an explicit `RULES` tuple in `static.py`. Tests run on the package, not on internal module structure. |
| Coverage uplift to 95 % might require unrealistic mocking for `mcp/listview.py` middleware paths | Use `await server._mcp_call_tool(...)` against an in-process FastMCP server with structured-content tools; the middleware fires naturally. If unrealistic, lower the per-file aspiration with a comment, not the global threshold. |
| `App.use_factory` widens the core surface | Limit to ~15 LOC; one method, one private dict. Scoped against the v1.0 "thin core" budget (still well under the 12-file / 2000-LOC cap). |
| Moving `compute_schema` shifts an import path that subagent reports already documented | Compatibility re-export from `packages/testing/snapshots` for one cycle (matches the proposal's "no runtime breakage" claim). |
| `Optional[T]` handling change interacts with the existing JSON-decode behavior for complex types | Add a focused test matrix: `int`, `Optional[int]`, `int \| None`, `list[int]`, `Optional[list[int]]`. The first three become primitive Click options; the rest stay JSON-decode. |
| ty integration regresses if the parallel agent's fixes are incomplete | This change's design assumes the ty-fix agent lands first. If it doesn't, the type-correctness-gate capability ships without the rule overrides — falls back to gating only the tightest subset. |
| OTel deps add to install size for users who don't want them | Optional extra; the `[otel]` install adds ~6 MB. CHANGELOG explicitly documents the trade-off. |
| `__init__.py` count rises to 11 with `lint/rules/` | Update `module-layout-discipline` spec scenario from "target 9" to "target = 2 + N plugins + 1 lint-rules subdir". This is a real spec-level change, not a number tweak. |

## Open questions (low-stakes, decide during implementation)

- Whether `App.use_factory` should accept multiple factories per call
  (`app.use_factory(f1, f2, ...)` with auto-mapping by signature) or
  stay one-at-a-time. Lean: one-at-a-time for clarity; revisit if
  multi-factory ergonomics matter.
- Whether the OTel middleware should also instrument the connections
  CLI subgroup or stay tool-call-only. Lean: tool-call-only;
  connection ops are infrequent and orthogonal.
- Whether `tests/packages/select/__init__.py` should be added (with
  `pyproject.toml [tool.pytest.ini_options] importmode = "importlib"`)
  or whether the directory should be renamed (`tests/packages/select_grammar/`).
  Lean: importlib mode — preserves source-mirror invariant.
