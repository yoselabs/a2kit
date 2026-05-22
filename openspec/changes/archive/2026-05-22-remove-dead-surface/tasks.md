## 1. Delete the `select` package and its dependency

- [x] 1.1 Delete the directory `src/a2kit/packages/select/` in full
      (`__init__.py` and any `__pycache__`)
- [x] 1.2 Remove the `select` slot from `LAYER_MANIFEST` in
      `src/a2kit/packages/lint/layers.py`
- [x] 1.3 In `pyproject.toml`, remove the `cel-python>=0.5,<0.6`
      dependency line
- [x] 1.4 In `pyproject.toml`, remove the per-file `noqa` carve-out
      for `src/a2kit/packages/select/__init__.py`
      (`["C901", "ARG005", "PLR0911", "PERF401"]`)
- [x] 1.5 In `pyproject.toml`, tidy the `--import-mode=importlib`
      comments that name the select test package (in both the
      `[tool.pytest.ini_options]` and the mutmut config blocks);
      verify `--import-mode=importlib` itself is still needed by
      another test package before removing the flag — keep the flag
      if so, only adjust the explanatory comments
- [x] 1.6 Delete `tests/packages/select/test_select.py` and remove
      its line from `tests/_test_only.txt`
- [x] 1.7 In `tests/test_extras_coverage_2.py`, delete the
      select-specific tests (`test_select_evaluate_bool_python_path`,
      `test_select_evaluate_non_bool_result_raises_invalid_filter`,
      `test_select_collect_atom_names_flattens_nested_dict`,
      `test_select_validate_atoms_raises_for_unknown`,
      `test_select_validate_atoms_silent_for_known`) and the
      `--- select edges ---` section comment
- [x] 1.8 Grep `src/`, `tests/`, `examples/` for any remaining
      `select` reference (e.g. `InvalidFilterExpression`,
      `UnknownAtomError` in `a2kit/exceptions.py`) and remove
      exception types orphaned by the deletion

## 2. Remove `App.tool_descriptors()`

- [x] 2.1 Delete the `tool_descriptors()` method from
      `src/a2kit/app.py` (~line 497)
- [x] 2.2 Grep `src/`, `tests/`, `examples/`, `docs/` to confirm no
      caller remains; remove any test that exercised the method
- [x] 2.3 Confirm `App.tools()` is the single tool-introspection
      accessor and behaviour is unchanged

## 3. Collapse the lint aliases

- [x] 3.1 In `src/a2kit/packages/lint/runtime.py`, delete
      `run_runtime = run_runtime_checks` (~line 162) and remove
      `"run_runtime"` from `__all__`
- [x] 3.2 In `src/a2kit/packages/lint/static.py`, delete
      `run_static = run_static_rules` (~line 241) and remove
      `"run_static"` from `__all__`
- [x] 3.3 In `src/a2kit/packages/lint/__init__.py`, remove the
      `run_runtime` / `run_static` re-export lines, the
      `"run_runtime"` / `"run_static"` `__all__` entries, and the
      alias mentions in the module docstring
- [x] 3.4 Confirm `lint/cli.py` and all `tests/packages/lint/` still
      use only `run_runtime_checks` / `run_static_rules`

## 4. Remove `ListViewMode` and its aliases

- [x] 4.1 In `src/a2kit/packages/formatter/response.py`, delete the
      `ListViewMode` enum (with `AUTO` / `LOCAL` / `PASSTHROUGH`),
      the `Local` and `Passthrough` module-level aliases, and the
      `"ListViewMode"` / `"Local"` / `"Passthrough"` entries from
      `__all__`
- [x] 4.2 Trim the `response.py` module docstring lines that
      describe the `ListViewMode` enum and the `Local` / `Passthrough`
      aliases
- [x] 4.3 In `src/a2kit/packages/formatter/__init__.py`, remove
      `ListViewMode`, `Local`, `Passthrough` from the `.response`
      import and from `__all__`
- [x] 4.4 In `tests/packages/formatter/test_response.py`, delete the
      `TestListViewMode` class, the `Local` / `Passthrough` /
      `ListViewMode` imports, and update the module docstring

## 5. Remove `ToolBuildSpec.descriptor`

- [x] 5.1 In `src/a2kit/packages/dispatch/spec.py`, delete the
      `descriptor: ToolDescriptor | None = None` field, the docstring
      paragraph describing it, and the now-unused `ToolDescriptor`
      import if it becomes orphaned
- [x] 5.2 In `src/a2kit/packages/mcp/server.py`, remove the
      `descriptor=desc` kwarg from the `ToolBuildSpec(...)`
      construction
- [x] 5.3 In `src/a2kit/packages/cli/builder.py`, remove the
      `descriptor=None` kwarg from the `ToolBuildSpec(...)`
      construction
- [x] 5.4 Update test construction sites that pass `descriptor=`
      (e.g. `tests/packages/dispatch/test_stages.py`) to drop the
      kwarg

## 6. Remove the dead `StderrToolContext` compat parameters

- [x] 6.1 In `src/a2kit/packages/context/__init__.py`, remove the
      `report_type`, `tool_name`, `reports_enabled`, `events_enabled`
      parameters (all `# noqa: ARG002`) from
      `StderrToolContext.__init__`
- [x] 6.2 Grep `src/`, `tests/`, `examples/` for any
      `StderrToolContext(` call passing those kwargs and update it
      (none expected — all known call sites use `StderrToolContext()`)

## 7. Remove tautological tests

- [x] 7.1 Delete
      `tests/test_in_process_client.py::test_genuinely_unknown_attribute_raises_attribute_error`
- [x] 7.2 In `tests/test_extras_coverage_2.py`, remove the
      `pytest.raises(AttributeError)` block from
      `test_otel_module_lazy_attrs_resolve`, keeping the lazy-attr
      *resolution* assertions that check real a2kit behaviour

## 8. Verify-then-maybe-delete the import tombstones

- [x] 8.1 Verify whether `a2kit.packages.codemode.run_code` was ever
      importable in a tagged release (the `codemode` package was
      introduced in commit `92fdf68` / v0.39.3; `run_code` has always
      lived at `a2kit.packages.cli`). If orphaned, delete the
      `run_code` branch from the `__getattr__` in
      `src/a2kit/packages/codemode/__init__.py`
- [x] 8.2 Verify whether `a2kit.packages.cli.context` ever shipped as
      a real (non-tombstone) module in a tagged release. If orphaned,
      delete `src/a2kit/packages/cli/context.py` and
      `tests/packages/cli/test_context.py`; if not, keep both and
      record the finding in this task. Default expectation: keep
      `cli/context.py`, delete `codemode.run_code`
      VERIFIED: `cli/context.py` shipped as a real module in tagged
      releases v0.38.0 and v0.39.3 (moved out by refactor `ccc93fb`) —
      tombstone KEPT. `codemode` package is absent from every tag
      (introduced post-v0.39.3, untagged) so `codemode.run_code` never
      shipped — tombstone (the whole `__getattr__`) DELETED.
- [x] 8.3 Record the verification outcome for both tombstones in the
      change notes (which was deleted, which was kept, and why)

## 9. Reconcile the `tool-descriptors` spec

- [x] 9.1 Confirm `openspec/specs/tool-descriptors/spec.md` is
      consistent after this change: `tool_descriptors()` is removed
      everywhere and `App.tools()` is named as the single
      tool-introspection accessor (the "Descriptor build is one-shot"
      requirement is updated by the spec delta in this change)

## 10. Wrap-up

- [x] 10.1 Run `make check` (lint + tests) and confirm
      `--cov-fail-under=90` still passes
- [x] 10.2 Run `make example-smoke` and `make markdown-lint` green
- [x] 10.3 Update the CHANGELOG `Unreleased` section with the
      **BREAKING** removals (`packages.select`,
      `App.tool_descriptors()`, `ListViewMode` / `Local` /
      `Passthrough`, the `cel-python` dependency)
- [x] 10.4 Run `openspec validate remove-dead-surface --strict`
- [x] 10.5 Run `openspec archive remove-dead-surface`
