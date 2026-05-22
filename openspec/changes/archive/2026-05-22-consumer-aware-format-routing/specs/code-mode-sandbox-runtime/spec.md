## ADDED Requirements

### Requirement: `call_tool` marshals results into the sandbox as dataclasses

When sandboxed code calls `call_tool`, the result SHALL be marshalled
into the monty sandbox as a dataclass — nested dataclasses for nested
structures — never as a dict and never as a pydantic `BaseModel` (a
`BaseModel` cannot cross the monty boundary). Field access in the
sandbox SHALL therefore be attribute access. The conversion SHALL be
driven by the tool's `ToolDescriptor.return_type`.

#### Scenario: call_tool result supports attribute access

- **WHEN** sandboxed code does `r = await call_tool("get_task", {...})`
- **THEN** fields are reached as `r.title`, not `r["title"]`

#### Scenario: nested Page yields attribute access all the way down

- **GIVEN** a tool annotated `-> Page[Task]`
- **WHEN** sandboxed code calls it
- **THEN** `page.items[0].title` and `page.next_cursor` are valid

### Requirement: a2kit generates monty type-stubs from tool descriptors

a2kit SHALL generate monty type-stubs from the tool descriptors: a
dataclass mirror for each tool's return type and nested item types,
and one `@overload` of `call_tool` keyed on `Literal[<tool name>]` per
tool returning that tool's mirrored type.

#### Scenario: stubs include a dataclass mirror per return type

- **GIVEN** a tool annotated `-> Page[Task]`
- **WHEN** the stubs are generated
- **THEN** they declare dataclass mirrors of `Page` and `Task`

#### Scenario: stubs include one Literal overload per tool

- **GIVEN** registered tools `list_tasks` and `count_tasks`
- **WHEN** the stubs are generated
- **THEN** there is one `@overload` of `call_tool` per tool keyed on
  the tool's name as a `Literal`

### Requirement: Sandbox code is type-checked before execution

The a2kit `SandboxProvider` SHALL type-check the LLM-submitted code
against the generated stubs (monty `type_check=True`) before executing
it. On a type error it SHALL feed the error back to the model for one
retry; if the retry also fails type-checking, the call SHALL fail with
the type error and SHALL NOT execute.

#### Scenario: a misnamed field is rejected before execution

- **WHEN** submitted code accesses a field the return type lacks
- **THEN** the type check rejects it before any execution

#### Scenario: a hallucinated tool name is rejected before execution

- **WHEN** submitted code calls `call_tool` with an unregistered name
- **THEN** the type check rejects it (no matching overload)

#### Scenario: a type error triggers exactly one retry

- **WHEN** the first submission fails type-checking
- **THEN** the type error is fed back and the model is asked once more
- **AND** a second failure fails the call without executing

### Requirement: a2kit owns the `execute` description and output contract

a2kit SHALL override CodeMode's `execute_description` with a contract
that states: `call_tool` results are objects with attribute access;
the answer is produced by ending the code with a bare expression and a
top-level `return` SHALL NOT be used; a flat list of records is
preferred. The description SHALL be a versioned artifact covered by an
eval.

#### Scenario: the execute description states the output contract

- **WHEN** the MCP server is built with code mode on
- **THEN** the `execute` tool's description states the
  bare-expression output contract and attribute-access rule

#### Scenario: code ending with a bare expression produces the answer

- **WHEN** sandboxed code defines a function and ends with
  `await that_function()` as its last line
- **THEN** that expression's value is the `execute` result
