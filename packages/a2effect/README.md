# a2effect

Typed-error foundation for Python frameworks. Pydantic-only, no framework
dependency. Inspired by Effect-TS but adapted for Python's type system
(no HKTs, no monads — `Annotated` metadata + `isinstance` dispatch + lint).

## Quickstart

### 1. Subclass `AppError`

```python
from a2effect import AppError

class NotFound(AppError):
    kind = "input"
    http_status = 404
    cli_exit_code = 2
    hint = "verify the id is correct"

class UpstreamUnavailable(AppError):
    kind = "infra"
    # retryable defaults to True for kind=infra
```

Kinds are `input | auth | policy | infra | bug`. Per-class
`http_status` / `cli_exit_code` ClassVars override the kind defaults
(400/401/403/503/500 and sysexits.h 2/77/77/75/70).

### 2. Annotate the tool's return

```python
from typing import Annotated
from a2effect import Raises

async def fetch(id: str) -> Annotated[Memory, Raises(NotFound, UpstreamUnavailable)]:
    row = await db.get(id)
    if row is None:
        raise NotFound(f"memory id {id!r} does not exist")
    return Memory.model_validate(row)
```

Multiple `Raises(...)` markers in one `Annotated[...]` flatten
additively. `Raises.flatten_from_annotation(fn)` reads them via
`get_type_hints(include_extras=True)`.

### 3. Register an enricher (when integrating with a2kit)

```python
import asyncpg
import a2kit

router = MyRouter()
app = a2kit.App("myapp")

@router.enricher
def pg_enricher(exc: asyncpg.PostgresError) -> UpstreamUnavailable | None:
    # Narrow form: framework dispatches only on isinstance(exc, asyncpg.PostgresError)
    return UpstreamUnavailable(str(exc))

app.add_router(router)
```

The first parameter's annotation chooses the dispatch shape: bare
`Exception` / `BaseException` is wide (called on every raise); a
specific type is narrow (called only on `isinstance`). Return type is
`AppError | None`; the runtime validates and raises `TypeError` if a
non-`AppError` is returned.

### 4. Run contract tests

```python
# tests/test_contract.py
from a2effect.testing import contract_tests

import myapp

tests = contract_tests(myapp.build())

def test_envelope_round_trip(): tests["envelope_round_trip"]()
def test_dead_enricher_detection(): tests["dead_enricher"]()
def test_surface_parity(): tests["surface_parity"]()
```

`contract_tests(app)` parametrises across every tool × every Raises
member to assert: envelopes round-trip identically across MCP/HTTP/CLI,
every registered enricher is reachable from some tool's declared raise
set, and the three surfaces agree on the envelope shape.

## What you get on the wire

| Surface | Success | Error |
|---|---|---|
| MCP | `content[0].text = json.dumps(model_dump)`, `isError=false` | `content[0].text = prose`, `structuredContent={"error": <envelope>}`, `isError=true` |
| HTTP | `200 + JSON body` | status from kind map (or per-class override), body `{"error": <envelope>}` |
| CLI | stdout = formatted, exit 0 | stderr = prose, exit = `cli_exit_code` (default by kind) |

Prose format: `<KindLabel> (<Type>): <message>\n\nHint: <hint>`. The
`Hint:` block is omitted when `hint` is None.

## Lint rules

```bash
python -m a2effect.lint <your-src>
```

Three rules ship as Python entry points under the `a2lint.rules` group:

- `A2K-RAISES-CLOSURE` (error) — every `raise X(...)` in a tool body
  must be declared in `Raises(...)`, caught and re-raised as something
  declared, or covered by an enricher.
- `A2K-RAISES-UNCOVERED` (warning) — a known-throwing function (per
  `raises_registry` built-in stubs for httpx/asyncpg/redis/sqlalchemy/
  fastapi, or your `[tool.a2effect.raises_registry]` extension) is
  called in a tool body but its raise set isn't covered.
- `A2K-RAISES-NOT-TYPED` (error) — `Raises(...)` contains a class that
  isn't an `AppError` subclass.

## Why no Result monad?

Effect-TS's mechanism leans on HKTs and a fiber runtime. Python has
neither, and `Result[T, E]`-style returns make every call site
ceremonial. The Python-native answer: declare the failure vocabulary in
metadata, dispatch via `isinstance`, and lint the closure. You get
Effect's *guarantee* (no error escapes undeclared) without its
*mechanism* (HKTs, monads).

See `docs/adr/0021-typed-error-foundation.md` in the parent a2kit repo
for the full design rationale.
