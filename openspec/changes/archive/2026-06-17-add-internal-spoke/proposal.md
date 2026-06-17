# add-internal-spoke

## Why

a2kit apps that own a **single-writer store** (e.g. a2kay over DuckDB) must run
as one writer process: exactly one process may open the store read-write, and
every other writer must funnel through it. Co-resident **first-party jobs**
(transcription, profile regen) run as *sandboxed subprocesses* (untrusted job
code, per-vault trust) and therefore **cannot open the store** — they must call
back into the writer over an inter-process channel.

That channel must be **private** (not reachable off-host), **authed** (the job
acts as a scoped actor, not a trust-by-channel free pass), and **co-resident**
(same process, same store handle as the public surfaces). a2kit has no such
surface today, and the public MCP/HTTP edge is the wrong door: a first-party job
should not authenticate to its own parent over a network-facing port.

This is **substrate**, not product: any a2kit app with a single-writer store +
sandboxed workers hits it identically. If consumers hand-roll it, every app
re-implements a socket responder + a principal hack — and a2kit's
"no backward-compat / no redundancy" doctrine makes those hand-rolls drift.

The scope is deliberately small: a **spoke** (a local socket door + a dynamic
auth strategy + a client), reusing the existing dispatcher, scopes, `Principal`,
and DI container wholesale. It is **not** a surface-composition framework (that
remains explicitly deferred — see Non-goals).

## What Changes

### 1. `serve` runs a co-resident loopback listener (the chunky piece)

Today `serve --transport=http` runs **one** listener
(`uvicorn.run(parent, host, port)`, `mcp/cli.py`). Add an optional second,
loopback-only listener bound to a **Unix domain socket**, serving the same
`AppRuntime` (so it shares the one DI container and the `SINGLETON` store
handle — single-writer preserved). Both listeners' lifespans enter under the
one `async with runtime:`.

### 2. `AuthTarget` opened beyond `Literal["api", "mcp"]`

`auth/spec.py` pins `AuthTarget = Literal["api", "mcp"]`. Open it so a spoke
surface can be an auth target (e.g. `"internal"`). One-line type change +
fallout.

### 3. Auth-middleware mounting generalized (the no-redundancy cleanup)

`http/build.py:_install_auth_middlewares` is welded: hardcoded
`for_target("api")` + `isinstance(spec, APIKeyAuth)`. Replace with a generic
`AuthSpec.build_middleware()` hook dispatched over `for_target(surface.name)`,
removing the `isinstance` chain. This is the "split auth strategy per surface"
seam and the precondition for a new strategy.

### 4. `TokenAuth` — a dynamic, lease-validating auth strategy

A new `AuthSpec` subclass that validates a presented token against a **live,
mutable lease table** per request (unlike `APIKeyAuth`, whose keys are
materialised once at build). On a hit it publishes a `Principal` carrying the
lease's scopes. The lease table itself is owned by the consumer's runner
(a2kay) — `TokenAuth` reads whatever live set it is handed.

### 5. A supported spoke client

A thin a2kit-supported client a spawned job uses to dial the UDS and call verbs
by canonical name, so jobs do not reach into fastmcp/httpx internals.

## Decisions (settled during exploration)

- **Transport: Unix domain socket**, not same-port `/internal` (a private channel
  must be off-host-unreachable by construction, not merely auth-gated) and not a
  separate TCP port (the socket needs no port management and is local by nature).
- **Key lifetime: revocable lease bound to job liveness**, not a fixed TTL
  (expires mid-job — a transcription run may span a day) and not a permanent key.
  The runner mints at spawn, the lease is validated per request against the live
  table, and the runner revokes on job exit/crash/timeout. → drives `TokenAuth`
  (4) over static `APIKeyAuth`.
- **Identity: scopes, not a new `Principal.kind`.** The lease carries the job
  manifest's scopes (least privilege); `authorize=` gates evaluate them
  uniformly. `Principal` is unchanged.
- **DI: one runtime, shared.** Both listeners build SCOPED children off the one
  root container; the store is `SINGLETON` on the root → a single shared handle.

## Non-goals (explicitly deferred)

- Surface-composition *framework*: user-defined surfaces, N-instances-per-protocol,
  scope-*derived* placement (the matrix stays per-tool), surface-as-persona.
- Surface-aware *behavior* (the `Secret[str]` per-surface rendering / handoff).
- Read-only companions (status bars, query UIs): those run as a separately
  configured read-only app — no spoke, no new substrate.

These are deferred until a second concrete consumer forces each; this change
ships only the single forced primitive.
