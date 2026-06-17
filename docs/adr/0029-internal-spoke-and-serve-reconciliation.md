---
id: "0029"
status: accepted
date: 2026-06-17
last_reviewed: 2026-06-17
supersedes: []
superseded_by: null
tags: [surface, auth, serve, security, architecture, jobs, http]
deciders: [Denis Tomilin]
---

# ADR 0029: Internal spoke (UDS + lease auth) and serve reconciliation

## Status

Accepted, 2026-06-17. Delivered by the OpenSpec change `add-internal-spoke`
(applied and archived as `2026-06-17-add-internal-spoke`); confirmed by the
human (Constitution Phase A). Touches the Tier-2
public surface (adds `a2kit.spoke`), so it **extends ADR 0004**'s tier
list; it does not supersede it.

## Summary

In one sentence: first-party, co-resident jobs reach the single-writer
core over a private Unix-domain-socket **spoke** — a second listener
sharing the one `serve` runtime, authenticated by a revocable lease
token — and along the way `serve` is reconciled to the one canonical
multiplex command the `serve-topology` spec already mandates.

## The problem

a2kay runs the app in `serve` mode and spawns sandboxed jobs
(transcription, enrichment) that must call verbs **back** into the core
to persist results. Single-writer DuckDB forbids a second writer
process, so jobs cannot own a parallel copy of the store — they must
funnel writes through the one writer. They also must not traverse the
public network edge auth (OAuth / API key) to do first-party work, and
the channel must not be reachable off-host.

While grounding the design we found the serve surface had drifted:

- The **wired** CLI `serve` (`cli/_serve.py::register_serve`, Typer)
  served **MCP-only** over http — it never used `build_parent_app`,
  silently violating the canonical `serve-topology` spec.
- The **spec-compliant** multiplex (`mcp/cli.py::build_serve_command`,
  Click) was **orphaned dead code** with a stale docstring claiming
  `build_full_cli` materialised it (it does not).

A spoke that "shares the public listener's runtime" had no real runtime
to share until this drift was resolved.

## What we decided

1. **Transport = Unix domain socket, not a second TCP port.** A UDS has
   no network address (off-host-unreachable by construction) and is
   filesystem-permission gated. The socket node is created `0600`
   (umask-narrowed across `bind`, `chmod` after as belt-and-suspenders).

2. **Auth = a revocable lease, not static keys, not a fixed TTL.** New
   `TokenAuth(AuthSpec)` (`target="internal"`) calls a consumer-supplied
   `resolve(token) -> Principal | None` **per request**. The runner
   mints a lease at job spawn and revokes it at exit; revocation takes
   effect on the next call, and a long-running job (a day-long
   transcription) never expires mid-span. a2kit does **not** own the
   lease table or its lifecycle — `TokenAuth` holds only the `resolve`
   closure, keeping the table (and any secret) outside a2kit and outside
   the synced vault.

3. **Privilege rides on `Principal` scopes, not a new field.** The
   `Principal` type is unchanged; a job acts as a least-privilege scoped
   actor, evaluated by `authorize=` uniformly with every other surface.

4. **One runtime, two listeners.** `serve` builds the `AppRuntime` once
   and enters it once (`async with runtime:`); the public listener and
   the spoke run under one `asyncio.gather`. `build_parent_app` gained
   `enter_runtime=False` so the caller owns the single lifecycle, and
   both listeners share the one DI root container → the one `SINGLETON`
   store handle. Single-writer is preserved.

5. **Auth mount is generic.** `AuthSpec` grew `build_middleware()`;
   `_install_auth_middlewares` now iterates `registry.for_target(target)`
   and calls `spec.build_middleware()` — the `isinstance(APIKeyAuth)`
   weld and the hardcoded `"api"` are gone. `AuthTarget` is opened from
   `Literal["api","mcp"]` to an open `str` so `"internal"` (and future
   consumer surfaces) can be auth targets. This is both the enabler and
   the no-redundancy cleanup (AGENTS.md §2).

6. **Serve is reconciled onto one command.** The wired Typer `serve`
   http path now runs the `build_parent_app` multiplex (MCP **and** API;
   `--select` narrows to one), with the serve knobs (`--compact` /
   `--tools` / code-mode) threaded into the MCP build via `mcp_options`
   so nothing silently no-ops. `--internal-uds PATH` adds the spoke in
   parallel, in either transport mode. The orphaned Click
   `build_serve_command` + its test are **deleted** (AGENTS.md §1/§2).

7. **Supported client.** `a2kit.spoke.client(socket_path, token)`
   (Tier-2 facade over `a2kit.packages.spoke`) dials the socket and
   `invoke(name, **kwargs)`s verbs by canonical name. It carries no
   catalog of its own — the reachable set is exactly the API surface's
   projected catalog; an unprojected name 404s. Jobs never import
   `httpx`/`fastmcp` internals.

## The write-serialization caveat (consumer obligation)

Two listeners means concurrent callers (an agent over MCP **and** a job
over the UDS) hit the one `SINGLETON` store handle. The shared singleton
gives the *handle*, not concurrency safety. a2kay MUST:

1. **Serialize writes** at the handle (async lock / single write-task).
2. **Write long jobs in short, per-file transactions**, releasing the
   writer between units. Lease validity (may be a day) and write-lock
   holding (per-file, brief) are separate concerns — a day-long job MUST
   NOT hold the writer for a day or it starves the public surfaces.

## Deferred (recorded to prevent scope creep)

- **Surface-composition framework** — per-router/per-persona surface
  spawning, scope-derived placement, N-listeners-per-protocol,
  surface-aware behavior (`Secret[str]` link-vs-inline). The spoke is a
  spoke, not a framework.
- **Peer-cred hardening** (`SO_PEERCRED` / `getpeereid` on accept) —
  investigated and deferred. Two concrete blockers: (1) uvicorn's ASGI
  abstraction does not expose the per-connection socket to middleware
  (the ASGI `scope` carries only `client`, `None` for a UDS), so reading
  peer creds needs a custom uvicorn `Protocol` subclass or a raw-asyncio
  UDS server reimplementing ASGI — invasive and version-coupled; (2) no
  clean cross-platform API (Linux `SO_PEERCRED` vs macOS `LOCAL_PEERCRED`
  with no Python `getpeereid`, needing manual `getsockopt` + `xucred`
  unpacking). And it is low-value: the `0600` socket is already a
  **same-uid gate** (only same-user processes can connect) and the lease
  token is the per-request primary control, so peer-cred only adds
  pid-level discrimination for a same-user, same-host, first-party threat
  model. Revisit only if a shared-host threat model demands it.

## Consequences

- `serve --transport=http` is now spec-compliant (both surfaces); the
  two-serve-commands redundancy is gone.
- New Tier-2 surface `a2kit.spoke` (extends ADR 0004's tier list,
  snapshot-gated at `tests/surface/expected_tier_spoke.txt`).
- `build_api_key_middleware` (free function) removed in favour of
  `APIKeyAuth.build_middleware()`; the 401 envelope lives once in
  `packages/auth/_asgi.py`.
- a2kay owns lease minting/revocation and write-serialization; a2kit
  ships the mechanism, not the policy.
