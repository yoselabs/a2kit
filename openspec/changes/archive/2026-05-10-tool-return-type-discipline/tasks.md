## 1. Pre-flight: scan tree for existing violations

- [x] 1.1 `grep -rn "class.*BaseModel" src/` filtered to in-function/in-method definitions; record any hits.
- [x] 1.2 For each hit, verify whether it is used as a tool return type. If yes, hoist to module scope as part of this change's PR. If no, leave alone (the rule only fires for return types).

## 2. Lint rule: A2K-LOCAL-RETURN-MODEL

- [x] 2.1 Create `src/a2kit/packages/lint/rules/local_return_model.py` with `rule_local_return_model(tree, filename, source)` AST visitor following the same shape as `rule_ldd_report_type`.
- [x] 2.2 Implement two-pass detection: (1) walk module AST collecting `BaseModel` subclasses partitioned by scope (module-scope = ok set; non-module-scope = flag set); (2) walk decorated tool functions (`@a2kit.read`/`write`/`list_`, alias-aware via existing import-tracking helper) and check each `returns` annotation's root identifier(s) against the flag set.
- [x] 2.3 Handle generic `Subscript` annotations by walking the `slice` (single arg or `Tuple` for multi-arg generics).
- [x] 2.4 Skip `ClassDef` nodes inside `If(test=Name(id="TYPE_CHECKING"))` blocks.
- [x] 2.5 Add `A2K_LOCAL_RETURN_MODEL = "A2K-LOCAL-RETURN-MODEL"` constant in `src/a2kit/packages/lint/static.py` and wire it into `_RULES` and `__all__`.
- [x] 2.6 Tests: in-function direct return fires; generic param fires; module-scope class passes; imported class passes; TYPE_CHECKING block passes; inner class of module-scope class passes; multiple violations in one module each fire once at correct line numbers.

## 3. Decoration-time runtime check

- [x] 3.1 Add `_check_return_scope(return_type)` in `src/a2kit/tool.py` next to existing `_check_return`. Walk `typing.get_type_hints` output and `typing.get_args` for generic carriers; for each reachable concrete class, check `"<locals>" in getattr(cls, "__qualname__", "")`.
- [x] 3.2 Wire the new check into the decoration machinery so it runs alongside `_check_return` at module import time.
- [x] 3.3 Raise `InvalidToolReturnTypeError(f"return type {cls.__qualname__} is defined in non-module scope; see A2K-LOCAL-RETURN-MODEL")`.
- [x] 3.4 Tests: import-time raise for in-function model; passes for module-scope model; raises for generic carrier with offending arg; clear error message format.

## 4. `a2kit.testing.peek`

- [x] 4.1 Add `peek(app, type_) -> Any` in `src/a2kit/packages/testing/__init__.py` (or a new `peek.py` re-exported via `__init__`). Implementation: `app.container().resolve_sync(type_)`.
- [x] 4.2 Docstring: "Test-only sync container peek. Production code should resolve via the container during dispatch."
- [x] 4.3 Tests: resolves registered singleton; raises `SyncResolveUnavailable` for async chain; propagates unregistered-type exception unchanged.

## 5. Documentation

- [x] 5.1 Update `ANTIPATTERNS.md` entry #2's last paragraph to reference the live `A2K-LOCAL-RETURN-MODEL` rule and `InvalidToolReturnTypeError` as both enforced; remove the "treat as a hard convention if you're not running the linter" language.
- [x] 5.2 `CHANGELOG.md` entry: new lint rule, new decoration-time check, `a2kit.testing.peek` helper.

## 6. Verification

- [x] 6.1 `make test` — full suite green.
- [x] 6.2 `make lint` — confirm the new rule does not fire on a2kit's own tree (any deliberate exception requires `# noqa: A2K-LOCAL-RETURN-MODEL` with justification).
- [x] 6.3 `openspec validate tool-return-type-discipline --strict`.
- [x] 6.4 Confirm dependency: `Container.resolve_sync` is available (depends on `app-lifecycle-and-di-ergonomics` having shipped or being co-merged).
