## 1. Layer manifest

- [x] 1.1 `LAYER_MANIFEST` declared in `packages/lint/layers.py` —
      covers every `packages/*` directory plus the `core` pseudo-unit.
      Corrected from the draft: `context` joins the kernel layer
      (`context → ldd` is a same-layer non-cycle edge), collapsing six
      layers to five
- [x] 1.2 `tests/packages/lint/test_layers.py` — the manifest covers
      every directory under `src/a2kit/packages/` plus `core`, nothing
      stale or unassigned

## 2. A2K-LAYER rule

- [x] 2.1 `A2K_LAYER` rule code added to `static.py::ALL_RULES`
- [x] 2.2 Implemented in `lint/rules/importing.py` (`collect_layer_imports`
      + `rule_a2k_layer_cross`): resolves each import to its unit, flags
      higher-layer imports, flags same-layer imports that close a cycle
- [x] 2.3 Inspects `TYPE_CHECKING`-guarded (and function-local) imports —
      `ast.walk` visits every `ImportFrom` / `Import` node
- [x] 2.4 Registered in `static.py` and wired into `run_static_rules`'s
      cross-file pass. Shipped directly as hard error (see §5.2)
- [x] 2.5 Tests: higher-layer import fires; core→kernel clean;
      same-layer non-cycle clean; same-layer cycle fires; type-only
      cycle fires; noqa suppresses

## 3. A2K-PKG-FRONT-DOOR rule

- [x] 3.1 `A2K_PKG_FRONT_DOOR` rule code added to `static.py`
- [x] 3.2 Implemented `rule_pkg_front_door`: flags
      `from a2kit.packages.X.<submodule>` from outside package X;
      `_FRONT_DOOR_ALLOWLIST` constant for documented exceptions
- [x] 3.3 Registered in `static.py::_build_rules_table`. Shipped
      directly as hard error
- [x] 3.4 Tests: deep cross-package import fires; front-door import
      clean; same-package submodule clean; noqa suppresses

## 4. Open the front doors

- [x] 4.1 `packages/di/__init__.py` already re-exports `Container`,
      `Scope`, `Resolver`; gained `lazy_inner_type` (`signature.py`
      needs it)
- [x] 4.2 `packages/formatter/__init__.py` gained `infer_format_hint`
      (`build_encoding_plan` was already re-exported)
- [x] 4.3 `packages/mcp/__init__.py` already exposes `build_mcp_server`
      (lazy `__getattr__`); `packages/cli/__init__.py` already
      re-exports `build_full_cli`
- [x] 4.4 `app.py` deep imports rewritten to front-door imports
- [x] 4.5 `signature.py` and `tool.py` deep imports rewritten
- [x] 4.6 `build_mcp_server` deep imports in `cli/_serve.py` and
      `testing/client.py` rewritten onto `a2kit.packages.mcp`; the
      `a2kit/__init__.py` `run()` import onto `a2kit.packages.cli`;
      `connections/dispatch.py` + `health/__init__.py` onto
      `a2kit.packages.di`
- [x] 4.7 `a2kit lint static src/` — zero `A2K-PKG-FRONT-DOOR` and
      zero `A2K-LAYER` hits after the rewrites

## 5. Flip to error

- [x] 5.1 `a2kit lint static src/ tests/ examples/` — both rules
      report zero hits
- [x] 5.2 Both rules are in `ALL_RULES` as hard errors. The
      warn-first window collapsed to zero — this change cleans every
      violation in the same pass, so there is no interval where the
      rule ships ahead of the cleanup
- [x] 5.3 `module-layout-discipline`'s `__init__.py`-count scenario
      uses the dynamic `2 + N + R` formula — `context` and `dispatch`
      are already covered with no hand-edit needed

## 6. Wrap-up

- [x] 6.1 AGENTS.md: layer manifest + the two rules documented in the
      "Architecture strategy" section
- [x] 6.2 ADR 0015 records the internal layer DAG — the internal-graph
      sibling of ADR 0004
- [x] 6.3 `make lint`, `make test` green (1065 passed, 90.91% cov)
- [x] 6.4 `openspec archive enforce-package-layering`
