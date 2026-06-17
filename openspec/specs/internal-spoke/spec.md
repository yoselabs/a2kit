# internal-spoke Specification

## Purpose
TBD - created by archiving change add-internal-spoke. Update Purpose after archive.
## Requirements
### Requirement: First-party processes reach the writer over an authed local spoke

a2kit SHALL provide a way for a first-party, co-resident process (e.g. a
sandboxed job spawned by the app's runner) to call the app's projected verbs over
a **local, non-network** channel (a Unix domain socket), authenticated as a
**scoped actor**, without traversing the public network edge auth.

A verb call over the spoke SHALL receive the **same** dispatcher treatment as a
public call — validation, audit, `authorize=`, `if_version`, typed-error mapping —
keyed off a `Principal` published by the spoke's auth strategy (`TokenAuth`). The
spoke SHALL NOT mount the public edge auth (OAuth / API-key for `api`/`mcp`); it
mounts only its own `target`-matched strategy. The spoke SHALL be unreachable
off-host (a Unix socket has no network address) and file-permission gated
(`0600`).

The actor's identity and permissions SHALL be carried as `Principal` scopes
(least privilege), not as a new `Principal` field or `kind`. The `Principal`
type SHALL be unchanged by this capability.

#### Scenario: A job acts as a scoped actor over the spoke

- **WHEN** a spawned job presents its lease token and invokes a verb over the UDS
- **THEN** the call dispatches with a `Principal` carrying the lease's scopes,
  passes/fails `authorize=` on those scopes, is audited with that subject, and
  writes through the one shared store handle

#### Scenario: The spoke is not the public edge

- **WHEN** a caller without a valid spoke token connects to the socket
- **THEN** the call is rejected, and no public OAuth/API-key path is consulted

### Requirement: A supported spoke client calls verbs by canonical name

a2kit SHALL expose a supported client entry that dials the spoke socket and
invokes verbs by their canonical name (e.g. `client.invoke(name, **kwargs)`),
so consumers do not depend on fastmcp/httpx internals or hand-roll socket code.
The client's reachable verb set SHALL match the spoke surface's projected
catalog (the same canonical names), with no separate tool catalog.

#### Scenario: Client round-trips a verb over the socket

- **WHEN** a job uses the supported client with its socket path and token to
  invoke a verb by canonical name
- **THEN** the call reaches the dispatcher over the UDS and returns the verb's
  result, using only a2kit's public client API

