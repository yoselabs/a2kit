## Context

a2kit lifts one tool surface to a CLI and an MCP server. It is at
v0.39.3, pre-1.0, solo-maintained. Seven minor releases of fast
iteration left eight distinct pieces of dead weight in `src/a2kit/`:

1. `packages/select/` — a CEL-based filtering package (~218 SLOC)
   with zero callers and a dedicated third-party dependency
   (`cel-python`).
2. `App.tool_descriptors()` — a deprecated alias for `App.tools()`,
   zero callers.
3. `lint.run_runtime` / `lint.run_static` — bare-name aliases for
   `run_runtime_checks` / `run_static_rules`, zero callers.
4. `ListViewMode` / `Local` / `Passthrough` / `ListViewMode.AUTO` —
   a formatter enum and aliases, defined and re-exported, zero
   consumers.
5. `ToolBuildSpec.descriptor` — a struct field set at two sites and
   read at none.
6. Four `# noqa: ARG002` compat parameters on
   `StderrToolContext.__init__`, all discarded.
7. Two tautological tests asserting language behaviour.
8. Two import-path tombstones (`cli/context.py`,
   `codemode.run_code`) whose orphan status must be verified.

Each item is small in isolation; together they violate AGENTS.md
principles "no multiple ways to do the same thing", "no dead
defensive structure", and "no backward-compat shims". This is a
removal-only change — it adds no behaviour and creates no new
capability.

The constraint that shapes the change: it is purely a planning
artifact set at this stage. The implementation, when it lands, must
keep `make check` green (lint + tests + coverage ≥ 90%), so deleting a
covered line means deleting its test in the same step.

## Goals / Non-Goals

**Goals:**

- Remove the eight dead-weight items above and everything carried
  solely to support them (the `cel-python` dependency, the two
  `pyproject.toml` select carve-outs, the `select` layer-manifest
  slot, the select test package).
- Collapse every "two names for one thing" to its single canonical
  name: `tools()`, `run_runtime_checks`, `run_static_rules`.
- Reconcile the `tool-descriptors` spec so it is internally
  consistent: `tool_descriptors()` is gone, `tools()` is the API.
- Keep the framework's observable behaviour identical for every
  surface that has a real consumer — nothing here is a behaviour
  change, only a surface deletion.

**Non-Goals:**

- Not reconciling specs broadly. Only `tool-descriptors` is touched.
  A separate change, `reconcile-stale-specs`, owns the rest; this
  change deliberately does not edit `type-driven-format-routing` or
  any other spec (verified: no spec references `ListViewMode`).
- Not changing dispatch, DI, formatter routing, or lint rule
  semantics. The `descriptor` field and the `ListViewMode` enum are
  removed because nothing reads them, not to alter how anything
  works.
- Not introducing a deprecation cycle. a2kit is pre-1.0 and AGENTS.md
  forbids backward-compat shims; removals are immediate and marked
  **BREAKING** where they touch a public name.
- Not deleting the `cli/context.py` tombstone unconditionally — its
  fate is decided by the verification task (see D6).

## Decisions

### D1. Delete `packages/select/` whole, with its dependency and carve-outs

The package is removed as a unit, not deprecated. Grep confirms zero
`from a2kit.packages.select` imports outside the package itself and no
`--select` flag on either transport. Because the package is the *sole*
consumer of `cel-python`, the dependency goes with it. The two
`pyproject.toml` carve-outs exist only for this package — the per-file
`noqa` block (`C901, ARG005, PLR0911, PERF401` for the Lark-tree
walking) and the `select` slot in `LAYER_MANIFEST` — so both are
removed. The `--import-mode=importlib` machinery in `pyproject.toml`
was added partly because the select test package shadows the stdlib
`select` module name; the explanatory comments that name the select
package are tidied, but `--import-mode=importlib` itself stays
(other test packages may rely on it — the implementation task
verifies before touching the `addopts` value).

Alternative considered: keep the package, mark it experimental. Rejected
— "experimental but unreferenced" is exactly the dead structure
AGENTS.md rejects, and it keeps a dependency alive for nothing.

### D2. Remove `tool_descriptors()`; `tools()` is the one accessor

`App.tool_descriptors()` is documented in-code as a "Deprecated alias
for `tools()`" and has zero callers. It is deleted outright. The
`tool-descriptors` spec already mandates this removal in one
requirement but two other requirements ("Descriptor build is one-shot"
and a scenario under it) still phrase their normative text in terms of
`tool_descriptors()`. This change rewrites those to name `tools()`, so
the spec stops contradicting itself. No deprecation shim is added.

### D3. Collapse lint aliases to canonical names

`run_runtime = run_runtime_checks` (in `runtime.py`) and
`run_static = run_static_rules` (in `static.py`) are bare aliases.
Every caller — `lint/cli.py` and the entire `tests/packages/lint/`
tree — already uses the `_checks` / `_rules` form. The aliases, their
`__all__` entries in all three files (`runtime.py`, `static.py`,
`lint/__init__.py`), and the alias mentions in the `lint/__init__.py`
module docstring are removed. One name per function.

### D4. Remove `ListViewMode` and its aliases as a no-implementation surface

`ListViewMode` (with `AUTO` / `LOCAL` / `PASSTHROUGH`) and the
module-level `Local` / `Passthrough` aliases are defined in
`formatter/response.py` and re-exported from `formatter/__init__.py`,
but no decorator, dispatch stage, or tool actually consumes them — the
docstring even calls `AUTO` a "future-reserved sentinel … currently
unused". A re-exported public type with no implementation behind it is
dead surface. It is removed from `response.py` (enum, both aliases,
`__all__`) and from `formatter/__init__.py` (import line and `__all__`).
The `response.py` module docstring, which describes the enum, is
trimmed. Verified: no file under `openspec/specs/` references
`ListViewMode` — so no spec delta is needed for this item.

### D5. Remove `ToolBuildSpec.descriptor` and both kwargs

`ToolBuildSpec.descriptor: ToolDescriptor | None = None` is read
nowhere in `src/`. It is set at `mcp/server.py` (`descriptor=desc`)
and `cli/builder.py` (`descriptor=None`). The field and both kwargs
are removed. The dataclass docstring paragraph describing `descriptor`
is dropped. Test construction sites that pass `descriptor=` (e.g.
`tests/packages/dispatch/test_stages.py`) are updated in the same
step. The `ToolDescriptor` import in `spec.py` is dropped if it
becomes unused.

### D6. Tombstones: verify orphan status, then delete only if orphaned

Both `cli/context.py` and the `codemode.run_code` `__getattr__` branch
are loud-crash `ImportError` tombstones for import paths moved in the
import-acyclicity refactor (commit `ccc93fb`, and `92fdf68` for
codemode). A tombstone earns its keep only if a *released* consumer
could have used the old path; if the old path never shipped, the
tombstone guards nothing.

- `codemode.run_code`: the `codemode` package was introduced in
  `92fdf68` (v0.39.3, the most recent commit). `run_code` has always
  lived at `a2kit.packages.cli` — there is no release in which
  `a2kit.packages.codemode.run_code` was importable. The tombstone is
  therefore **orphaned** and is deleted (the `__getattr__` branch and,
  if `__getattr__` then only does the trivial `AttributeError` fall-
  through, the whole function — kept only if it still serves a
  purpose).
- `cli/context.py`: the old path `a2kit.packages.cli.context` is still
  named in example docstrings (`examples/sampling/server.py`,
  `examples/elicitation/server.py`,
  `examples/streaming_logger/README.md`) and has a live test
  (`tests/packages/cli/test_context.py`). The implementation task
  re-checks whether that path ever shipped as a real (non-tombstone)
  module in a tagged release. If it did, the tombstone stays and the
  example docstrings are corrected to the new path under
  `reconcile-stale-specs`/docs scope — not here. If it did not, the
  tombstone module and its test are deleted. The verification result
  is recorded in the task notes. Default expectation: `cli/context.py`
  is **kept** (the old path predates the refactor and example
  docstrings reference it), `codemode.run_code` is **deleted**.

### D7. Delete tautological tests, not the code they touch

`test_genuinely_unknown_attribute_raises_attribute_error` asserts that
accessing an undefined attribute on a `TestClient` raises
`AttributeError` — that is Python's own behaviour, not an a2kit
invariant. The `pytest.raises(AttributeError)` half of
`test_otel_module_lazy_attrs_resolve` similarly asserts the stdlib
`__getattr__` fall-through, not the lazy-attr resolution that test is
named for. Both assertions are deleted; the lazy-attr-*resolution*
half of the otel test (the part that does check a2kit behaviour) is
kept. No production code changes for this item.

### D8. Coverage stays green by deleting tests with their code

a2kit enforces `--cov-fail-under=90`. Removing a covered line drops
coverage unless its test goes too. Each removal task pairs the
production deletion with the corresponding test deletion in the same
task group: `select/` with `tests/packages/select/` and the select
extras tests; `tool_descriptors()` with any test exercising it (the
`tool-descriptors` spec scenario "Legacy `tool_descriptors()` removed"
becomes a removed/modified requirement, not a live test);
`ListViewMode` with `tests/packages/formatter/test_response.py`'s
`TestListViewMode` class and the `Local` / `Passthrough` import.

## Risks / Trade-offs

- **A future feature wants CEL filtering again** → Mitigation: it is
  recoverable from git history, and re-adding a dependency for a real
  consumer is cheap and correct. Keeping ~218 SLOC plus a dependency
  alive on the *speculation* of a future consumer is precisely the
  dead structure AGENTS.md forbids.
- **`ListViewMode.AUTO` was a deliberate forward-reservation** →
  Mitigation: the docstring says "currently unused"; a forward-
  reserved enum member with no decorator path to reach it is
  indistinguishable from dead code. If list-view modes return, the
  enum is re-introduced alongside the decorator that consumes it, in
  one coherent change.
- **Coverage regression after deletion** → Mitigation: D8 — every
  production removal is paired with its test removal in the same task
  group; the wrap-up task runs `make check` to confirm
  `--cov-fail-under=90` still passes.
- **Tombstone deleted too eagerly** → Mitigation: D6 makes deletion
  conditional on an explicit verification task. The default outcome
  (delete `codemode.run_code`, keep `cli/context.py`) is the
  conservative one; the task records its finding.
- **Spec drift** → the `tool-descriptors` spec is the only spec
  touched. Risk that another spec silently depends on a removed name:
  mitigated by the grep in D4 (no spec references `ListViewMode`) and
  by scoping all other spec reconciliation to `reconcile-stale-specs`.
- **`pyproject.toml` `addopts` over-edit** → the
  `--import-mode=importlib` flag has reasons beyond the select test
  package; D1 keeps the flag and only tidies the naming comments,
  with the implementation task verifying no other test package needs
  the comment's rationale before editing.
