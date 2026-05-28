## ADDED Requirements

### Requirement: `Lazy` and `LddEmission` are top-level a2kit re-exports

`a2kit.Lazy` and `a2kit.LddEmission` SHALL exist as top-level
re-exports of `a2kit.packages.di.Lazy` and
`a2kit.packages.ldd.LddEmission` respectively.

Both top-level paths SHALL be the canonical import targets going
forward. The existing `a2kit.packages.di.Lazy` and
`a2kit.packages.ldd.LddEmission` paths SHALL continue to work
(no removal — they remain as the implementation site, re-exported by
the top-level).

The top-level `a2kit/__init__.py` SHALL include both symbols in its
`__all__` so they appear in `dir(a2kit)` alongside `App`, `Router`,
`ToolContext`, `HealthResult`.

#### Scenario: Top-level import works

- **WHEN** `from a2kit import Lazy, LddEmission` runs
- **THEN** both imports succeed
- **AND** `Lazy is a2kit.packages.di.Lazy`
- **AND** `LddEmission is a2kit.packages.ldd.LddEmission`

#### Scenario: Legacy import paths still work

- **WHEN** `from a2kit.packages.di import Lazy` runs
- **THEN** the import succeeds and returns the same object as
  `from a2kit import Lazy`

#### Scenario: Symbols appear in `dir(a2kit)`

- **WHEN** `dir(a2kit)` is inspected
- **THEN** `"Lazy"` and `"LddEmission"` appear in the result
- **AND** `"App"`, `"Router"`, `"ToolContext"`, `"HealthResult"` also
  appear (no regression on existing top-level symbols)

### Requirement: `a2kit.packages.*` is documented as private

The `a2kit/packages/__init__.py` module docstring SHALL declare the
`a2kit.packages.*` namespace as "internal scaffolding, not the
consumer API." The documentation SHALL direct consumers to import
canonical symbols from the top-level `a2kit` package instead.

This is a documentation/discoverability change only; existing imports
under `a2kit.packages.*` continue to work (compatibility preserved
indefinitely).

#### Scenario: Module docstring carries the private-namespace note

- **WHEN** `a2kit.packages.__doc__` is inspected
- **THEN** the docstring contains language indicating the namespace
  is "internal" / "scaffolding" / "not a stability surface" — language
  consistent with stdlib `_thread` / `threading` convention
- **AND** the docstring names the top-level `a2kit` package as the
  canonical consumer API
