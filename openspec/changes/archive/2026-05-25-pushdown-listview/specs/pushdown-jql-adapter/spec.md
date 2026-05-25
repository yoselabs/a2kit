## ADDED Requirements

### Requirement: JQL adapter package is opt-in

`a2kit.packages.pushdown_jql` SHALL be opt-in via
`pip install 'a2kit[pushdown-jql]'`. The package SHALL declare
`httpx>=0.27` (or higher minimum) as its sole runtime dep.

#### Scenario: Extra exists in pyproject
- **WHEN** `pyproject.toml [project.optional-dependencies]` is inspected
- **THEN** `pushdown-jql = ["httpx>=0.27"]` (or analogous) is declared

### Requirement: `JqlPushdown` translates CEL to JQL

The adapter SHALL translate CEL filter expressions to JQL where the
mapping is unambiguous:

- `project == "API"` → `project = "API"`
- `status != "Done"` → `status != "Done"`
- `priority > 3` → `priority > 3`
- `created > "2026-01-01"` → `created > "2026-01-01"`
- `labels in ["urgent", "p0"]` → `labels in ("urgent", "p0")`

Boolean compounds (`&&`, `||`, `!`) SHALL translate to JQL `AND`,
`OR`, `NOT`. Untranslatable CEL SHALL raise `PushdownNotSupported`.

#### Scenario: Simple equality maps to JQL
- **WHEN** `JqlPushdown.filter(state, "project == 'API'")` is invoked
- **THEN** the state's accumulated JQL is `project = "API"`

#### Scenario: Compound boolean maps
- **WHEN** the filter is `project == 'API' && status != 'Done'`
- **THEN** the JQL is `project = "API" AND status != "Done"`

### Requirement: JQL adapter maps fields + page to REST query params

`fields(state, names)` SHALL set the REST `fields=` query parameter
to a comma-separated list. `page(state, cursor, size)` SHALL set
`startAt=<cursor>` and `maxResults=<size>`. Cursor format: integer
offset as a decimal string (Atlassian's native semantics).

#### Scenario: Field projection
- **WHEN** `fields(state, ("id", "summary", "assignee"))` is called
- **THEN** the resulting state has REST query param `fields=id,summary,assignee`

#### Scenario: Pagination with cursor
- **WHEN** `page(state, cursor="50", size=25)` is called
- **THEN** the resulting state has REST query params `startAt=50` and `maxResults=25`

### Requirement: `execute` issues an authenticated REST call

`JqlPushdown.execute(state)` SHALL issue an HTTP GET (or POST for
large JQL) to the connection's Atlassian REST endpoint with the
accumulated JQL + query params, parse the response, and return
`list[dict]` of issues / pages.

#### Scenario: Execute returns issues from response
- **WHEN** the configured Atlassian endpoint returns a `{"issues": [...]}` JSON body
- **THEN** `execute` returns the `"issues"` array

#### Scenario: Cassette tests cover execute
- **WHEN** the test suite runs against recorded `vcrpy` cassettes
- **THEN** `JqlPushdown.execute` is exercised end-to-end against the recorded HTTP traffic; no real Atlassian call is required for CI
