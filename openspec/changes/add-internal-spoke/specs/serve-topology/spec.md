## ADDED Requirements

### Requirement: Co-resident loopback (UDS) listener shares the one runtime

`serve` (http path) SHALL support an optional second listener bound to a **Unix
domain socket** (the "spoke"), in addition to the public TCP listener. When the
spoke is enabled, `serve` SHALL build the `AppRuntime` **exactly once** and serve
**both** listeners from that single runtime, so they share the one DI root
container and therefore the one `SINGLETON` store handle (single-writer
preserved). The spoke socket SHALL be created with `0600` permissions.

Both listeners' lifespans SHALL be entered under a single `async with runtime:`
(the runtime entered once, exited last), as with the existing multi-surface
parent. The public TCP listener and its mounted surfaces (MCP/HTTP) and their
auth SHALL be unchanged whether or not the spoke is enabled.

The spoke SHALL serve the dispatcher-backed verb surface (same dispatcher, same
validation, audit, `authorize=`, `if_version`, typed errors as the public
surfaces) and SHALL NOT expose a second tool catalog: projected verbs SHALL carry
the identical canonical names served on the public API surface.

#### Scenario: Spoke and public listener share one store handle

- **WHEN** `serve` runs with the spoke enabled and a verb is invoked over the UDS
- **THEN** the call resolves through the same `AppRuntime` and writes through the
  same `SINGLETON` store instance that a TCP call resolves, with no second store
  handle opened

#### Scenario: Public surfaces unaffected by the spoke

- **WHEN** the spoke is enabled
- **THEN** the public TCP listener's MCP/HTTP mounts and their auth behave
  identically to a spoke-disabled run

#### Scenario: Spoke disabled by default

- **WHEN** `serve` runs without the spoke option
- **THEN** only the public TCP listener is started and no Unix socket is created

## MODIFIED Requirements

### Requirement: stdio `serve` is a single-protocol MCP surface

The default `serve` transport (stdio) SHALL serve the MCP surface only,
because a stdio pipe cannot multiplex more than one protocol. Surface
narrowing on the `http` transport is expressed with `--select 'surface=...'`
(the `runtime-tool-selection` capability), not with dedicated surface flags.

#### Scenario: stdio still serves MCP

- **WHEN** the app is started with `serve` and no transport flag
- **THEN** the MCP surface is served over stdio exactly as before this change

## REMOVED Requirements

### Requirement: Surface selection via `--mcp-only` and `--rest-only`

**Reason**: the `--mcp-only` / `--rest-only` flags do not exist — surface
narrowing is done with `--select 'surface=mcp'` / `--select 'surface=api'`
(the `runtime-tool-selection` selector). The canonical spec carried these
removed flags as stale text; this change deletes the requirement. The
`http` multiplex (both surfaces by default, narrowed with `--select`) is
covered by the "`serve --transport=http` runs a multiplexed server"
requirement above.
