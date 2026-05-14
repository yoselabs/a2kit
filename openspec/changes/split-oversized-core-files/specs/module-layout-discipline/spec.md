# module-layout-discipline — split-oversized-core-files delta

## ADDED Requirements

### Requirement: Teardown topology SHALL live in its own module

The DI teardown topology SHALL live in `src/a2kit/packages/di/teardown.py` (factory-graph traversal, Kahn-with-cycle-break ordering algorithm, cycle-break WARN logging). Concretely, the algorithm lives in
`src/a2kit/packages/di/teardown.py`. `Container` methods that touch
teardown (`register_singleton(..., teardown=...)`,
`teardown_order()`) SHALL delegate to this module rather than embed
the algorithm inline. The split exists so the DI core file stays
under the A2K014 SLOC budget and so the teardown algorithm has a
single location for future readers.

#### Scenario: Teardown helper importable from its module

- **WHEN** consumer code or tests do `from a2kit.packages.di.teardown import teardown_order`
- **THEN** the import succeeds and the symbol resolves to the topological-order function

#### Scenario: container.py stays under SLOC budget

- **WHEN** `uv run a2kit lint static src/` runs
- **THEN** `src/a2kit/packages/di/container.py` does not emit an A2K014 warning, and the file carries no `# noqa: A2K014` suppression

### Requirement: Timeout parsing helper SHALL live in its own module

The verb-decorator `timeout=` value-parsing logic SHALL live in `src/a2kit/_timeout.py` (the `_parse_timeout` function plus its suffix-multiplier table). The verb decorators in `src/a2kit/tool.py`
SHALL import from this module rather than define the parser inline.
The split exists so the verb-decorator file stays under the A2K014
SLOC budget and so the parsing logic has a single location for
future readers.

#### Scenario: Timeout helper importable from its module

- **WHEN** consumer code or tests do `from a2kit._timeout import _parse_timeout`
- **THEN** the import succeeds and the symbol resolves to the parser function

#### Scenario: tool.py stays under SLOC budget

- **WHEN** `uv run a2kit lint static src/` runs
- **THEN** `src/a2kit/tool.py` does not emit an A2K014 warning, and the file carries no `# noqa: A2K014` suppression
