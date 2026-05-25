# a2effect

Typed-error foundation for Python frameworks. Pydantic-only, no framework
dependency. Inspired by Effect-TS but adapted for Python's type system
(no HKTs, no monads — `Annotated` metadata + `isinstance` dispatch + lint).

## Quick taste

```python
from a2effect import AppError, Raises

class NotFound(AppError):
    kind = "input"
    http_status = 404
    cli_exit_code = 2
    hint = "verify the id is correct"

async def fetch(id: str) -> Annotated[Memory, Raises(NotFound)]:
    row = await db.get(id)
    if row is None:
        raise NotFound(f"memory id {id!r} does not exist")
    return Memory.model_validate(row)
```

The framework reads `Raises(...)` from the annotation, renders the
envelope to MCP / HTTP / CLI without further author input, and lints
that every raised exception is either declared, caught and re-raised,
or covered by an enricher path.

See `openspec/changes/a2effect-foundation/` for the full design.
