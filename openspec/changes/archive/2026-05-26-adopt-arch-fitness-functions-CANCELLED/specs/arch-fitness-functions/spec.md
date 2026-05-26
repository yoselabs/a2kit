## ADDED Requirements

### Requirement: pytest-archon hosts AST-level / call-site architectural rules

The repository SHALL carry a `tests/architecture/` package containing pytest-archon rule modules. Each rule SHALL be expressible as one pytest function (or a small set of related functions in one module). The suite SHALL be runnable as `uv run pytest tests/architecture -q` and SHALL be wired into the default lint gate. Architectural invariants that are AST-level or call-site assertions SHALL live in this package — NOT scattered across `tests/test_*.py`.

#### Scenario: Archon suite collects under standard pytest

- **WHEN** `uv run pytest tests/architecture -q` runs
- **THEN** every module under `tests/architecture/` is collected
- **AND** at least three rules execute (init-purity, tool-returns-pydantic, no-dict-str-any-on-internal-dataclasses)

#### Scenario: New architectural rule lives under tests/architecture/

- **WHEN** a contributor adds a new structural invariant (e.g. "only manifest-bearing modules under a plugin surface")
- **THEN** the rule SHALL be added as a new file under `tests/architecture/`
- **AND** it SHALL NOT be added as a standalone `tests/test_*.py`

### Requirement: `__init__.py` purity rule rejects `_`-prefixed re-exports

The rule `test_packages_init_is_only_public_surface` SHALL fail when any `src/a2kit/packages/<name>/__init__.py` re-exports a `_`-prefixed name through `__all__` or through a `from ._x import _name` re-export. The rule complements `A2K-PKG-FRONT-DOOR` (which catches `_`-prefixed imports past the front door) by catching the reverse direction: private names leaking out through it.

#### Scenario: Private re-export through `__all__` fails

- **GIVEN** a package `packages/foo/__init__.py` containing `__all__ = ["public_thing", "_private_thing"]`
- **WHEN** `test_packages_init_is_only_public_surface` runs
- **THEN** the rule fails and names `_private_thing` as the offending re-export

#### Scenario: Private re-export through `from ._x import _name` fails

- **GIVEN** a package `packages/foo/__init__.py` containing `from ._impl import _internal_helper`
- **WHEN** `test_packages_init_is_only_public_surface` runs
- **THEN** the rule fails and names `_internal_helper` as the offending re-export

### Requirement: Tool-return-type rule rejects non-pydantic returns

The rule `test_tool_returns_are_pydantic` SHALL fail when any `@tool` / `@app.read` / `@app.write` / `@app.list_` decorated function has a return annotation resolving to `str`, `dict`, `dict[..., ...]`, `list`, or any non-pydantic structural type. The rule uses AST inspection (decorator names + return annotation), not runtime introspection, so it catches decoration-time discipline regardless of whether the tool is wired into a runtime.

#### Scenario: `str` return annotation fails

- **GIVEN** a function decorated `@app.read("get_thing")` with return annotation `-> str`
- **WHEN** the rule runs
- **THEN** the rule fails and names the function + its location

#### Scenario: Pydantic return annotation passes

- **GIVEN** the same function with return annotation `-> Thing` where `Thing` is a `BaseModel` subclass
- **WHEN** the rule runs
- **THEN** the rule passes

### Requirement: `dict[str, Any]` rule rejects untyped fields on internal dataclasses with allowlist

The rule `test_no_dict_str_any_on_internal_dataclasses` SHALL fail when any `@dataclass`, `@dataclass(frozen=True)`, or `BaseModel` subclass defined under `src/a2kit/packages/` has a field annotation `dict[str, Any]` UNLESS the field is named in the rule module's allowlist. The allowlist SHALL document each entry inline (one short line stating why the `Any` is load-bearing at that site — typically because the field carries a wire payload whose schema is owned by an external system).

#### Scenario: Unallowlisted `dict[str, Any]` field fails

- **GIVEN** a dataclass `class Foo` defined in `packages/X/Y.py` with field `payload: dict[str, Any]` not in the allowlist
- **WHEN** the rule runs
- **THEN** the rule fails and names `Foo.payload` + its location

#### Scenario: Allowlisted field passes

- **GIVEN** the same dataclass with `("packages.mcp._wrappers", "Foo", "payload")` in the allowlist (with a one-line reason)
- **WHEN** the rule runs
- **THEN** the rule passes

### Requirement: `make arch` is the umbrella structural gate

The `Makefile` SHALL define an `arch` target invoking `uv run pytest tests/architecture -q`. `make lint` (or the project's umbrella check target) SHALL invoke `make arch` and fail on its non-zero exit. CI SHALL fail on `make arch` non-zero exit.

#### Scenario: make arch wires the archon suite

- **WHEN** `make arch` runs
- **THEN** the pytest-archon suite runs
- **AND** the target exits 0 only if every rule passes

#### Scenario: make lint depends on make arch

- **WHEN** `make lint` runs
- **THEN** `make arch` runs as part of it
- **AND** a failure in the archon suite causes `make lint` to exit non-zero
