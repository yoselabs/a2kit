## MODIFIED Requirements

### Requirement: `--json` flag mirrors structuredContent envelope to stdout

The CLI SHALL accept a `--json` flag on every tool invocation. With `--json`:

- **Success**: stdout receives `json.dumps(model_dump)` (the canonical serialization, identical to MCP `content[0].text` on success). stderr remains silent. Exit code 0.
- **Error**: stdout receives `{"error": <envelope as dict>}` (the canonical envelope, identical to MCP `structuredContent.error` and HTTP body). stderr remains silent. Exit code from kind map.

The `--json` flag is intended for piping to other tools; it makes the CLI fully machine-readable.

`--json` and `--format` SHALL be mutually exclusive. Passing both SHALL raise `BadParameter` naming both flag names and stating that `--json` is the end-to-end machine channel while `--format` chooses the formatter pipeline output.

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

#### Scenario: --json and --format are mutually exclusive

- **GIVEN** any tool
- **WHEN** invoked with both `--json` and `--format=json`
- **THEN** `BadParameter` is raised before tool dispatch
- **AND** the error message names both flags
