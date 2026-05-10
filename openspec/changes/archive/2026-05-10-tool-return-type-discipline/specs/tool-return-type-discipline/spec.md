## ADDED Requirements

### Requirement: Lint rule `A2K-LOCAL-RETURN-MODEL` flags non-module-scope BaseModel return types

The static lint package SHALL ship a rule with code `A2K-LOCAL-RETURN-MODEL` that fires when a function decorated with `@a2kit.read`, `@a2kit.write`, or `@a2kit.list_` declares a return annotation whose root identifier resolves to a `pydantic.BaseModel` subclass defined inside a function, classmethod, or closure scope (i.e. not at module scope) within the same module. The rule SHALL also fire when the return annotation is a generic `Subscript` (e.g. `Page[Result]`, `list[Result]`) and a slice argument resolves to a non-module-scope `BaseModel`.

#### Scenario: In-function BaseModel as direct return type

- **GIVEN** a module containing
  ```python
  def make_router():
      class Result(BaseModel):
          ok: bool
      class R(a2kit.Router):
          @a2kit.read()
          async def t(self) -> Result: ...
  ```
- **WHEN** the lint rule runs
- **THEN** a `LintMessage` with rule `A2K-LOCAL-RETURN-MODEL` is emitted at the line of the `-> Result` annotation

#### Scenario: In-function BaseModel as generic parameter

- **GIVEN** a module where `Result` is defined inside a function and a tool returns `Page[Result]`
- **WHEN** the lint rule runs
- **THEN** a `LintMessage` is emitted referencing both `Result` and the annotation site

#### Scenario: Module-scope BaseModel passes

- **GIVEN** a module with `class Result(BaseModel): ...` at module level used as a tool return type
- **WHEN** the lint rule runs
- **THEN** no `A2K-LOCAL-RETURN-MODEL` message is emitted for that module

#### Scenario: Imported BaseModel passes (out of jurisdiction)

- **GIVEN** a tool whose return type is `OtherModule.Result` imported from a different module
- **WHEN** the lint rule runs
- **THEN** no `A2K-LOCAL-RETURN-MODEL` message is emitted

#### Scenario: TYPE_CHECKING block exempted

- **GIVEN** a `BaseModel` defined inside `if TYPE_CHECKING:` and used as a tool return type
- **WHEN** the lint rule runs
- **THEN** no `A2K-LOCAL-RETURN-MODEL` message is emitted

#### Scenario: Inner class of module-scope class passes

- **GIVEN** `class Outer:` at module scope with `class Inner(BaseModel): ...` defined inside it, used as a tool return type
- **WHEN** the lint rule runs
- **THEN** no `A2K-LOCAL-RETURN-MODEL` message is emitted (the class is reachable via module-scope `Outer.Inner`)

### Requirement: Lint rule registered in static rule set

The rule SHALL be wired into `src/a2kit/packages/lint/static.py` in the same registration list used by the existing rules (e.g. `A2K-LDD-REPORT-TYPE`), with constant `A2K_LOCAL_RETURN_MODEL = "A2K-LOCAL-RETURN-MODEL"` exported via the package's `__all__`.

#### Scenario: Rule is invoked by the linter

- **WHEN** the lint entry point runs against a project
- **THEN** the rule executes for every Python file under `src/` and emits messages alongside the other rules

### Requirement: Decoration-time runtime check raises `InvalidToolReturnTypeError`

The decoration machinery in `src/a2kit/tool.py` (which already runs `_check_return` for antipattern #1) SHALL also reject return types that are non-module-scope `BaseModel` subclasses. The check SHALL walk generic arguments (e.g. `Page[Result]`, `list[Result]`) and inspect the root model class. The check SHALL use the presence of `<locals>` in `cls.__qualname__` as the authoritative signal that the class was defined in a function body. On detection, the framework SHALL raise `InvalidToolReturnTypeError` with a message naming the offending class and citing rule code `A2K-LOCAL-RETURN-MODEL`.

#### Scenario: Decoration raises for in-function class

- **GIVEN** a tool method decorated with `@a2kit.read()` whose return annotation is a `BaseModel` subclass with `<locals>` in its `__qualname__`
- **WHEN** the module containing the tool is imported
- **THEN** import fails with `InvalidToolReturnTypeError` whose message names the offending class and rule code `A2K-LOCAL-RETURN-MODEL`

#### Scenario: Module-scope class passes decoration

- **GIVEN** a tool method whose return annotation is a module-scope `BaseModel`
- **WHEN** the module is imported
- **THEN** decoration completes without error

#### Scenario: Generic carrier inspected

- **GIVEN** a tool method whose return annotation is `Page[Result]` where `Result` has `<locals>` in its `__qualname__`
- **WHEN** the module is imported
- **THEN** import fails with `InvalidToolReturnTypeError` naming `Result`

### Requirement: Documentation references the enforced rule

`ANTIPATTERNS.md` entry #2 SHALL reference `A2K-LOCAL-RETURN-MODEL` and `InvalidToolReturnTypeError` as enforced mechanisms, and SHALL NOT describe the rule as advisory or as a "convention if you're not running the linter."

#### Scenario: Doc references the rule

- **WHEN** a reader opens `ANTIPATTERNS.md` to entry #2
- **THEN** the entry names `A2K-LOCAL-RETURN-MODEL`, names the runtime exception (`InvalidToolReturnTypeError`), and describes both as enforced
