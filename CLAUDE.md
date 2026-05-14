# a2kit — agent conventions

This file is loaded into every Claude Code session for this repo. It
sets the rules for working on a2kit. Project specifics live in
OpenSpec capability specs; this file is about **how to make changes**.

## Core principles

### 1. No backward compatibility shims

When a surface is renamed, removed, or restructured: the old surface
crashes loudly with an embedded migration hint. No aliases, no
`DeprecationWarning`, no transitional period.

- Renames: the old name raises `TypeError` (or `AttributeError` with
  a substantive message) referencing the new name.
- Removed kwargs: catch them via `**_kw`, raise `TypeError` with the
  migration recipe.
- Renamed methods on canonical types (e.g. `TestClient`): override
  `__getattr__` to intercept known-old names and raise with hint.

**Reason**: graceful migration paths hide drift from consumer read
paths. Hard crashes force the migration into consumers' commit
history. v0.33 prettification established this pattern; subsequent
releases reinforce it.

### 2. No redundancy / no multiple ways of doing the same thing

If two surfaces do the same job, exactly one of them ships.
Examples retired during v0.33:

- `@app.singleton(T)` decorator form → only the method-call form
  `app.singleton(T, factory)` ships
- `@a2kit.tool` general decorator → only `@a2kit.read` / `@a2kit.write`
  / `@a2kit.list_` ship
- `name=` kwarg on verb decorators → only `fn.__name__` derivation

**Exception**: critical interop (e.g. `a2kit.ToolContext` is a lazy
re-export of `fastmcp.Context` — the alias is critical because the
cold-start budget forbids eager fastmcp import). Document the
exception inline.

### 3. No silent errors

A function that hits an unexpected condition either:
- Raises with a clear, action-oriented message, OR
- Logs at WARN+ with the same clarity AND returns a sentinel that
  the caller is forced to handle.

Specifically forbidden:

- `**kwargs` accepted but unknown keys silently ignored. Either
  validate against the declared parameter set and `raise TypeError`,
  or don't accept `**kwargs` at all.
- `except Exception: return None` (or any equivalent fallback) with
  no log line. The "decoration must not raise" rationale is fine,
  but the function MUST log what was lost.
- `getattr(obj, "x", default)` where the default masks a missing
  invariant. Use `hasattr` checks at protocol boundaries; for
  type-known objects, access directly and let `AttributeError`
  surface.
- Defensive `hasattr` against types you control. `hasattr(app, "ldd")`
  when `app: a2kit.App` is dead defense — `App` always has `.ldd`.
  Remove the branch.

### 4. Errors carry migration hints

When the framework crashes, the message includes the fix:

```python
# bad
raise TypeError("invalid kwarg")

# good
raise TypeError(
    "App(health_tool=...) was removed in v0.34. Register a check "
    "with @app.health_check to auto-install the _meta.health tool."
)
```

The pattern: name the removed surface, name the replacement, name
the version (so consumers can grep release notes).

## Patterns to use

### Loud-crash on unsupported kwargs

```python
class App:
    def __init__(self, name: str, *, lifespan=None, debug=False, **_kw):
        if _kw:
            raise TypeError(
                f"Unexpected kwargs: {sorted(_kw)}. "
                f"See CHANGELOG for v0.34 removals."
            )
        ...
```

### `__getattr__` migration hints

```python
class TestClient:
    _MIGRATED_NAMES: ClassVar[dict[str, str]] = {"call": "invoke"}
    def __getattr__(self, name: str) -> Any:
        if name in self._MIGRATED_NAMES:
            new = self._MIGRATED_NAMES[name]
            raise TypeError(
                f"TestClient.{name}(...) was renamed to "
                f"TestClient.{new}(...). Update the call site; "
                f"no alias is provided."
            )
        raise AttributeError(f"'TestClient' object has no attribute {name!r}")
```

### Validate kwargs against signature

```python
declared = set(inspect.signature(fn).parameters)
unknown = set(call_kwargs) - declared
if unknown:
    raise TypeError(
        f"{fn.__name__}() received unexpected keyword arguments: "
        f"{sorted(unknown)}"
    )
fn(**call_kwargs)
```

### When `except Exception` is justified

Three legitimate cases:

1. **Async fan-out where one consumer must not break others.** Example:
   `ldd/__init__.py` sink dispatch — one bad sink is logged with
   `.exception(...)` and skipped; sibling sinks still fire.

2. **Decoration-time must-not-raise.** Example: introspecting return
   types for schema generation during `@a2kit.read(...)`. If
   `get_type_hints(fn)` fails, the decorator still has to apply.
   But the function MUST log at WARN — see `signature.py::resolve_hints`
   for the `_WARN_ONCE` pattern.

3. **Wire-error envelope wrappers.** The MCP error envelope wrapper
   catches all exceptions and re-raises as `ToolError(json)`. The
   "swallow" here is actually a transform — the consumer sees the
   real class name and message.

Any other `except Exception` is a bug.

## Anti-patterns to look for during audits

Run periodically:

```bash
# Silent except blocks
grep -rn "except Exception\|except:" src/ --include='*.py' | \
  grep -v "raise\|log\.\|_LOGGER\.\|# why:" | head

# Defensive hasattr against known types
grep -rn "hasattr(app," src/ --include='*.py'
grep -rn "hasattr(self\.app," src/ --include='*.py'

# Silent fallback patterns
grep -rn "getattr(.*, *None) or" src/ --include='*.py'
grep -rn "return None\s*$" src/ --include='*.py' | head

# Backward-compat aliases
grep -rn "= invoke\|= call\|= read\|= write\|= list_" src/ --include='*.py'
```

## Workflow

### OpenSpec for non-trivial changes

Anything that changes a capability spec, adds a new lint rule,
removes a public surface, or shifts framework semantics goes through
OpenSpec:

```bash
# author proposal + tasks + spec delta under openspec/changes/<name>/
openspec validate --changes --strict
# implement against tasks
openspec archive <name>
```

Trivial fixes (typos, lint-noqa, single-test additions) can land
without proposals — but if the change touches a capability spec's
behaviour, it needs one.

### Spec-delta authoring under multi-change waves

When authoring multiple changes that target the same capability
spec, archive them in dependency order. Downstream `MODIFIED` /
`REMOVED` requirement titles must match the **post-prior-archive**
canonical spec headers. The archive tool matches by literal header
text; renames between waves cause `MODIFIED failed for header X —
not found` and abort the archive.

Mitigations:
- Sequence so spec headers stabilise before downstream targets them
- Author downstream deltas against the post-prior-archive state
- For pure renames, the safe pattern is `MODIFIED` keeping the
  canonical title and updating the body — not retitling

### Commits

- No GitHub PRs for solo branches — merge to `main` directly.
- Commit message style: `feat!:` / `fix:` / `chore:` prefix, terse
  subject, hyphenated breaking shape in title (`feat!: close
  v0.32 MCP blocker + 8 coordinated framework changes`).
- Long-form rationale in the body. Reference OpenSpec change names
  inline.
- Don't include emoji in commit messages unless the user explicitly
  asks (the existing Co-Authored-By footer is the only stable
  exception).

### Tests

- BDD-first: write the failing test (Gherkin-style or `pytest`-
  parametrised) before the implementation.
- Test names spell the contract: `test_call_raises_with_migration_hint`,
  not `test_call_error`.
- Real-transport tests (driving `fastmcp.Client(transport=...)`)
  catch wrapper-chain regressions that the in-process test client
  used to hide. Add a real-transport scenario for any change touching
  the MCP wrapper chain.

### Lint discipline

- `make lint` must be green. ty errors in `src/` are zero-tolerance.
- ty errors in `tests/` are tolerated (61 baseline as of v0.34); a
  separate sweep will gate them.
- `a2kit lint static` warnings: zero. Use `# noqa: A2K014` on
  intentional SLOC overage with an accompanying issue link or
  refactor TODO; everything else fixes root cause.

### Memory hygiene

The user's auto-memory lives at
`~/Documents/Knowledge/Agents/Claude/MEMORY.md`. When a session
changes a2kit's design state meaningfully, update
`project_a2kit_design_state.md`. Delete obsolete `feedback_*`
memories when their issue resolves.

## Project state hooks

- `OPERATIONAL_CONTRACTS.md` — the framework's behaviour contract.
  Updated by changes that touch dispatcher/lifecycle/transport
  semantics. Read first when authoring any change in those areas.
- `ANTIPATTERNS.md` — concrete consumer-facing anti-patterns. Add
  to it when a footgun guard ships.
- `CHANGELOG.md` `Unreleased` section — the wire shape for the next
  release. Every breaking change adds a migration table row.
- `openspec/specs/<capability>/spec.md` — the canonical behaviour
  spec for each capability. Reference these in proposals.

## Related memories (in user's MEMORY.md)

- `project_a2kit_design_state` — post-v0.33 surface
- `feedback_no_prs` — solo repos merge to main directly
- `feedback_bdd_first` — write the test first
- `feedback_a2kit_ldd_wire_format` — LDD channels invariants
- `project_a2kit_format_routing` — JSON | TSV | page-tsv wire shapes
