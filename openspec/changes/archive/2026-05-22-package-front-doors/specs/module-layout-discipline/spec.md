## ADDED Requirements

### Requirement: A package `__init__.py` is a re-export front door, not an implementation site

A plugin-package `__init__.py` under `src/a2kit/packages/<name>/` SHALL contain only front-door plumbing: imports, re-exports, module-level constants, an `__all__`, and an optional lazy re-export `__getattr__` / `__dir__` pair for cold-start deferral. It SHALL NOT define implementation — a top-level `class` or a top-level `def` / `async def` other than the lazy `__getattr__` / `__dir__` pair. Implementation SHALL live in named submodules of the package. A static lint rule (`A2K-PKG-INIT-IMPL`) SHALL enforce this and surface findings under `a2kit lint static`.

The `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, and `testing` packages SHALL be brought into compliance: their `__init__.py` implementation moves into named submodules and their `__init__.py` is reduced to re-exports. With every package compliant, the rule SHALL report zero findings against `src/a2kit/`.

#### Scenario: Implementation in `__init__.py` is flagged

- **WHEN** `a2kit lint static src/` runs against a package `__init__.py` that defines a class body or a logic-bearing function
- **THEN** a lint finding is emitted naming the offending definition

#### Scenario: Re-export front door is clean

- **WHEN** `a2kit lint static src/` runs against a package `__init__.py` that only imports, re-exports, declares `__all__`, and optionally defines a lazy re-export `__getattr__` / `__dir__`
- **THEN** no such finding is emitted

#### Scenario: Every init-heavy package has a re-export-only front door

- **WHEN** the `__init__.py` of `ldd`, `context`, `health`, `codemode`, `connections`, `formatter`, and `testing` are inspected after the change
- **THEN** each contains only re-export front-door plumbing
- **AND** the package's implementation lives in named submodules alongside it

#### Scenario: The rule reports clean against the whole source tree

- **WHEN** `a2kit lint static src/` runs after the splits land
- **THEN** the `A2K-PKG-INIT-IMPL` rule emits no findings

#### Scenario: Root-level imports are unaffected

- **WHEN** existing consumer code imports a symbol from one of the seven packages' roots (`a2kit.packages.<name>`)
- **THEN** the import resolves exactly as before the split
