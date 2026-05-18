---
id: "0002"
status: accepted
date: 2026-05-13
last_reviewed: 2026-05-13
supersedes: []
superseded_by: null
tags: [surface, authoring, annotations]
deciders: [Denis Tomilin]
---

# ADR 0002: Pydantic.Field as the per-parameter author annotation surface

## Status

Accepted, 2026-05-13. The "Future vision" section below carries
**Anticipated** status: design committed, implementation deferred until
a third transport lands.

## Summary

In the context of multi-transport tool authoring, facing the fact that
each Python CLI / API / RPC framework ships its own annotation library
(`typer.Option`, `fastapi.Query`, `strawberry.field`, FastMCP's
schema reader), we decided for `pydantic.Field` as the single
per-parameter annotation surface for tool authors and against requiring
authors to import any transport-specific metadata class, to achieve one
annotation that lifts cleanly to every current and future transport,
accepting that CLI-specific behavior beyond `description` (env vars,
prompts, autocompletion) has no annotation channel today and is handled
in the tool body until the third-transport pressure justifies the
extension described in "Future vision."

## The problem

We ship two transports (CLI and MCP) and have two more on the
plausible roadmap (REST, GraphQL). Each of the Python frameworks we
might consume in those transports has its own annotation library:

```
transport       annotation library  what it carries
─────────────────────────────────────────────────────────────────
MCP (FastMCP)   pydantic.Field      description, validation
CLI (Typer)     typer.Option        help, envvar, prompt, completion
REST (FastAPI)  fastapi.Query/etc.  alias, location, openapi extras
GraphQL         strawberry.field    resolver, deprecation, directives
```

If every transport gets its own annotation, tool authors face the
N-libraries problem: a tool that exposes the same parameter on three
transports needs three annotations. That contradicts the central a2kit
contract: **the wire is plural, the author surface is singular.**

Today this is handled implicitly by `pydantic.Field`: FastMCP reads
its `description`, and our `_field_to_typer` adapter
(`src/a2kit/packages/cli/_field_to_typer.py`) reads the same field and
emits `typer.Option(help=...)`. Authors write one annotation, both
transports see it. So far so good.

The crack appears at transport-specific behavior that `pydantic.Field`
does not (and should not) carry:

- `envvar`: read the value from an environment variable on the CLI
- `prompt` / `hide_input`: interactive prompt for secret-like input on the CLI
- `autocompletion`: shell completion source for the CLI
- `rest_location`: header vs query vs path on a future REST transport
- `directives`: GraphQL field directives on a future GraphQL transport

None of these have a `pydantic.Field` kwarg, because they are not
validation or schema concerns. They are *transport-routing* concerns.

Today this is not a blocking pain. Authors who need an env-var-driven
arg read `os.environ` in the tool body. Authors who need a prompt do
`getpass.getpass()`. The CLI surface works, just without those
ergonomics.

The decision we have to make now is not "do we add `envvar` support
today" but "**what is the contract for adding transport-specific
metadata when we eventually need it**, so that the answer is not
re-litigated per-feature and per-transport."

## What we considered (and why pydantic.Field)

**Status quo: pydantic.Field, full stop, no extensions.** Works for
~80% of cases. Description, validation, examples. Cross-transport
"for free" because every Python framework worth using either reads
pydantic directly or accepts json schema. Cost: features like `envvar`
have no annotation channel; authors who need them write tool-body code.
Accepted as the current state; the question is what to do when the
status quo fractures.

**Reintroduce `a2kit.Param` as a typed metadata class.** Rejected.
Version 0.31.0 deleted `a2kit.Param` because it duplicated
`pydantic.Field` without adding cross-transport value. Reintroducing
the same class with new fields would repeat that mistake unless the
class carried *strictly more* than `Field`, and unless every transport
adapter learned to read it. The latter is the harder problem: FastMCP
reads `pydantic.FieldInfo`, FastAPI reads its own `Param` subclasses,
strawberry reads its own. None of them will learn `a2kit.Param`.

**Import `typer.Option` directly in tool signatures.** Rejected. Tool
authors writing `Annotated[str, typer.Option(envvar="X")]` couples
their tool to Typer. The `pydantic.FieldInfo` channel is
transport-agnostic by happy accident (everyone reads pydantic); the
`typer.Option` channel is transport-specific by design. We'd be
promoting CLI to a privileged transport in the annotation surface.

**Pydantic.Field with `json_schema_extra` for transport hints.**
Pydantic preserves `json_schema_extra` through to the generated JSON
schema. Every transport that reads the schema (MCP, OpenAPI/REST,
GraphQL via schema introspection) sees the extras automatically. We
adopt the OpenAPI convention of an `x-` prefix to namespace
vendor extensions, specifically `x-a2kit-*`. Each transport adapter
reads its own keys and ignores the rest. **This is the chosen path.**

The only ergonomics cost is that `json_schema_extra={"x-a2kit-envvar": "FOO"}`
is stringly-typed at the call site. The "Future vision" section below
addresses that with a thin factory function.

## The decision

**Today.** Pydantic.Field is the per-parameter annotation surface for
tool authors. Full stop. No transport-specific metadata classes appear
in tool signatures. The single allowed exception is the tool-level
verb decorators (`@a2kit.read` / `@a2kit.write` / `@a2kit.list_` /
`@a2kit.tool`), which carry *per-tool* metadata, not per-parameter.

```python
# Today's canonical shape:
async def fetch_user(
    self,
    *,
    user_id: Annotated[str, Field(description="User ID")],
    limit: Annotated[int, Field(description="Page size", ge=1, le=100)] = 10,
) -> dict: ...
```

**Reserved namespace.** The `x-a2kit-*` prefix in
`pydantic.Field.json_schema_extra` is reserved for transport-routing
metadata that future transport adapters will consume. No transport
ships keys in this namespace today; the namespace is locked so that
when a transport ships extension support, it does not collide with
ad-hoc author usage.

**No new metadata classes.** Until and unless the "Future vision"
extension lands, no `a2kit.Arg`, `a2kit.Param`, or any other
metadata wrapper is added. Authors who need transport-specific
behavior beyond what `pydantic.Field` carries handle it in the tool
body.

## Consequences

### Positive

- One annotation library to teach (pydantic). Onboarding cost is one
  library a Python developer already knows.
- Every transport adapter reads from the same place
  (`pydantic.FieldInfo` plus `json_schema_extra`), so adding a fourth
  transport does not change the author surface.
- The `x-a2kit-*` namespace contract makes it explicit where
  transport-specific behavior belongs when it lands, so per-feature
  bike-shedding is preempted.
- v0.31.0's "don't reinvent pydantic.Field" lesson stays intact.

### Negative

- CLI features Typer offers natively (`envvar`, `prompt`, `hide_input`,
  `autocompletion`) have no annotation channel today. Authors who want
  them write tool-body code. This is a paper cut, not a blocker, but
  it is real.
- The `x-a2kit-*` namespace is reserved but unused today, which means
  the contract is theoretical until a transport ships consumption code
  for it. A contributor reading the source will not see the namespace
  in action.

## Future vision

**Status: Anticipated.** Not implemented. Triggered when a third
transport (REST or GraphQL) lands and concretely requires
transport-routing metadata that `pydantic.Field` does not carry.

The expected shape: a factory function in `a2kit.args` that returns a
`pydantic.FieldInfo` with `json_schema_extra` populated under the
`x-a2kit-*` namespace.

```python
# Hypothetical a2kit/args.py
def Arg(
    *,
    description: str = "",
    envvar: str | None = None,
    sensitive: bool = False,
    rest_location: Literal["query", "path", "header", "body"] = "body",
    **field_kwargs,
) -> FieldInfo:
    extra = {}
    if envvar: extra["x-a2kit-envvar"] = envvar
    if sensitive: extra["x-a2kit-sensitive"] = True
    if rest_location != "body": extra["x-a2kit-rest-location"] = rest_location
    return Field(description=description, json_schema_extra=extra, **field_kwargs)
```

Tool authors would then write:

```python
async def fetch(
    self,
    *,
    api_key: Annotated[str, a2kit.Arg(
        description="API key",
        envvar="FOO_KEY",
        sensitive=True,
    )],
) -> dict: ...
```

Key properties of this shape:

1. Returns a `pydantic.FieldInfo`. No new metadata class. Every
   pydantic consumer (FastMCP, FastAPI, strawberry) reads it natively.
2. Typed function surface: IDE autocomplete works, typos in field
   names fail at lint time.
3. Transport adapters read `field_info.json_schema_extra["x-a2kit-*"]`
   and lift to their native idiom (`x-a2kit-envvar` becomes Typer's
   `envvar=`, FastAPI's env config, etc.). Adapters that do not
   recognize a key ignore it silently.
4. Validation kwargs (`ge`, `le`, `regex`) pass through to
   `pydantic.Field` unchanged.

What this ADR does **not** commit to:

- The exact field set on `a2kit.Arg`. The list above is illustrative.
  The real set is defined by what the triggering transport actually
  needs.
- The exact module path. `a2kit.args.Arg`, `a2kit.Arg`, or somewhere
  else, to be decided when the implementation lands.
- A timeline. The trigger is a third transport, not a release date.

When the trigger fires, this section is replaced by an implementation
ADR (`0003-...` or higher) and this ADR's Status is updated to
`Superseded by ADR NNNN`.

## References

- ADR conventions: `docs/adr/README.md`
- v0.31.0 `align-with-pydantic-and-stdlib` change (the proposal that
  deleted `a2kit.Param`):
  `openspec/changes/archive/2026-05-13-align-with-pydantic-and-stdlib/`
- Replace-cli-builder-with-typer (the change that surfaced this
  question by adding the second concrete transport adapter):
  `openspec/changes/archive/2026-05-13-replace-cli-builder-with-typer/`
- OpenAPI vendor-extension convention (`x-` prefix):
  <https://swagger.io/docs/specification/openapi-extensions/>
