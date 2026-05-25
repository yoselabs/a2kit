## ADDED Requirements

### Requirement: SQL adapter package is opt-in

`a2kit.packages.pushdown_sql` SHALL be opt-in via
`pip install 'a2kit[pushdown-sql]'`. The package SHALL have zero hard
runtime dependencies beyond stdlib (`sqlite3` is built-in); database
drivers are user-supplied.

#### Scenario: Optional install path
- **WHEN** `pyproject.toml [project.optional-dependencies]` is inspected
- **THEN** a `pushdown-sql = [...]` extra exists (may be empty list if no extra deps required)

#### Scenario: Lazy import
- **WHEN** `import a2kit.packages.pushdown_sql` is run
- **THEN** no DB driver (psycopg, asyncpg, etc.) is imported as a side effect

### Requirement: `SqlPushdown` implements the `Pushdown` Protocol

`a2kit.packages.pushdown_sql.SqlPushdown` SHALL implement
`Pushdown[SqlQueryState]` where `SqlQueryState` is a typed builder
(table, where-clauses, select-columns, limit, offset).

#### Scenario: Protocol conformance
- **WHEN** `isinstance(SqlPushdown(...), a2kit.pushdown.Pushdown)` is evaluated
- **THEN** the result is True

### Requirement: CEL → SQL translation covers basic ops

The SQL adapter SHALL translate the following CEL constructs to SQL
`WHERE` clauses with parameterized placeholders:

- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Boolean: `&&`, `||`, `!`
- Membership: `field in ["a", "b"]`
- Field access: `field` (single level)

Untranslatable CEL SHALL raise `PushdownNotSupported`.

#### Scenario: Equality compiles to parameterized SQL
- **WHEN** `SqlPushdown.filter(state, "project == 'API'")` is invoked
- **THEN** the resulting state's `where` clause has `project = ?` with parameter `'API'` (no string concatenation of user input)

#### Scenario: Boolean compounds compile
- **WHEN** the filter is `status == 'open' && priority > 3`
- **THEN** the resulting state's where clause is `status = ? AND priority > ?` with parameters `('open', 3)`

#### Scenario: Function calls raise PushdownNotSupported
- **WHEN** the filter is `now() - created < duration("1d")`
- **THEN** the adapter raises `PushdownNotSupported`

### Requirement: SQL adapter parameterizes all user input

The translator SHALL NOT concatenate user-supplied strings into SQL.
All filter values SHALL flow as parameter binds.

#### Scenario: SQL injection prevented
- **WHEN** the filter is `name == "'; DROP TABLE users; --"`
- **THEN** the resulting SQL has `name = ?` with the literal string as a bound parameter; no parsing as SQL syntax occurs

### Requirement: pagination via cursor + size

`SqlPushdown.page(state, cursor, size)` SHALL implement
`LIMIT size OFFSET <decoded cursor>`. Cursor format: base64-encoded
non-negative integer offset.

#### Scenario: First page has empty cursor
- **WHEN** `page(state, cursor=None, size=20)` is called
- **THEN** the resulting state has `limit=20, offset=0`

#### Scenario: Subsequent page decodes cursor
- **WHEN** `page(state, cursor="MjA=" (base64 of "20"), size=20)` is called
- **THEN** the resulting state has `limit=20, offset=20`
