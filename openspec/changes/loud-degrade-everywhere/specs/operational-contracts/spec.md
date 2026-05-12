## ADDED Requirements

### Requirement: Framework-internal introspection failures are observable, not silent

Framework-internal introspection performed during tool decoration or middleware dispatch — such as `typing.get_type_hints`, return-annotation copying, FastMCP tool-metadata lookup via `server.get_tool`, list-view payload projection / reconstruction, and OTel span-metadata lookup — SHALL NOT silently swallow exceptions. Each site SHALL emit one WARN-level log line per offender per process and SHALL continue with the documented fallback for that site (empty descriptions, `None` annotation, `()` selectable fields, unprojected payload, empty span metadata, etc.).

Bare `contextlib.suppress(Exception)` and bare `except Exception: pass` (or equivalent `except Exception: return <fallback>` with no observability hook) SHALL NOT be used on any code path reachable from tool decoration or middleware dispatch. Where a typed catch is appropriate, the catch SHALL still emit the per-offender WARN before applying the fallback.

The dedupe key per site SHALL be the most specific identity available:

- For decoration-time sites operating on a callable: `fn.__qualname__`.
- For middleware sites operating on a registered tool: the FastMCP tool name string. When a single module has more than one distinct failure site naturally keyed by `tool_name`, the dedupe key SHALL be composed as `f"{tool_name}::{site_tag}"` (e.g. `f"{tool_name}::get_tool"` for the registry lookup site and `f"{tool_name}::project"` for the projection site), so a single module-level `_WARN_ONCE: set[str]` can hold keys for multiple sites without collision.

Each module SHALL own its own `_WARN_ONCE` dedupe set at module scope (matching the pattern in `src/a2kit/signature.py:resolve_hints` and the docstring-pull sites). Cross-module sharing of dedupe state is not required and SHALL NOT be introduced.

The semantic outcome at every site SHALL be unchanged from the silent-degrade behaviour: decoration / middleware does not raise, the user-visible surface degrades the same way it did pre-policy. Only the silence is replaced with one observable WARN line per offender per process.

The `OPERATIONAL_CONTRACTS.md` document SHALL include an explicit clause stating this policy and SHALL index the sites it covers (the round-5/6 docstring-pull sites and the `loud-degrade-everywhere` sites L1 through L5).

#### Scenario: Decoration-time `get_type_hints` failure emits one WARN per qualname

- **GIVEN** a tool whose annotations cause `typing.get_type_hints` to raise (unresolved forward reference, missing import, etc.)
- **WHEN** the tool is decorated (any code path that calls `get_type_hints` during decoration: docstring pull, return-annotation resolution, selectable-fields derivation, dispatch-hook return-annotation copy)
- **THEN** decoration SHALL NOT raise
- **AND** exactly one WARN-level log line is emitted per (site, `fn.__qualname__`) pair, identifying the site and the offending function
- **AND** decorating the same tool a second time in the same process emits no further line for the same (site, qualname) pair

#### Scenario: Middleware tool-metadata lookup failure emits one WARN per tool name

- **GIVEN** an MCP server with the listview or OTel middleware installed and a tool whose `server.get_tool(tool_name)` raises (e.g. due to a corrupted registry state)
- **WHEN** the middleware processes a `call_tool` for that tool name
- **THEN** the middleware SHALL NOT raise; it SHALL apply the documented fallback (unprojected payload for listview, empty `a2kit.*` span attributes for OTel)
- **AND** exactly one WARN-level log line is emitted per `tool_name` per middleware site, naming the tool and the underlying exception
- **AND** subsequent invocations of the same tool name in the same process emit no further line from the same site

#### Scenario: Multi-site module reuses one dedupe set via composite keys

- **GIVEN** a module (e.g. `packages/mcp/listview.py`) with two distinct failure sites naturally keyed by `tool_name` (registry lookup and result projection)
- **WHEN** both sites fail for the same `tool_name` in the same process
- **THEN** exactly two WARN-level log lines are emitted, one per site, deduped by `f"{tool_name}::get_tool"` and `f"{tool_name}::project"` respectively
- **AND** both keys live in a single module-level `_WARN_ONCE: set[str]`
- **AND** a second failure at the same site for the same `tool_name` emits no further line

#### Scenario: No bare suppress in decoration or middleware paths

- **WHEN** the codebase is grepped under `src/a2kit/` for `contextlib.suppress(Exception)` or bare `except Exception:` in files reachable from tool decoration (`tool.py`, `_docstring.py`, `signature.py`, `packages/mcp/server.py`) or from middleware dispatch (`packages/mcp/listview.py`, `packages/otel/middleware.py`)
- **THEN** every match SHALL implement the WARN_ONCE pattern (try/except with module-local dedupe set and one `logging.warning(...)` per offender) or carry an inline comment justifying why the path is not an introspection failure

#### Scenario: Policy is documented in OPERATIONAL_CONTRACTS.md

- **WHEN** a reader opens `OPERATIONAL_CONTRACTS.md`
- **THEN** there is a section naming the "fail observable, not silent" policy for framework-internal introspection failures, listing the dedupe-key conventions per site type (including the composite-key convention for multi-site modules), and indexing the sites the policy covers (docstring pull, return-annotation resolution, selectable-fields derivation, dispatch-hook annotation copy, listview middleware, OTel middleware)
