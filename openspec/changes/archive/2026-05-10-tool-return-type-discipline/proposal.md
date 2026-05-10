## Why

`ANTIPATTERNS.md` entry #2 documents a lint rule named `A2K-LOCAL-RETURN-MODEL` that flags `BaseModel` subclasses defined inside function or closure scope when used as tool return types — the doc says "treat as a hard convention if you're not running the linter." The rule does not exist in `src/a2kit/packages/lint/rules/`. The folklore is real; the enforcement isn't. Consumers (a2web among them) carry comments like "antipattern #2" because the promised guard never shipped. This change ships the missing rule and a parallel decoration-time check, and adds one small test helper (`a2kit.testing.peek`) that pairs with `Container.resolve_sync` from change `app-lifecycle-and-di-ergonomics`.

## What Changes

- **NEW**: lint rule `A2K-LOCAL-RETURN-MODEL` in `src/a2kit/packages/lint/rules/local_return_model.py`. Static AST visitor that fires when a function decorated with `@a2kit.read`, `@a2kit.write`, or `@a2kit.list_` declares a return annotation whose root identifier resolves to a `BaseModel` subclass defined inside a non-module scope (function, classmethod, closure) within the same module. Walks generic `Subscript` annotations (`Page[Result]`, `list[Result]`). Skips `if TYPE_CHECKING:` blocks. Wired into the rule registry alongside `A2K-LDD-REPORT-TYPE`.
- **NEW**: decoration-time check in `src/a2kit/tool.py` (sibling to existing `_check_return`) that walks the return type, peels generic args, and inspects each reachable model's `__qualname__` for non-module-scope indicators. Raises `InvalidToolReturnTypeError` with a clear message citing rule code `A2K-LOCAL-RETURN-MODEL`.
- **NEW**: `a2kit.testing.peek(app, type_) -> Any` — one-line wrapper over `app.container().resolve_sync(type_)`. Lives in `src/a2kit/packages/testing/`. Documented as test-only; gives a discoverable name for the test pattern. Depends on `resolve_sync` shipping in change `app-lifecycle-and-di-ergonomics`.
- **DOC**: `ANTIPATTERNS.md` entry #2 is updated to reference the live lint rule and runtime exception by name; the "treat as a hard convention" language is removed.
- Out of scope: every other a2kit antipattern (we add exactly one rule); structured event emission and the `ctx.event` replacement (those move into `fastmcp-context-passthrough` since they're tightly coupled to the Context surface change).

## Capabilities

### New Capabilities

- `tool-return-type-discipline`: defines the lint rule (`A2K-LOCAL-RETURN-MODEL`), the decoration-time runtime check, and the documentation-must-match-implementation invariant. Includes scenarios for true/false positives, generic carriers, `TYPE_CHECKING` exemption, and the registration-time raise path.
- `test-container-peek`: defines `a2kit.testing.peek(app, T)` as a thin sync-resolve helper for tests.

### Modified Capabilities

- None. (The earlier draft modified `mcp-context-passthrough`; that delta has moved into the `fastmcp-context-passthrough` change itself.)

## Impact

- **Code added**: ~80 LOC for the lint rule + tests, ~20 LOC for the decoration-time check + tests, ~20 LOC for `testing.peek` + tests.
- **Public API**: additive — new lint rule code, new test helper. `InvalidToolReturnTypeError` raise condition broadens (currently fires for antipattern #1; now also fires for #2).
- **Dependencies**: depends on `Container.resolve_sync` from `app-lifecycle-and-di-ergonomics` (for `testing.peek`). That change ships in 0.24 (additive); this change can ship in the same release or fast-follow.
- **Cold start**: lint rule is in `packages/lint/`, not on the bare-import path; `a2kit.testing` is import-lazy.
- **Downstream**: a2web removes "antipattern #2" comments from `models.py` (the rule now flags it for real); replaces `await container.resolve(T, connection=None)` test peeks with `a2kit.testing.peek(app, T)` for tests where the chain is sync.
- **Breaking risk**: the decoration-time check could fail to import existing modules that have an in-function `BaseModel` return type. We treat this as a *correctness fix* — those modules were producing schemas that FastMCP couldn't introspect (the documented failure mode). If we discover any in-tree, hoist them as part of this change.
- **Specs touched**: new `tool-return-type-discipline` and `test-container-peek` specs. ANTIPATTERNS.md updated.
