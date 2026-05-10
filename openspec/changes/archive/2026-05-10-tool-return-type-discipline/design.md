## Context

a2kit ships two parallel guardrail mechanisms: lint rules under `src/a2kit/packages/lint/rules/` (e.g. `A2K-LDD-REPORT-TYPE`, `A2K-IMPORT-DISCIPLINE`) and decoration-time checks in `src/a2kit/tool.py::_check_return` (currently enforces antipattern #1, the `-> str` rejection). Antipattern #2 — `BaseModel` subclasses defined in non-module scope used as tool return types — is documented as having a lint rule `A2K-LOCAL-RETURN-MODEL` that does not actually exist. Consumer code carries "treat as convention" comments and occasional latent bugs (FastMCP's `inspect.signature(eval_str=True)` cannot resolve names from a function that has already returned, so the failure mode is a server-build-time `InvalidSignature: name 'Result' is not defined` — opaque and hard to diagnose).

Separately, the `app-lifecycle-and-di-ergonomics` change introduces `Container.resolve_sync(T)` for tests that want to peek at App-scoped state. The natural pairing is a discoverable `a2kit.testing.peek(app, T)` wrapper.

This change is deliberately small: ship the missing lint rule, add a parallel runtime check, fix the doc, and add the one test helper that ties off the resolve_sync ergonomic story. Nothing here couples to the breaking `fastmcp-context-passthrough` work — the Context surface is irrelevant to return-type discipline.

## Goals / Non-Goals

**Goals:**
- Make antipattern #2 unrepresentable: lint catches it pre-run, runtime catches it at decoration time for users who don't lint.
- Match `ANTIPATTERNS.md` to reality (no more folklore-as-doc).
- Provide a discoverable test helper for sync container peek.

**Non-Goals:**
- Lint rules for any antipattern other than #2.
- Refactoring the existing `_check_return` machinery.
- Anything related to the Context surface or events bridge — those move with `fastmcp-context-passthrough`.

## Decisions

### 1. `A2K-LOCAL-RETURN-MODEL` lint rule

AST visitor in `src/a2kit/packages/lint/rules/local_return_model.py`. Detection algorithm:

1. Walk the module-level AST. For every `ClassDef` whose bases include a name resolving to `pydantic.BaseModel` (or a known subclass alias used in the project — reuse the import-tracking helpers other rules already have), record `(class_name, scope_qualname)`. Module-scope classes are the "ok set"; classes inside `FunctionDef`, `AsyncFunctionDef`, or another class's method body are the "flag set".
2. Walk every function decorated with `@a2kit.read`, `@a2kit.write`, or `@a2kit.list_` (alias-aware, same helper). Read its `returns` annotation.
3. For each annotation, extract the root identifier:
   - `Name(id="Result")` → `"Result"`
   - `Subscript(value=Name(id="Page"), slice=Name(id="Result"))` → also walk the slice; both `Page` and `Result` are checked
   - `Subscript(value=Name(id="list"), slice=Name(id="Result"))` → walk the slice
4. If a root identifier matches a class in the "flag set", emit a `LintMessage` at the **annotation site** (not the class def site, which can be far away — the user's eye is on the return annotation).
5. False-positive guard: skip `ClassDef` nodes inside an `If` whose `test` is `Name(id="TYPE_CHECKING")`. Document the limitation re: `if sys.version_info ...` (uncommon, won't fix in v1).

The rule is registered in `src/a2kit/packages/lint/static.py::_RULES` alongside the existing entries and exported via `A2K_LOCAL_RETURN_MODEL`.

**Alternatives considered:**
- *Decoration-time only* — fires only on import, costs import overhead per tool module. Lint catches issues in CI without paying that cost.
- *Lint only* — leaves users who skip the linter exposed. We ship both; the runtime check is a one-line walk over the same logic.

### 2. Decoration-time runtime check

Sibling to `_check_return` in `src/a2kit/tool.py`. Implementation: `_check_return_scope(return_type)` walks `typing.get_type_hints` output, peels `typing.get_args` for generic carriers, and inspects each reachable concrete class:

```python
def _is_module_scope(cls):
    qualname = getattr(cls, "__qualname__", "")
    # Module-scope: qualname == name (no dots) OR
    # nested-class-of-module-class (qualname like "Outer.Inner" with Outer at module scope)
    if "." not in qualname:
        return True
    # Heuristic: <locals> in qualname means defined inside a function
    return "<locals>" not in qualname
```

If any reachable model class is non-module-scope, raise `InvalidToolReturnTypeError(f"return type {cls.__qualname__} is defined in non-module scope; see A2K-LOCAL-RETURN-MODEL")`. The `<locals>` qualname marker is the unambiguous Python-builtin signal — Python sets it for any class defined in a function body.

Inner classes of module-scope classes (e.g. `Outer.Inner` where `Outer` is module-level) pass the check. They're a legitimate-if-uncommon pattern.

### 3. `a2kit.testing.peek(app, T)`

Trivial:

```python
def peek(app, type_):
    return app.container().resolve_sync(type_)
```

Lives in `src/a2kit/packages/testing/__init__.py` (or a new `peek.py` re-exported through `__init__`). The function exists primarily to give a discoverable name for the pattern; the implementation is the `resolve_sync` work in change `app-lifecycle-and-di-ergonomics`. Documented as "tests only — production code should resolve via the container."

### 4. ANTIPATTERNS.md update

Entry #2's last paragraph currently reads: "The lint rule A2K-LOCAL-RETURN-MODEL flags it; if you're not running the linter, treat it as a hard convention." Replace with: "Both `A2K-LOCAL-RETURN-MODEL` (static lint) and `InvalidToolReturnTypeError` (decoration-time, raised at import) flag this. There is no opt-out."

## Risks / Trade-offs

- [**Risk**] Decoration-time check could break existing in-tree modules that currently work by accident. **Mitigation**: pre-flight `grep` for in-function `class.*BaseModel` patterns in `src/` before merge; hoist any found. The rule's whole purpose is that these modules are subtly broken — finding them is a feature.
- [**Risk**] `<locals>` heuristic is technically a CPython implementation detail. **Mitigation**: it's been stable since 3.0 and is used by `inspect`, `pickle`, etc. Documented as "assumes CPython qualname semantics" — acceptable; a2kit targets CPython.
- [**Risk**] Lint rule false positive when a `BaseModel` is defined inside an `if sys.version_info ...` branch (e.g. a Python 3.11+ vs 3.10 split). **Mitigation**: rare in practice; can extend the exempted-condition list later if it bites.
- [**Trade-off**] `a2kit.testing.peek` is a one-liner; some would argue it doesn't deserve a public symbol. **Mitigation**: discoverability is the point. Documented and short. Cost is one symbol.

## Migration Plan

1. Land `app-lifecycle-and-di-ergonomics` (provides `resolve_sync`).
2. Land this change.
3. a2web upgrades, removes "antipattern #2" comments, switches test peek calls to `a2kit.testing.peek(app, T)`.

If any in-tree a2kit module is currently violating antipattern #2 (none expected, but we'll confirm), hoist its `BaseModel` to module scope as part of this change's PR. Rollback: revert the rule registration line + the decoration check call site; the rest is dead code that can stay or be removed independently.

## Resolved Decisions

- **Lint + runtime, not one or the other.** Lint is the cheap CI gate; runtime is the safety net for users who skip lint. Cost of duplication is one extra walk over the same logic.
- **`<locals>` as the non-module-scope signal.** Stable across CPython versions, well-known, used by stdlib introspection. Reject more elaborate scope detection.
- **`a2kit.testing.peek` is a public symbol despite being a one-liner.** Discoverability over minimalism; tests are a first-class consumer.
