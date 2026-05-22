## Why

Over half of a2kit's plugin packages put implementation directly in `__init__.py`. `ldd/__init__.py` is 580 lines — an entire subsystem living in the package's front door. `context/__init__.py` is 332 lines, `health/__init__.py` 153; `codemode`, `connections`, `formatter`, and `testing` each carry a class or logic-bearing functions in their `__init__.py` too. The remaining packages (`di`, `dispatch`, `cli`, `mcp`, `lint`) keep `__init__.py` as a thin re-export front door with the implementation in named submodules.

The `A2K-PKG-FRONT-DOOR` rule treats `__init__.py` as a boundary — but for the init-heavy packages the boundary *is* the building. The package-as-directory affordance is unused: a 580-line `ldd` has no visible internal structure, while a 9-file `di` does. The inconsistency means the front-door rule has nothing to bite on for the packages that most need internal structure.

## What Changes

- Split **all seven init-heavy packages** — `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, `testing` — so each `__init__.py` becomes a re-export-only front door; the implementation moves into named submodules within each package.
- Add a `module-layout-discipline` requirement: a package `__init__.py` SHALL be a re-export front door (re-exports plus an optional lazy `__getattr__` facade), not an implementation site. A lint rule (`A2K-PKG-INIT-IMPL`) enforces it so the inconsistency cannot regress — and, with all seven brought into compliance, the rule reports zero findings against `src/a2kit/`.

Verified safe by investigation: there are **zero** deep-submodule imports of the relocated symbols today — every consumer imports the package root or a public facade. The split is therefore purely internal and breaks no importer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `module-layout-discipline`: adds a requirement that a package `__init__.py` is a re-export front door, not an implementation site, with lint enforcement.

## Impact

- **Code:** `src/a2kit/packages/{ldd,context,health,codemode,connections,formatter,testing}/` — implementation relocated into named submodules; each `__init__.py` reduced to re-exports.
- **Tests:** `tests/packages/<pkg>/` mirror the new submodule structure (per the existing test-layout requirement) — mostly renames of existing non-mirror test files.
- **Lint:** a new rule (`A2K-PKG-INIT-IMPL`) flags a class or logic-bearing function defined in a package `__init__.py`.
- **Public API / consumers:** unchanged. All current imports target the package root or a facade; those continue to resolve.
- **Out of scope:** the `otel` package — already a clean lazy-`__getattr__` facade; the `di`, `dispatch`, `cli`, `mcp`, `lint` packages — already compliant.
