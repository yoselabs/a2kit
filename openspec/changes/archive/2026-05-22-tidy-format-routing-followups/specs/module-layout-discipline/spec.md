## ADDED Requirements

### Requirement: Submodules do not import from their own package `__init__`

A Python file under `src/a2kit/` that is not itself a package `__init__.py` SHALL NOT import from its own package's `__init__.py`, in either the absolute form (`from a2kit.<...>.<package> import ...`) or the relative form (`from . import ...`). Symbols shared between a package's `__init__.py` and its submodules SHALL live in a dedicated leaf module that both import from. This rule forbids the latent import cycle in which a package `__init__` aggregates a public surface that its own submodules then need. A static lint rule SHALL enforce it and surface findings under `a2kit lint static`.

#### Scenario: Submodule importing its own package `__init__` is flagged
- **WHEN** `a2kit lint static src/` runs against a file `src/a2kit/packages/<pkg>/<sub>.py` that contains `from a2kit.packages.<pkg> import X` or `from . import X`
- **THEN** a lint finding is emitted naming the offending import

#### Scenario: Importing from a sibling submodule is allowed
- **WHEN** `a2kit lint static src/` runs against a submodule that imports from a sibling module (e.g. `from .formats import FormatName`) or from any other package
- **THEN** no such finding is emitted

#### Scenario: A package `__init__` may import its own submodules
- **WHEN** the rule runs against a package's own `__init__.py` that re-exports symbols from its submodules
- **THEN** no finding is emitted, because the aggregation direction is `__init__` importing submodule, never the reverse
