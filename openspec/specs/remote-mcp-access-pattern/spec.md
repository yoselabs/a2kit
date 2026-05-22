# remote-mcp-access-pattern Specification

## Purpose
TBD - created by archiving change remote-mcp-access-pattern. Update Purpose after archive.
## Requirements
### Requirement: Pattern doc names the canonical shape

The repository SHALL ship `docs/patterns/remote-mcp-access.md` documenting the canonical shape for an a2kit-based remote MCP server that authenticates web-only AI clients with Google per ADR 0011 and exposes operations scoped to the authenticated user. The doc SHALL cover: the `UserSession` per-call DI shape, the workspace-dir convention, the liftability rubric (lift / lift-with-care / don't-lift / never-lift with concrete examples for each), and an inline reference to the `examples/mcp-google-auth/` example as the working source of truth.

#### Scenario: The pattern doc exists and references the example

- **WHEN** a maintainer reads `docs/patterns/remote-mcp-access.md`
- **THEN** the doc names `UserSession`, the workspace-dir hashing rule, and the four-category liftability rubric
- **AND** the doc links to `examples/mcp-google-auth/` as the canonical worked implementation

### Requirement: Example server lifts the authenticated email into verb bodies via DI

The example under `examples/mcp-google-auth/` SHALL wire a per-call DI provider that reads the authenticated user's email from the FastMCP auth state (via `ToolContext`) and constructs a `UserSession` value with at minimum `email: str` and `workspace_dir: Path`. Verbs in the example that take `user: UserSession` SHALL receive an instance whose `email` matches the authenticated identity and whose `workspace_dir` exists on disk and is unique per email.

#### Scenario: A verb receives the authenticated email

- **GIVEN** the example server is running with `StaticTokenVerifier` mapping token `T1` to email `alice@example.com`
- **WHEN** a client invokes the example's `whoami` verb with bearer token `T1`
- **THEN** the response contains `email = "alice@example.com"`
- **AND** the workspace path returned exists on disk

#### Scenario: Two users get distinct workspace dirs

- **GIVEN** the example server is running with token `T1` → `alice@example.com` and token `T2` → `bob@example.com`
- **WHEN** the `whoami` verb is invoked once with each token
- **THEN** the two responses return different `workspace_dir` paths
- **AND** neither path is a prefix of the other

### Requirement: Workspace dirs are named by SHA-256 of the email, not the raw email

The example's per-user workspace directory name SHALL be the first 16 hex characters of `sha256(email.lower().strip())`. The raw email SHALL NOT appear in the directory name. A `_email` file SHALL be written into each workspace on first creation containing the raw email for forensics.

#### Scenario: Workspace dir name is opaque

- **GIVEN** the example server is running with token `T1` → `alice@example.com`
- **WHEN** the `whoami` verb is invoked and the workspace is created
- **THEN** the workspace dir's basename is exactly 16 hex characters
- **AND** the basename is not the email
- **AND** a `_email` file inside the workspace contains `alice@example.com`

### Requirement: CI smoke test exercises the per-user workspace contract end-to-end

The repository SHALL ship a `make example-smoke` (or named-equivalent) target that boots the example server with the `StaticTokenVerifier` escape hatch, exercises one read verb and one write verb under two distinct fixture tokens, and asserts: (a) authenticated emails reach verb bodies, (b) workspaces are isolated per user, (c) write operations performed under token `T1` are not visible to operations performed under token `T2`. The smoke test SHALL complete in under 10 seconds and require no external network access. The smoke test SHALL run on every CI invocation that runs lint or unit tests.

#### Scenario: Smoke test passes on a clean checkout

- **GIVEN** a clean checkout of the repository on the current a2kit version
- **WHEN** a maintainer runs `make example-smoke`
- **THEN** the target exits 0
- **AND** the elapsed time is under 10 seconds
- **AND** no external network calls were issued

#### Scenario: Per-user write isolation holds

- **GIVEN** the smoke test environment with token `T1` → `alice@example.com` and `T2` → `bob@example.com`
- **WHEN** the smoke test issues a write verb under `T1` storing key `k1` with value `v1`
- **AND** then issues a read verb under `T2` for key `k1`
- **THEN** the read under `T2` returns no value (or a value distinct from `v1`)
- **AND** the smoke test asserts this and exits 0

### Requirement: Example is covered by the repository's lint and typecheck

The `examples/mcp-google-auth/` source tree SHALL be included in the repository's existing lint and typecheck targets so that a2kit-side type or API changes that break the example are caught at the framework boundary.

#### Scenario: Lint covers the example

- **WHEN** a maintainer runs `make lint`
- **THEN** files under `examples/mcp-google-auth/` are checked

#### Scenario: Typecheck covers the example

- **WHEN** a maintainer runs `make typecheck` (or the named-equivalent target)
- **THEN** files under `examples/mcp-google-auth/` are checked

### Requirement: Pattern composes existing primitives only — no new a2kit core code

The change SHALL NOT modify any file under `src/a2kit/`. The pattern SHALL compose existing capabilities (`mcp-context-passthrough`, `di-per-call-scope`, `core-composition`). All new code SHALL live under `examples/` and all new prose under `docs/patterns/`.

#### Scenario: No source-tree changes to a2kit core

- **WHEN** the change's diff is inspected against `main`
- **THEN** no files under `src/a2kit/` are added, modified, or removed
- **AND** new files appear only under `docs/patterns/`, `examples/`, `Makefile`, `BACKLOG.md`, and the openspec change directory

