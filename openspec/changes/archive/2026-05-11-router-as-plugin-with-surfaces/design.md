## Context

Origin of this change is the a2web feedback round 3 (`A2KIT_FEEDBACK.md` in
the a2web repo). Two items collapsed into one architectural move:

- Wish 3 — `add_cli(connections_cli(X))` hides a multi-subsystem install
  (CLI + MCP + provider) behind a chain call that names only one of the
  three.
- New observation — credential-management tools (`login`, `logout`)
  should not surface on MCP by default; the plugin author knows this and
  needs a way to declare it.

The architectural observation: `Router` (slug + tools) and "plugin"
(router + providers + lifecycle) are the same concept at different
completion levels. A2kit currently has only the first; the work needed to
honor a2web's wish would have introduced the second. Better to extend
the first.

## Decisions

### D-ROUTER-AS-UNIT — Router is the unit of installation

`Router` grows `providers: tuple[...] = ()`. Lifecycle hooks
(`on_startup`, `on_shutdown`) are recognized as methods on a Router
subclass and registered against the App during `add_router`. No new top-
level type; no new install verb.

Rejected alternatives:

- **Separate `AppPlugin` dataclass + `app.install()` verb.** Adds a
  second concept that overlaps almost entirely with Router. Tool authors
  would need to learn when each applies. The split was an artifact of
  migration thinking, not a real architectural boundary.
- **Composition via decorator on the factory function.** Looked at
  `@a2kit.plugin def connections(...)` returning a magic object. More
  metaprogramming, same surface, less inspectable. Router is already a
  class authors subclass; extending the class is the path of least
  surprise.

### D-SURFACE-FLAG — `Surface` is a `Flag`, not an Enum

Future surfaces (`HTTP`, `SSE`, dedicated admin transports) compose:
`Surface.CLI | Surface.HTTP`. Flag arithmetic is in stdlib (`enum.Flag`)
and supports `in` membership tests cleanly. Enums would force enumerating
every combination.

`Surface.ALL` is the default; tool authors who don't think about
transports get every transport, which matches today's behavior.

### D-SURFACE-FILTERING — transport mounters filter, decorator doesn't

Tool authors mark `surfaces=Surface.CLI` on a tool. The CLI builder
walks the App's registered tools and skips ones missing `Surface.CLI`.
The MCP server does the same for `Surface.MCP`.

Rejected alternative: filtering at decoration time (i.e. the decorator
itself decides whether to register). Rejected because the same tool
should be visible to lint, tests, and metadata regardless of transport;
filtering at mount time keeps the tool "real" everywhere except where
the operator chose not to expose it.

### D-SURFACE-METADATA — stored in `meta.extra`

The decorator stashes `surfaces` in the tool's `meta.extra` dict under
the key `a2kit.surfaces`. Default value is `Surface.ALL` if the kwarg is
absent. Transport mounters look it up via `get_meta(fn).extra.get(...)`
with a default. No new field on the core `meta` dataclass; the existing
`extra` dict is the right place for transport-specific advisory
metadata.

### D-CONNECTIONS-FACTORY — `connections(X)` returns a parameterized Router

```python
def connections(conn_cls: type) -> Router:
    """Build the connections-management router parameterized by `conn_cls`."""

    class _ConnectionsRouter(Router):
        name = "connections"
        providers = (conn_cls,)

        @read(surfaces=Surface.CLI)
        async def login(self, *, profile: str, token: str) -> ConnectionState: ...

        @read(surfaces=Surface.CLI)
        async def logout(self, *, profile: str) -> None: ...

        @read()  # ALL — agents may want this
        async def list_connections(self) -> list[ConnectionInfo]: ...

        async def on_startup(self) -> None: ...
        async def on_shutdown(self) -> None: ...

    return _ConnectionsRouter()
```

Dynamic class generation is necessary because the providers tuple
closes over `conn_cls`. Alternative considered: instance attribute
`router.providers = (conn_cls,)` set on a plain `Router()` plus a
functional decorator path `@router.read(...)`. Rejected because:

- Class-based routers are the canonical authoring pattern.
- Mixing class-based and functional decoration creates two ways to do
  it, with subtly different semantics.

### D-DEPRECATION-PATH — `connections_cli` survives one release

```python
def connections_cli(conn_cls: type) -> click.Group:
    warnings.warn(
        "connections_cli is deprecated; use add_router(connections(X))",
        DeprecationWarning,
        stacklevel=2,
    )
    # Emit the same registrations the old chain would have, returning
    # just the click.Group so `add_cli(...)` still works.
    ...
```

Removed in v0.27. The migration is a one-line diff per call site, so the
deprecation window can be short.

### D-LINT-HEURISTIC — credential-name dictionary, conservative bias

`A2K-SURFACE-EXPLICIT` fires on tools whose declared name (or `title`)
matches a small heuristic dictionary:

```
login, logout, signin, signout, authenticate, auth_*,
set_token, set_credential, rotate_key, rotate_secret,
issue_token, revoke_token
```

Rule emits a finding when such a tool defaults to `Surface.ALL` (i.e.
the `surfaces=` kwarg is absent from the decorator). Suppression: add
`surfaces=Surface.ALL` explicitly, which makes the intent visible.

The heuristic is intentionally narrow. False positives are easier to
suppress than the smell is to spot. Lint behavior is the same as
existing A2K-* rules: warning by default, configurable severity.

## Risks / open questions

- **Subclass-based Router lifecycle vs. decorator-based.** If we later
  ship functional routers (`router = Router(); @router.read ...`),
  lifecycle hooks need an instance API too. Defer until demand.
- **`Surface` for non-tool resources.** Health probes today are tools;
  if `health_tool=True` is replaced by a `Surface`-aware mechanism,
  we'd cover health-on-CLI-only deployments. Out of scope for this
  change.
- **Per-install surface override.** Consumer says "I want `login` on
  MCP for our internal-only server." Considered `app.add_router(r,
  surface_overrides={"login": Surface.ALL})`. Deferred — the plugin's
  default is correct 95% of the time; the consumer can write a wrapper
  Router that overrides if needed.
