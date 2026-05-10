## ADDED Requirements

### Requirement: Decoration-time check rejects all primitive returns

The decoration machinery in `src/a2kit/tool.py` SHALL reject return annotations that are any of the primitive types (`str`, `int`, `float`, `bool`, `bytes`) or `None` with `InvalidToolReturnTypeError` naming the offending type and the tool. The previous behavior of rejecting only `-> str` is generalized.

#### Scenario: int return raises

- **GIVEN** a tool decorated `@a2kit.read()` with return annotation `-> int`
- **WHEN** the module containing the tool is imported
- **THEN** import fails with `InvalidToolReturnTypeError` whose message names `int` and the tool name

#### Scenario: bool return raises

- **GIVEN** a tool with return annotation `-> bool`
- **WHEN** the module is imported
- **THEN** import fails with `InvalidToolReturnTypeError` naming `bool`

#### Scenario: None return raises

- **GIVEN** a tool with return annotation `-> None`
- **WHEN** the module is imported
- **THEN** import fails with `InvalidToolReturnTypeError` naming `NoneType`

#### Scenario: bytes return raises

- **GIVEN** a tool with return annotation `-> bytes`
- **WHEN** the module is imported
- **THEN** import fails with `InvalidToolReturnTypeError` naming `bytes`

#### Scenario: dict return passes

- **GIVEN** a tool with return annotation `-> dict[str, int]`
- **WHEN** the module is imported
- **THEN** decoration completes without error

#### Scenario: BaseModel return passes

- **GIVEN** a tool whose return annotation is a module-scope Pydantic model
- **WHEN** the module is imported
- **THEN** decoration completes without error

### Requirement: Error message points to the antipattern doc

The `InvalidToolReturnTypeError` raised for primitive returns SHALL include the rule code reference (`antipattern #1`) and a one-line guidance ("return a Pydantic model, dict, or list/Page of either").

#### Scenario: Error message guidance

- **WHEN** a primitive-return tool is imported
- **THEN** the raised exception's message includes both the offending type name and the guidance string verbatim
