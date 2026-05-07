# a2kit anti-patterns

Concrete failures observed while building two upstream MCPs (a SQL-wrapping
MCP and a Jira/Confluence-wrapping MCP) and a2kit itself. Each entry:
*the mistake* (one paragraph), *what to do instead* (one paragraph),
*citation* (file:line).

## 1. Don't return `-> str` from a FastMCP tool

The mistake: typing a tool as `-> str` looks natural ("agents read text") but
FastMCP double-serialises strings — the tool returns a JSON-encoded string,
the runtime wraps it in another JSON envelope, and the agent sees a quoted
quoted blob. Worse, schema introspection produces an `output_schema` whose
shape is "string" while the actual return is a formatted JSON document.

What to do: return `dict` or a Pydantic model. If you need a string body,
wrap it: `return {"format": "toon", "data": "<rows>"}`. The fat decorator
in `a2kit.tools.tool` enforces this at decoration time —
`InvalidToolReturnTypeError` fires the moment the file imports.

Citation: surfaced during a SQL-wrapping MCP's early build; reproducible
on any FastMCP server with `-> str` returns. `a2kit/tools.py::_check_return_annotation`
(`src/a2kit/tools.py`).

## 2. Pydantic models used as MCP tool return types must be at module scope

The mistake: defining a `class Result(BaseModel): ...` inside the function
that registers a tool, or inside a closure. FastMCP's
`inspect.signature(eval_str=True)` walks the wrapper chain to resolve the
return annotation; `eval_str=True` runs `eval(annotation_str, globals, locals)`
and it cannot see locals from a function that has already returned. Result:
`InvalidSignature: name 'Result' is not defined` at startup.

What to do: hoist every BaseModel used as a tool return type to module scope.
Adopt the lint rule "Pydantic models used as MCP tool return types must be
defined at module scope, not inside functions or classes" — candidate for
`modules/linters.md`.

Citation: surfaced during a2kit v0.2 build; reproducible with FastMCP and any
locally-defined Pydantic return-type model.

## 3. `from __future__ import annotations` stringifies return annotations

The mistake: under PEP 563 every annotation is a string at runtime. Code that
checks `if return_annotation is str:` silently misses the case where the
annotation is the literal string `"str"`. Decorators that try to enforce a
return-type contract end up letting `-> str` through.

What to do: check both `ret is str or ret == "str"`. a2kit's
`_check_return_annotation` does both. If you write a similar gate, copy the
pattern.

Citation: a2kit `src/a2kit/tools.py::_check_return_annotation`.

## 4. Schema extraction has no public FastMCP API — pin the seam

The mistake: reaching into FastMCP for tool schemas naturally lands at
`server._tool_manager.list_tools()` because `server.list_tools()` is async.
Sync test harnesses can't await; many consumers will end up importing the
underscore-prefixed manager directly, scattering the SDK-version-pin across
every test.

What to do: route every internal-API access through one named helper —
a2kit ships `_list_tools` in `a2kit.testing` and pins `mcp >= 1.0`. If
FastMCP changes the path, you update one function. File a SEP/issue against
FastMCP for a public sync `list_tools()`; until merged, this seam stays.

Citation: a2kit `src/a2kit/testing.py::_list_tools`.

## 5. Don't auto-register pytest plugins via setuptools entry points

The mistake: shipping `pytest11 = "a2kit.pytest_plugin"` in `pyproject.toml`
makes the plugin "free" for consumers — and instantly breaks coverage on
every consumer that uses pytest-cov. pytest imports plugin modules BEFORE
pytest-cov starts measurement; importing `a2kit.pytest_plugin` transitively
imports `a2kit/__init__.py` and the rest of the package, recording zero
coverage on every import-time line. The consuming repo's coverage drops
5–15% with no obvious culprit.

What to do: opt-in registration via the consumer's `conftest.py`:
`pytest_plugins = ["a2kit.pytest_plugin"]`. One line; no entry-point block;
plugin loads after coverage starts.

Citation: a2kit `src/a2kit/pytest_plugin.py` (header comment).

## 6. Don't ship a `main()` — author owns the FastMCP server

The mistake: a "convenience" wrapper that exposes `a2kit.run(server)` or, worse,
`a2kit.Server` — once it exists, every consumer's code branches between "use
the wrapper" and "drop down to FastMCP", and the wrapper accumulates flags
(`--scope`, `--enable`, `--register`, `--http`) that the next MCP doesn't
share. The library starts dictating program entry shape.

What to do: a2kit ships `MCPRunner` as a *helper* the author can ignore.
Calling `server.run()` directly is fully supported. The runner only exists
to absorb argv-parsing for flags that ARE n=2 confirmed, and to set the
transport seam used by `streaming=True` decorators. No `main()`. No required
class.

Citation: a2kit `src/a2kit/scaffold.py::MCPRunner`.

## 7. Don't add a primitive that overlaps a FastMCP primitive

The mistake: shipping a "tool" decorator that competes with `@server.tool()`.
A wrapper that produces a tool descriptor of its own forces the consumer to
choose between the two stacks; once the wrapper diverges from FastMCP's tool
shape (different argument coercion, different error envelope), every fix in
FastMCP misses your wrapper.

What to do: a2kit's `@a2kit.tool(...)` is *additive* — `@server.tool()`
stacks OUTSIDE it and remains the source of truth for tool registration.
The decorator only does pre-call hygiene (connection lookup, write check,
xml guard, OTel) and post-call routing (enricher). FastMCP keeps the
authoritative tool list, schema, dispatch.

Citation: a2kit `src/a2kit/tools.py` module docstring (stacking note).

## 8. Don't trust XML-shaped strings the agent passes you

The mistake: an agent's tool-call envelope (`<parameter name="x">...`) leaks
into the body of a string argument; the tool happily processes the broken
value and the failure surfaces three layers down with a confusing error.

What to do: the fat decorator runs `assert_clean_string` on every str-typed
argument by default. If the marker `<parameter name=` is present, raise
`ToolXMLContamination` immediately — short error, points at the offending
parameter, asks the agent to retry. Disable per-tool via `xml_guard=False`
when you genuinely accept XML. Standalone helper available for non-decorated
code paths.

Citation: a2kit `src/a2kit/tools.py::assert_clean_string`. Pattern observed
in production after agent tool-call envelopes leaked into string arguments.

## 9. Read-only is the default; write-marked tools require both flags

The mistake: every tool can mutate. The agent triggers a write on a
production database the user only ever wanted to query. There's no audit
trail because the connection didn't carry a write/read distinction.

What to do: the v0.2 contract is *read-only by default*. Connections set
`read_only=True` unless explicitly toggled at login. Tools that mutate use
`@a2kit.tool(write=True)`; the decorator raises `WriteNotAllowed` when the
resolved connection is read-only. The runner adds `--writes` (off by default)
to register write tools at all. Every layer agrees.

Citation: a2kit `src/a2kit/tools.py::tool` (the `write=` arg).

## 10. Don't paraphrase the connection-param explanation in every tool

The mistake: every tool docstring re-explains "the `connection` argument is
the saved connection name, not a project key" in slightly different wording.
The agent's mental model drifts; one tool says "connection key", another
says "connection name", a third says "saved profile". Eventually it sends a
project key and gets a confusing not-found error.

What to do: use `a2kit.docs.connection_param_doc()` and embed it via
f-string. One canonical sentence across the whole MCP. Override only the
CLI name and an optional domain-specific suffix.

Citation: a2kit `src/a2kit/docs.py::connection_param_doc`. Drift was measured
in production at roughly 5 wrong-key calls per 96 correct calls per session
before the canonical-sentence fix.

## 11. OTel auto-wiring must not import the package when no provider is set

The mistake: instrumenting every tool call by unconditionally importing
`opentelemetry.trace` adds a transitive dep to every consumer, including
those that never wanted OTel. Worse: even with the import, the default
no-op provider produces span objects with no attributes; the per-call
allocation cost is real and pure waste.

What to do: lazy import inside the call site; declare `opentelemetry-api` as
an optional `[otel]` extra; detect a non-default tracer provider before
opening a span (the default `ProxyTracerProvider` returns `NoOpTracer`
which we treat as "no provider" — skip the span). Document the seam so
consumers know how to flip it.

Citation: a2kit `src/a2kit/tools.py::_otel_span`.

## 12. Don't ship a TOON encoder if a vetted dep exists; vendor minimally if not

The mistake: writing 200 LOC of encoder for a wire format that is "tab,
newline, header row" — re-implementing CSV badly.

What to do: vendor a ≤ 30 LOC encoder, keep it in one place, document the
shape ("uniform list of dicts; non-uniform → JSON; the `format_response`
helper makes the choice for you"). a2kit's encoder is 12 LOC. If a
maintained TOON package emerges with stable semantics, swap to it; the
encoder is the single seam.

Citation: a2kit `src/a2kit/formatter.py::_toon_encode`.

## 13. Don't auto-stream from stdio MCPs

The mistake: returning an async iterator from a tool when the transport is
stdio. The MCP stdio framing has no streaming semantics; the iterator never
gets serialised, the agent sees an empty result.

What to do: opt into streaming with `@a2kit.tool(streaming=True)`. The
decorator collects items into a list when the active transport is stdio
and yields them through when HTTP. Transport is read from a thread-local
the runner sets — `MCPRunner` is the only writer; tests can poke
`_set_current_transport` directly. Without `streaming=True`, async-iterator
returns are returned-as-is and FastMCP will probably reject them — by
design.

Citation: a2kit `src/a2kit/tools.py::_consume_or_passthrough_async`.

## 14. Pydantic models can't use bare class-attribute defaults for fields

The mistake: subclassing a Pydantic model and overriding a field by writing
`name = "issues"` (no annotation). Pydantic v2 only registers a class
attribute as a field when there's an annotation, so the bare assignment
silently shadows the parent field — the subclass instance carries the
parent's default, not yours, and `extra="forbid"` won't catch the typo.

What to do: pass the value at instantiation. `IssuesRouter(name="issues",
capabilities={Cap.EXTERNAL})` is the canonical form. If you need a
class-level override, you must repeat the annotation: `name: str = "issues"`.
Pydantic v0.3.1's `Router` rewrite hit this — the v0.3 `class IssuesFeature(Feature): name = "issues"` style was dropped because the assignment didn't bind a field.

Citation: `src/a2kit/scaffold.py::Router` (v0.3.1 rewrite).

## 15. `Capability = str` runtime alias forces `# noqa: TC001` quirk

The mistake: hiding `Capability: TypeAlias = str` under `if TYPE_CHECKING:`.
Pydantic v2 reads field annotations *at runtime* to build the validator
schema, so anything used as a type annotation must be importable at runtime,
even if the value is a `TypeAlias`. Hiding the alias inside `TYPE_CHECKING`
causes Pydantic to fail with `NameError: name 'Capability' is not defined`
the first time you instantiate the model.

What to do: import `Capability` at runtime, accept the `TC001` noqa on the
import line, and document the pattern. The `_capabilities.py` and
`_configs.py` modules both carry the noqa for this reason.

Citation: `src/a2kit/_capabilities.py::Capability`,
`src/a2kit/_configs.py::ToolConfig`.

## 16. `from __future__ import annotations` interacts with Pydantic forward references

The mistake: turning on `from __future__ import annotations` (PEP 563),
declaring a Generic Pydantic model, and having Pydantic still see the type
parameter as a string at validation time. Symptom: `PydanticUserError:
... is not fully defined; you should define X, then call .model_rebuild()`.

What to do: after the forward-ref class is defined, call
`Model.model_rebuild()`. For most a2kit models we sidestep this by keeping
generic parameters narrow (`TypeVar(... bound=ConnectionInfo)`), but the
gotcha resurfaces every time a new generic is added. Prefer concrete unions
when the generic doesn't earn its complexity.

Citation: `src/a2kit/scaffold.py::Router` (Generic[ConnT]).

## 17. Don't auto-register pytest plugins via `pytest11` entry points

The mistake (already in v0.1, extended in v0.3.1): shipping a `pytest11`
entry point in `pyproject.toml` so consumers automatically pick up your
plugin. Any plugin that imports the parent package zeros out `pytest-cov`
measurement on the package — coverage is collected by source instrumentation,
which doesn't run for code already imported before pytest-cov starts.

What to do: opt-in only. Document `pytest_plugins = ["a2kit.pytest_plugin"]`
in the consumer's `conftest.py`. The plugin still ships in the wheel, but
nothing imports it until the consumer asks for it.

Citation: `src/a2kit/pytest_plugin.py`; consumer setup in
`tests/conftest.py:6`.

## 18. Synthetic clauses in deprecation aliases are tech debt

The mistake: implementing `--writes` (deprecated) by synthesising a `(read or
write)` clause into a `--select` expression internally. The translation
worked at runtime but polluted the AST: the lint rule A2K010 saw `read` and
`write` atoms in the user's expression that the user never wrote, which
prevented clean atom validation and made the error messages confusing.

What to do: prefer hard breaks over compatibility shims when the consumer
count is zero (pre-1.0, internal-only). v0.4 removed `--enable`, `--no-enable`,
and `--writes` entirely. Migration is documented one-line per flag in the
CHANGELOG. The lesson generalises: synthetic AST manipulation in a
compatibility layer makes the next layer's correctness story harder.

Citation: removed v0.4; previously at
`src/a2kit/scaffold.py::MCPRunner._legacy_to_select` (v0.3.1).

## 19. String-tuple drift: loose `KEY_FIELDS` over typed NamedTuples

The mistake (v0.3 through v0.4): declaring multi-field connection keys as
`KEY_FIELDS: ClassVar[tuple[str, ...]] = ("project", "env", "db")`. The
attribute carried only field names — every part of the key was implicitly
`str`. Calls like `store.load(env="production")` (note: `production`, not
`prod`) were valid Python and passed the runtime arity check, only failing
deep inside the store as `ConnectionNotFound`. There was no way to express
"the `env` part must be one of `dev`/`staging`/`prod`" at the type level.

The lint rule A2K005 attempted to compensate by cross-checking tool
parameter types against `KEY_FIELDS` arity, but it could only enforce
*shape*, not *values*. Any string passed as a key part was nominally legal.

What to do (v0.5): declare a NamedTuple per connection class and bind it
via `class WidgetConn(ConnectionInfo, key=WidgetKey)`. Use `Literal[...]`
on individual fields to constrain values:

```python
class WidgetKey(NamedTuple):
    project: str
    env: Literal["dev", "staging", "prod"]
    db: str
```

ty / pyright now reject `WidgetKey(env="production")` at type-check time.
The NamedTuple is still a tuple, so `store.load(("a", "dev", "c"))` and
the other legacy shapes keep working — but `store.load(WidgetKey(...))`
is the new most-explicit form, and `store.list_keys()` returns NamedTuple
instances rather than raw tuples.

Generalisation: if you find yourself reaching for `tuple[str, ...]` plus
a parallel name list to identify positions, you're describing a NamedTuple.
The string-tuple shape always under-types the data.

Citation: `src/a2kit/connections.py` (v0.5); migration via
`a2kit.exceptions.MigrationRequired`.
