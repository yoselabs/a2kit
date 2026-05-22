## 1. Layer manifest

- [ ] 1.1 Define the layer manifest (unit → layer integer) as a single
      declarative table in `packages/lint/`, covering every
      `packages/*` directory **and** a `core` pseudo-unit for the
      top-level `a2kit.*` modules
- [ ] 1.2 Test: the manifest covers every directory under
      `src/a2kit/packages/` plus `core` — nothing unassigned

## 2. A2K-LAYER rule

- [ ] 2.1 Add `A2K_LAYER` rule code to `static.py`
- [ ] 2.2 Implement in `packages/lint/rules/importing.py`: resolve each
      import to its unit (core vs a named package); flag an import of a
      higher-layer unit; flag a same-layer import that closes a cycle
- [ ] 2.3 The rule MUST inspect `TYPE_CHECKING`-guarded imports, not
      only runtime imports
- [ ] 2.4 Register in `static.py::ALL_RULES`, warn-only initially
- [ ] 2.5 Tests: cross-layer violation fires; core→kernel is clean;
      package→core upward import fires when the package is below core;
      same-layer cycle fires; a `TYPE_CHECKING`-only cycle fires

## 3. A2K-PKG-FRONT-DOOR rule

- [ ] 3.1 Add `A2K_PKG_FRONT_DOOR` rule code to `static.py`
- [ ] 3.2 Implement: flag `from a2kit.packages.X.<submodule> import ...`
      when the importing file is outside package X; support a
      documented allowlist constant
- [ ] 3.3 Register in `static.py::ALL_RULES`, warn-only initially
- [ ] 3.4 Tests: deep cross-package import fires; same-package
      submodule import is clean; allowlisted import is clean

## 4. Open the front doors

- [ ] 4.1 `packages/di/__init__.py`: re-export `Container`, `Scope`,
      `Resolver`
- [ ] 4.2 `packages/formatter/__init__.py`: re-export
      `infer_format_hint`, `build_encoding_plan`, and other types
      `app.py` / `tool.py` use
- [ ] 4.3 `packages/mcp/__init__.py`: re-export `build_mcp_server`
- [ ] 4.4 Rewrite `app.py` deep imports to front-door imports
- [ ] 4.5 Rewrite `signature.py` and `tool.py` deep imports
- [ ] 4.6 Rewrite the `build_mcp_server` deep imports in `cli/_serve.py`,
      `packages/testing`, and the relocated `run_code` onto
      `a2kit.packages.mcp`
- [ ] 4.7 Run `a2kit lint static` — expect zero `A2K-PKG-FRONT-DOOR`
      hits after the rewrites

## 5. Flip to error

- [ ] 5.1 Run `a2kit lint static` — confirm `A2K-LAYER` and
      `A2K-PKG-FRONT-DOOR` both report zero hits
- [ ] 5.2 Flip both rules from warn to hard error in `make lint` / CI
- [ ] 5.3 Refresh `module-layout-discipline`'s `__init__.py`-count
      scenario to the true package count

## 6. Wrap-up

- [ ] 6.1 AGENTS.md: document the layer manifest and the two rules in
      the "Architecture strategy" section
- [ ] 6.2 New ADR recording the layer DAG (core included) — the
      internal-graph sibling to ADR 0004's audience-tiered public
      surface
- [ ] 6.3 `make lint`, `make test` green;
      `openspec validate enforce-package-layering --strict`
- [ ] 6.4 `openspec archive enforce-package-layering`
