# Conditional dependencies — `Lazy[T]`

A tool that *might* need an expensive resource (browser pool, LLM
extractor, geo lookup, ...) but doesn't on every dispatch should
declare the parameter as `Lazy[T]`, not `T`.

```python
from a2kit.packages.di import Lazy

class Browser:
    async def __aenter__(self) -> "Browser": ...
    async def __aexit__(self, *exc) -> None: ...

async def extract(url: str, browser: Lazy[Browser]) -> str:
    if needs_js(url):
        b = await browser()       # entry happens HERE, first await
        return await b.scrape(url)
    return await plain_http_get(url)
```

- `app.provide(Browser)` registers the resource at app-scope.
- The tool receives a zero-arg async closure, not a `Browser` instance.
- If the closure is never awaited, `Browser.__aenter__` is never called
  and the resource is never created. Solves the "five-resource tool
  only uses one" problem without `ctx.get(T)` service-locator antipatterns.
- The closure honors the resource's scope: app-scope `Lazy[T]` returns
  the same instance across calls; per-call `Lazy[T]` returns a fresh
  instance per dispatch.
- Cleanup wires through the closure: a `Lazy[T]` of an app-scope
  resource is cleaned up at app exit; a `Lazy[T]` of a per-call resource
  is cleaned up at call exit.

The canonical motivating case is `a2web`'s `extract` tool — same
function, sometimes JS-rendering, sometimes plain fetch, sometimes
LLM-assisted. Three optional dependencies become three `Lazy[T]`
parameters; only the ones actually used get constructed.

## When NOT to use `Lazy[T]`

- If you always use the dependency: declare `T` directly.
- If you need the instance synchronously (no `await`): you can't —
  `Lazy[T]` is async-resolution by construction.

## Type alias

`a2kit.packages.di.Lazy` is `Callable[[], Awaitable[T]]`. The dispatcher
recognizes both the alias and the raw `Callable[[], Awaitable[T]]`
shape, so type-checking aliases through other names also works.
