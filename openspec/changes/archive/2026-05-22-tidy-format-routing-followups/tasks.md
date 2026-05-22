## 1. Remove the dead `toon` path

- [x] 1.1 Delete the four tests that exist only to assert the `toon` guard: `test_format_toon_raises` (`tests/packages/cli/test_runtime.py`), `test_toon_format_no_longer_offered` (`tests/packages/cli/test_runtime_format.py`), `test_toon_hint_raises` (`tests/packages/formatter/test_format_response.py`), `test_format_hint_toon_raises` (`tests/packages/formatter/test_basemodel_render.py`).
- [x] 1.2 Remove the `format_hint == "toon"` `ValueError` branch and its docstring paragraph from `format_response` in `src/a2kit/packages/formatter/__init__.py`.
- [x] 1.3 Confirm no `toon` references remain in `src/` and `tests/` except deliberate history (`CHANGELOG.md`); run `make test` and confirm green.

## 2. Cache the `execute` stub/registry derivation

- [x] 2.1 Write a failing test (`tests/packages/codemode/test_runtime.py` or `test_build_wiring.py`): calling `execute` twice against a stable catalog derives the monty stubs and dataclass registry once, not twice (assert via a counter/spy on `generate_stubs` or `collect_models`).
- [x] 2.2 Add an instance-level cache to `A2kitCodeMode` keyed on `tuple(sorted(tool names))` of the resolved catalog → `(stubs, registry)`; have the `execute` closure consult it before rebuilding (design D2).
- [x] 2.3 Confirm the new test passes and all existing `tests/packages/codemode/` tests stay green.

## 3. Leaf types module and typed `format` field

- [x] 3.1 Update `tests/packages/formatter/test_response.py`: replace `Response(..., format="toon")` usages with a valid `FormatName` value; add a test that `a2kit.packages.formatter.formats` exposes `FormatHint` and `FormatName` and that `a2kit.packages.formatter` still re-exports both. (Format-type tests live in the new mirror file `test_formats.py`.)
- [x] 3.2 Create `src/a2kit/packages/formatter/formats.py` defining `FormatHint` and `FormatName`, importing nothing from within the `formatter` package (design D3).
- [x] 3.3 In `formatter/__init__.py`, replace the inline `FormatHint` / `FormatName` `Literal` definitions with `from .formats import FormatHint, FormatName`; keep both in `__all__`.
- [x] 3.4 Type `Rendered.format` as `FormatName` in `formatter/render.py` and `Response.format` as `FormatName` in `formatter/response.py` (importing from `.formats`); drop the `# "json" | "tsv"` comment.
- [x] 3.5 Run `make lint` (ty) and `make test`; confirm green.

## 4. No-cycle lint rule

- [x] 4.1 Write failing tests for the rule (`tests/packages/lint/rules/`): it flags `from a2kit.packages.<pkg> import ...` inside that package and `from . import ...`; it passes sibling-module imports (`from .formats import ...`), cross-package imports, and a package `__init__.py` importing its submodules.
- [x] 4.2 Implement the rule (`A2K-PKG-INIT-IMPORT`) in `src/a2kit/packages/lint/rules/importing.py`: detect a non-`__init__.py` file importing from its own package root (design D4).
- [x] 4.3 Register the rule in the lint dispatch table / `ALL_RULES` so it runs under `a2kit lint static`.
- [x] 4.4 Run `a2kit lint static src/` and resolve any pre-existing violations by importing from the defining submodule; allow-list (with a `# why:` note) only if a fix is genuinely infeasible. (4 violations found in `lint/rules/`; fixed by extracting shared AST helpers from `rules/__init__.py` into the leaf `rules/detect.py`.)
- [x] 4.5 Confirm the rule's tests pass and `make lint` is green.

## 5. Trim docstrings to the existing rule

- [x] 5.1 Bring the `consumer-aware-format-routing` code into compliance with the `module-layout-discipline` "module-level docstring at most one line" rule: trim module and verbose function docstrings in `formatter/render.py`, `formatter/__init__.py`, `formatter/formats.py`, the consumer-aware additions in `formatter/inference.py`, `codemode/__init__.py`, `codemode/marshal.py`, `codemode/runtime.py`, `codemode/stubs.py`, `mcp/format_routing.py`, `mcp/_wrappers.py`, `cli/_serve.py`. Preserve genuine non-obvious WHY.
- [x] 5.2 Run `a2kit lint static src/`, `make markdown-lint`, and `make test`; confirm green.

## 6. Specs and quality gate

- [x] 6.1 Confirm `openspec validate tidy-format-routing-followups --strict` passes.
- [x] 6.2 Add a `CHANGELOG.md` entry for the cleanup (dead-`toon` removal, `execute` caching, leaf format-types module, new lint rule).
- [x] 6.3 Run the full gate: `make lint`, `make test` (coverage ≥ 90%), `make adr-check`, `make markdown-lint`; confirm all green.
