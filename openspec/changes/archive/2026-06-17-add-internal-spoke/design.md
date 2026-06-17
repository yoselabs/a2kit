# Design — add-internal-spoke

## Grounding (live in `src/`, 2026-06-17 audit)

| # | Seam | File / symbol | State today | This change |
|---|---|---|---|---|
| 1 | serve listener | **build finding:** wired serve = `cli/_serve.py` `register_serve` (Typer), was MCP-only; `mcp/cli.py` `build_serve_command` (multiplex) was orphaned | one MCP-only listener (spec-violating) + dead multiplex | consolidate onto `register_serve`: http = `build_parent_app` multiplex; add co-resident UDS listener on the same runtime; delete the orphan |
| 2 | runtime sharing | `packages/serve.py:84` "one runtime for the whole process" + `build` idempotent | already single-runtime | reuse — hand the one runtime to both listeners |
| 3 | store scope | `packages/di/scope.py:5` `SINGLETON` = one per Container, cached on root | exists | DuckDB stays `SINGLETON` → one handle across both listeners |
| 4 | auth target | `packages/auth/spec.py` `AuthTarget = Literal["api","mcp"]` | closed | open it |
| 5 | auth mount | `packages/http/build.py` `_install_auth_middlewares` → `for_target("api")` + `isinstance(spec, APIKeyAuth)` | welded | generic `spec.build_middleware()` over `for_target(surface.name)` |
| 6 | key lifecycle | `packages/auth/api_key.py` `_materialise_keys` ("resolved once at build") | static | new `TokenAuth` resolves per request against a live table |
| 7 | client | `packages/testing/client.py` in-process `fastmcp.Client(transport=build_mcp_server(app))` | in-proc, test-only | a supported cross-process UDS client |

## D1. Why a spoke and not a copy

Single-writer DuckDB forbids a second writer process. A "parallel copy with its
own store handle" works **only for read-only** consumers. Anything that writes
must funnel through the one writer. Jobs write (transcription results), so they
are clients of the writer, reached over a local channel. Read-only companions are
out of scope precisely because the copy pattern already serves them.

## D2. Topology — two listeners, one runtime, one store

```
   build(app) ──► ONE runtime ──► ONE root container (DuckDB = SINGLETON)
                                    │
            ┌───────────────────────┴───────────────────────┐
     public listener (TCP host:port)              spoke listener (UDS, 0600)
     parent app: MCP + API                        app: API surface only
     auth: OAuth / APIKeyAuth (target=api/mcp)    auth: TokenAuth (target=internal)
            │                                               │
            └── each call → SCOPED child container ─────────┘
                          one async with runtime: forwards both lifespans
```

Implementation shape (in `serve`, http path): build the runtime once; construct
the public parent (existing `build_parent_app`) **and** a spoke app (an HTTP app
over the API surface, with `TokenAuth` mounted); run two `uvicorn.Server`
instances — one `host/port`, one `uds=` — under one `asyncio.gather`, with the
runtime entered once and both servers' lifespans forwarded. Reuses the existing
"parent owns the single lifecycle" rule (`serve.py`).

### Concurrency caveat (load-bearing, called out, owned by the consumer)

Two listeners means concurrent callers (agent over MCP **and** job over UDS) hit
the **one** `SINGLETON` store handle. Two consequences a2kay must honor:
1. **Serialize writes** at the handle (async lock / single write-task). The
   shared singleton gives the handle, not concurrency safety.
2. **Long jobs write in short transactions** (per file), releasing the writer
   between units. Credential validity (lease, may be a day) and write-lock
   holding (per-file, brief) are separate concerns; a day-long job MUST NOT hold
   the writer for a day or it starves the public surfaces.

## D3. Auth — open target + generic mount

`AuthTarget` becomes an open `str` (or gains `"internal"`). `_install_auth_middlewares`
stops branching on `isinstance(APIKeyAuth)` and the literal `"api"`:

```python
# after
for spec in registry.for_target(surface.name):
    app.add_middleware(_BareAsgiMiddleware, factory=spec.build_middleware())
```

`AuthSpec` grows `build_middleware() -> AsgiFactory`. `APIKeyAuth` moves its
existing `build_api_key_middleware(self)` body behind it (no behavior change —
removes the isinstance weld). This is the "split auth per surface" the consumer
asked for; it is also the no-redundancy cleanup (one dispatch, not a per-class
chain).

## D4. `TokenAuth` — lease-validating strategy

```python
@dataclass
class TokenAuth(AuthSpec):
    target: ClassVar[str] = "internal"
    header: str = "X-A2kit-Token"
    resolve: Callable[[str], Principal | None]   # per-request lookup against the LIVE table
    def build_middleware(self) -> AsgiFactory: ...  # 401 on miss; publish Principal on hit
```

Key point vs `APIKeyAuth`: `resolve` is called **per request**, so revocation is
instant and leases need no fixed TTL. a2kit owns the strategy + the per-request
publish; the **lease table and its lifecycle (mint at spawn, revoke at exit) are
a2kay's runner** — `TokenAuth` is handed the `resolve` closure over whatever live
set the runner maintains. This keeps the table (and any secret) out of a2kit and
out of the synced vault.

## D5. The client

A spawned job dials the UDS. Minimal: document `httpx.HTTPTransport(uds=...)` /
`fastmcp.Client` over a UDS transport. Supported: a thin a2kit wrapper
(`a2kit.spoke.client(socket_path, token)`) exposing `invoke(canonical_name, **kw)`
so jobs never import fastmcp/httpx internals. Mirrors the catalog of the API
surface (same canonical names) — no second tool catalog.

## D6. Open implementation questions (resolve in build)

- **Two `uvicorn.Server`s vs one server + a raw asyncio UDS responder.** Prefer
  two `uvicorn.Server` instances (reuses ASGI + the existing app build); confirm
  clean shutdown ordering under `asyncio.gather` + the shared runtime exit.
- **Peer-cred belt-and-suspenders.** Optionally verify `SO_PEERCRED`/`getpeereid`
  so only a child of the runner can connect, in addition to the token. macOS vs
  Linux API split — keep it optional, token is primary.
- **`AuthTarget` open `str` vs enum-extension.** Open `str` is simplest and lets
  consumers name targets; confirm it does not weaken the `for_target` filter.
