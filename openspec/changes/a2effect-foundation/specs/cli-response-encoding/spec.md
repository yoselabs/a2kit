## ADDED Requirements

### Requirement: CLI error rendering goes to stderr with kind-mapped exit code

When a tool invocation via the CLI propagates an `AppError` (or subclass), the CLI SHALL:

- Write the prose form (kind label + message + hint, per `error-envelope-rendering`) to stderr.
- Leave stdout empty (unless `--json` is passed; see next requirement).
- Exit with the code from `AppError.cli_exit_code` if set, else from the `kind` map (`input=2, auth=77, policy=77, infra=75, bug=70` per sysexits.h).

Stack traces SHALL NOT be written to stderr by default. The `--explain` flag (deferred to a follow-up) MAY surface them.

#### Scenario: NotFound exits 2 with prose on stderr

- **GIVEN** a tool body raising `NotFound("memory id 'abc' does not exist")` with class-level `hint = "verify..."`
- **WHEN** the user runs `a2kit memory fetch --id abc`
- **THEN** the process exit code is `2`
- **AND** stderr contains exactly the prose form:
  ```
  Input error (NotFound): memory id 'abc' does not exist

  Hint: verify...
  ```
- **AND** stdout is empty

#### Scenario: InfrastructureError exits 75

- **GIVEN** a tool body raising `InfrastructureError(...)` (kind=infra)
- **WHEN** invoked via CLI
- **THEN** exit code is `75`

### Requirement: `--json` flag mirrors structuredContent envelope to stdout

The CLI SHALL accept a `--json` flag on every tool invocation. With `--json`:

- **Success**: stdout receives `json.dumps(model_dump)` (the canonical serialization, identical to MCP `content[0].text` on success). stderr remains silent. Exit code 0.
- **Error**: stdout receives `{"error": <envelope as dict>}` (the canonical envelope, identical to MCP `structuredContent.error` and HTTP body). stderr remains silent. Exit code from kind map.

The `--json` flag is intended for piping to other tools; it makes the CLI fully machine-readable.

#### Scenario: --json on success emits canonical JSON

- **GIVEN** a tool returning `Memory(id="x", text="hi")`
- **WHEN** invoked with `--json`
- **THEN** stdout is `{"id":"x","text":"hi"}` (compact JSON, no trailing newline beyond pipe convention)
- **AND** stderr is empty
- **AND** exit code is 0

#### Scenario: --json on error emits envelope

- **GIVEN** the same tool raising `NotFound(...)`
- **WHEN** invoked with `--json`
- **THEN** stdout is `{"error":{"type":"NotFound","kind":"input",...,"envelope_version":"1"}}`
- **AND** stderr is empty
- **AND** exit code is from the kind map

### Requirement: `--help` auto-generates parameter and raises documentation

For every CLI subcommand corresponding to a registered tool, the CLI SHALL auto-generate `--help` text from the tool's annotation:

- **Usage line**: `Usage: a2kit <router> <tool> [OPTIONS]` derived from the slug and tool name.
- **Description**: the tool's docstring summary (first line).
- **Options**: one entry per input parameter, derived from the inputSchema; required parameters marked `(required)`.
- **Returns**: the bare return type (with `Raises(...)` stripped); for pydantic models, a tree of fields with types.
- **Errors**: one entry per type in `descriptor.raises`, formatted as `<TypeName> (<kind>, exit <cli_exit_code>) <hint>`.

The `--help` output SHALL include the `--json` flag in the options list with its standard description.

#### Scenario: --help shows declared errors with kind and exit code

- **GIVEN** a tool annotated `-> Annotated[Memory, Raises(NotFound, InvalidId)]` with class metadata: `NotFound(kind="input", cli_exit_code=2, hint="verify the id...")` and `InvalidId(kind="input", cli_exit_code=2, hint=None)`
- **WHEN** the user runs `a2kit memory fetch --help`
- **THEN** the output contains an "Errors:" section listing:
  - `NotFound (input, exit 2) verify the id...`
  - `InvalidId (input, exit 2)`

### Requirement: `--schema` flag emits full ToolDescriptor as JSON

The CLI SHALL accept a `--schema` flag on every tool invocation that, when passed, prints the full tool descriptor as JSON to stdout and exits 0 without invoking the tool. The schema SHALL include at minimum:

- `name`: the tool name.
- `description`: the docstring summary.
- `inputSchema`: the JSON Schema for the tool's parameters.
- `outputSchema`: the auto-generated `oneOf[BareReturnSchema, ErrorEnvelopeSchema]` per `error-envelope-rendering`.
- `raises`: array of descriptor entries per declared `AppError` subclass: `{type, kind, retryable, hint, http_status, cli_exit_code}`.

This SHALL be the canonical machine-readable contract for the tool consumable by codegen, documentation generation, and discovery tools.

#### Scenario: --schema emits all descriptor fields

- **GIVEN** a tool annotated `-> Annotated[Memory, Raises(NotFound, InvalidId)]`
- **WHEN** the user runs `a2kit memory fetch --schema`
- **THEN** stdout contains a JSON object with `name`, `description`, `inputSchema`, `outputSchema`, and `raises` keys
- **AND** the `outputSchema` is the `oneOf` union per the rendering requirement
- **AND** the `raises` array contains both `NotFound` and `InvalidId` entries with all per-class metadata fields
- **AND** the tool body is NOT invoked

### Requirement: `list-tools` discovery command

The CLI SHALL provide a top-level `a2kit list-tools` command that prints every registered tool's name, router slug, verb (read/write/list_), and one-line description. The `--json` form SHALL emit the full set as a JSON array.

#### Scenario: list-tools shows every tool

- **GIVEN** an app with tools `memory.fetch`, `memory.remember`, `notes.search`
- **WHEN** the user runs `a2kit list-tools`
- **THEN** stdout contains a row for each tool with name, router slug, verb, and description
