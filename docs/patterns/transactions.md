# Per-call scope and transactions — `per_call=True`

A per-call resource lives for exactly one tool dispatch. It enters
when first resolved during the call, is cached for the rest of that
call, and is cleaned up when the call returns (or raises). The
canonical case is a database transaction.

```python
class Transaction:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    async def __aenter__(self) -> "Transaction":
        self._conn = await self._pool.acquire()
        await self._conn.execute("BEGIN")
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc is None:
                await self._conn.execute("COMMIT")
            else:
                await self._conn.execute("ROLLBACK")
        finally:
            await self._pool.release(self._conn)

app.provide(ConnectionPool)            # app-scope: one pool, shared
app.provide(Transaction, per_call=True) # per-call: fresh per dispatch
```

```python
async def transfer(tx: Transaction, src: str, dst: str, amount: int) -> None:
    await tx._conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, src)
    await tx._conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, dst)
    # On normal return: tx.__aexit__ runs with exc=None → COMMIT.
    # On exception: tx.__aexit__ runs with the exception → ROLLBACK.
```

## Scope rules

- A per-call resource MAY depend on app-scope resources (chain up to
  the parent container). The example above: `Transaction` depends on
  `ConnectionPool`.
- An app-scope resource MUST NOT depend on per-call resources. The
  framework rejects this at `async with app:` with a clear scope
  violation. Per-call types live for one dispatch; an app-scope
  instance would cache a stale per-call value. Use `Lazy[T]` to defer
  resolution into the call scope instead.

## Exception preservation

The per-call resource's `__aexit__` sees the propagating exception
exactly like a plain `async with` — `(exc_type, exc, tb)` are forwarded
through the cleanup stack. Tool body exceptions still win at the call
site; cleanup-stack failures log at WARN on `a2kit.di.cleanup` and
sibling cleanups still run.

## When NOT to use `per_call=True`

- For dependencies that should outlive the call (caches, pools,
  long-lived clients): use the default app-scope.
- For dependencies that are pure value containers with no lifecycle:
  consider whether you need DI at all; a plain constructor argument
  may be cleaner.
