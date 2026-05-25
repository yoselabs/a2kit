# Migration: typed errors (a2effect-foundation)

This document is the mechanical recipe for porting a consumer a2kit
project (a2web, a2atlassian, a2db, a2skill, or any third-party
a2kit-based MCP server) to the typed-error contract introduced by
the `a2effect-foundation` change. The new contract replaces the old
`enricher(exc) -> str | None` shape with `(exc) -> AppError | None`,
adds `Raises(...)` declarations to tool return annotations, and
swaps untyped error strings on the wire for the
`ErrorEnvelope`-shaped payload.

## What changed

- **Enricher signature.** `(exc) -> str | None` is gone. Enrichers now
  return `AppError | None`. Wide and narrow forms are both supported;
  the framework picks the dispatch shape from the first parameter's
  annotation.
- **Tool return annotations.** Every tool's declared errors live in
  `Annotated[ReturnT, Raises(E1, E2, ...)]`. The `Raises` markers are
  picked up at materialisation; they drive `ToolDescriptor.raises`,
  contract tests, and (post-Group 14 schema work) the MCP outputSchema
  union.
- **Wire format.** Errors on MCP carry prose in `content[0].text`
  plus the typed envelope in `structuredContent.error`. HTTP error
  bodies carry `{"error": <envelope dict>}` with status from the
  documented kind map. CLI exits with the kind-mapped sysexits.h
  code and prints prose to stderr.
- **AuthorizationDenied.** Now an `AppError` subclass; flows through
  the same envelope path. The legacy
  `{"error": "authorization_denied", "reason", "callable"}` body
  shape is gone.

## Step 1 — define your AppError subclasses

Pick the kind per the canonical taxonomy: `input` (bad inputs, missing
entities), `auth` (no credentials), `policy` (credentials present but
not allowed), `infra` (downstream gone, transient), `bug` (programmer
error). Set per-class `http_status` / `cli_exit_code` only when you
need to override the default kind map (NotFound subclasses commonly
set `http_status = 404`, Timeout subclasses set `504`).

```python
from a2effect import AppError

class NotFound(AppError):
    kind = "input"
    http_status = 404
    hint = "list_memories first to discover valid ids"

class InvalidId(AppError):
    kind = "input"

class UpstreamUnavailable(AppError):
    kind = "infra"
    # retryable defaults to True for kind=infra
```

## Step 2 — annotate every tool's return

```python
from typing import Annotated
from a2effect import Raises

class MemoryRouter(a2kit.Router):
    slug = "mem"

    @a2kit.read()
    async def fetch(self, *, id: str) -> Annotated[Memory, Raises(NotFound, InvalidId)]:
        ...

    tools = (fetch,)
```

Multiple `Raises(...)` markers in one `Annotated[...]` flatten
additively. The framework strips them before computing
`format_hint` / `encoding_plan`, so existing format routing is
unaffected.

## Step 3 — port enrichers to the new signature

The old shape:

```python
# REMOVE
class MemoryRouter(a2kit.Router):
    enrichers = (mem_404_enricher,)

def mem_404_enricher(exc: Exception) -> str | None:
    if isinstance(exc, LookupError):
        return f"memory not found: {exc}"
    return None
```

The new shape (instance-decorator, returns `AppError | None`):

```python
router = MemoryRouter()

@router.enricher
def mem_404_enricher(exc: LookupError) -> NotFound | None:
    # Narrow form: framework dispatches only on isinstance(LookupError)
    return NotFound(f"memory not found: {exc}", details={"key": str(exc)})

app.add_router(router)
```

Or, if you need to inspect many exception types inside one
enricher, use the wide form:

```python
@router.enricher
def general_enricher(exc: Exception) -> AppError | None:
    if isinstance(exc, asyncpg.PostgresError):
        return UpstreamUnavailable(str(exc))
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
        return UpstreamUnavailable("rate limited", retryable=True)
    return None
```

App-level enrichers work identically:

```python
@app.enricher
def fallback(exc: Exception) -> AppError | None:
    ...
```

Chain order is: per-tool inline (`raises_as` / `translate_to`) →
router enrichers (registration order) → app enrichers (registration
order) → defect quarantine. The first non-None wins.

## Step 4 — translate at the call site

For one-off translations inside a tool body, prefer the inline
helpers over a wide router enricher:

```python
from a2effect import raises_as

@a2kit.read()
async def fetch(self, *, id: str, db: Database) -> Annotated[Memory, Raises(NotFound)]:
    row = await raises_as(
        db.get(id),
        {asyncpg.PostgresError: UpstreamUnavailable},
    )
    if row is None:
        raise NotFound(f"memory id {id!r} does not exist", details={"id": id})
    return Memory.from_row(row)
```

## Step 5 — drop unhandled-raise sprawl

The framework wraps every non-`AppError` escape via
`UnexpectedDefect` (kind=bug, retryable=false). Don't write
catch-all `except Exception` blocks that re-raise as strings —
that pattern dies with the old contract. Let the body throw; the
enricher chain (or quarantine fallback) does the wire-shape work.

## Step 6 — adopt contract tests

```python
# tests/test_contract.py
from a2effect.testing import contract_tests

import myapp

app = myapp.build()
tests = contract_tests(app)

def test_envelope_round_trip(): tests["envelope_round_trip"]()
def test_dead_enricher_detection(): tests["dead_enricher"]()
def test_surface_parity(): tests["surface_parity"]()
```

`contract_tests(app)` parametrises across every tool × every Raises
member, asserting the envelope round-trips identically on MCP/HTTP/CLI,
that every registered enricher is reachable from at least one tool's
declared raise set, and that wire surfaces agree on the envelope shape.

## Step 7 — update existing test assertions

If your tests asserted the legacy wire shapes, update them:

| Old shape | New shape |
|---|---|
| `result.content[0].text == "Tool error: <msg>"` | `result.content[0].text == "<KindLabel> (<Type>): <msg>\n\nHint: ..."` |
| `result.structured_content` (on success) | unchanged (success path) |
| `result.structured_content == {"class": "ValueError", "message": "..."}` (on error) | `result.structured_content == {"error": {"type": "...", "kind": "...", ...}}` |
| HTTP error `{"error": "authorization_denied", "reason": "...", "callable": "..."}` | `{"error": {"type": "AuthorizationDenied", "kind": "auth", "details": {"reason": "...", "callable": "..."}, ...}}` |
| CLI: `result.output.startswith("error: ")` + `exit_code == 1` | `result.output.startswith("<KindLabel> (<Type>):")` + `exit_code` from the kind map (input=2, auth/policy=77, infra=75, bug=70) |

## Step 8 — verify

Run the full test suite. Run `python -m a2effect.lint <your-src>`
to catch undeclared raises (`A2K-RAISES-CLOSURE`), uncovered
known-throwing calls (`A2K-RAISES-UNCOVERED`), and non-AppError
members in `Raises(...)` (`A2K-RAISES-NOT-TYPED`).

There is no backwards-compatibility shim and no soft mode. The
contract is strict from day one.
