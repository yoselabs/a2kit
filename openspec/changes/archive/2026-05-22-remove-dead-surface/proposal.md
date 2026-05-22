## Why

Roughly seven minor releases of fast pre-1.0 iteration have left dead
weight in `src/a2kit/`: an entire unused package, deprecated aliases
with zero callers, defined-but-unconsumed types, an unread struct
field, discarded compat parameters, and tests that assert language
behaviour rather than a2kit behaviour. This weight contradicts the
AGENTS.md doctrine ("no multiple ways to do the same thing", "no dead
defensive structure", "no backward-compat shims") and one item drags a
third-party runtime dependency (`cel-python`) carried solely for code
nothing calls. Removing it now — while pre-1.0 — shrinks the surface,
drops a dependency, and stops the rot before it ossifies.

## What Changes

- **BREAKING**: Delete the entire `src/a2kit/packages/select/`
  package (~218 SLOC, CEL filtering). Grep confirms zero callers in
  `src/` — no `from a2kit.packages.select` import outside the package
  and no `--select` CLI/MCP flag. Delete with it the `cel-python`
  runtime dependency, the two `pyproject.toml` carve-outs for the
  package (the per-file `noqa` block and the `select` layer slot in
  `src/a2kit/packages/lint/layers.py`), the test
  `tests/packages/select/test_select.py` plus its `tests/_test_only.txt`
  entry, and the select-specific tests in
  `tests/test_extras_coverage_2.py`. The `--import-mode=importlib` /
  stdlib-shadow comments in `pyproject.toml` that name the select test
  package are also tidied.
- **BREAKING**: Remove `App.tool_descriptors()` — a "Deprecated alias
  for `tools()`" with zero callers anywhere in `src/`, `tests/`,
  `examples/`, or `docs/`. `App.tools()` is the single
  tool-introspection API.
- Collapse the lint aliases `run_runtime` → `run_runtime_checks` and
  `run_static` → `run_static_rules` to one canonical name each. The
  `*_checks` / `*_rules` names are used everywhere; the bare aliases
  are unused. Fix `__all__` and the module docstrings in
  `runtime.py`, `static.py`, and `lint/__init__.py`.
- **BREAKING**: Remove the `ListViewMode` enum, its `Local` /
  `Passthrough` module-level aliases, and the `ListViewMode.AUTO`
  member from `src/a2kit/packages/formatter/response.py`, plus their
  re-exports in `formatter/__init__.py`. They are defined and
  re-exported but have zero consumers — a surface with no
  implementation behind it.
- Remove the `ToolBuildSpec.descriptor` field from
  `src/a2kit/packages/dispatch/spec.py`. It is set at two construction
  sites (`mcp/server.py`, `cli/builder.py`) but never read; remove the
  field and both kwargs.
- Remove the four discarded compat parameters from
  `StderrToolContext.__init__` in
  `src/a2kit/packages/context/__init__.py` — `report_type`,
  `tool_name`, `reports_enabled`, `events_enabled` — all carry
  `# noqa: ARG002` and all are silently dropped. No caller passes
  them.
- Delete two tautological tests:
  `tests/test_in_process_client.py::test_genuinely_unknown_attribute_raises_attribute_error`
  (asserts Python's own attribute lookup, not a2kit behaviour) and the
  `pytest.raises(AttributeError)` half of
  `tests/test_extras_coverage_2.py::test_otel_module_lazy_attrs_resolve`.
- Verify-then-maybe-delete the two import tombstones:
  `src/a2kit/packages/cli/context.py` and the `run_code` `__getattr__`
  branch in `src/a2kit/packages/codemode/__init__.py`. Each is a
  loud-crash `ImportError` for an old import path. A task verifies
  whether any released consumer could ever have used the old path; if
  the old path predates any release (orphaned), the tombstone is
  deleted.

## Capabilities

### New Capabilities

<!-- none — this change only removes surface -->

### Modified Capabilities

- `tool-descriptors`: the legacy `App.tool_descriptors()` accessor is
  removed and the spec is reconciled so it consistently names
  `App.tools()` as the single tool-introspection API. The existing
  spec is internally contradictory — one requirement mandates removal
  of `tool_descriptors()` while two others still use the name; this
  change makes the spec consistent.

## Impact

- **Surface**: ~260+ SLOC removed across `select/`, `app.py`,
  `lint/`, `formatter/`, `dispatch/spec.py`, and `context/`. Smaller
  public surface, fewer "two names for one thing" traps.
- **Dependencies**: `cel-python>=0.5,<0.6` dropped from
  `pyproject.toml` — one fewer transitive tree at install time.
- **Tooling**: `pyproject.toml` loses two select-specific carve-outs;
  `lint/layers.py` loses the `select` layer slot.
- **Tests**: the select test package and select-specific extras tests
  are deleted; two tautological assertions removed.
- **Specs**: only `tool-descriptors` is reconciled. Broad spec
  reconciliation is owned by a separate change (`reconcile-stale-specs`)
  and is explicitly out of scope here.
