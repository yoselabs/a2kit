# a2kit — agent conventions

This file follows the [AGENTS.md](https://agentsmd.net/) convention
and is loaded by every coding agent (Claude Code, Cursor, Codex,
Aider, etc.) that supports it. It sets the rules for working on
a2kit. Project specifics live in OpenSpec capability specs; this
file is about **how to make changes**.

Claude-specific behaviour overlays this file via `CLAUDE.md`. The
two files should never disagree on tool-agnostic rules; if they do,
AGENTS.md wins and CLAUDE.md gets corrected.

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

**Tombstone sunset.** A migration-hint tombstone is a *transition
aid, not a permanent surface.* §1 forbids a transitional *behavior*
(the old path never works) but the hint itself is kept only until the
live downstream consumer has migrated past the removal — the
**migration horizon**. After that, delete the tombstone: the swept
name then raises the language-default `AttributeError` / `TypeError`
(still loud, no alias, still no transitional period — just no bespoke
hint). The migration recipe survives in the CHANGELOG and git history.
Do not let tombstones accumulate across the horizon; a permanent
monument to every past rename is the redundancy §2 forbids. The
horizon is not machine-knowable, so sweeping is a deliberate review
step, gated by an OpenSpec change (see `prune-stale-tombstones`, the
first sweep). The current in-flight cluster deliberately retained
until a2web migrates: positional `a2kit.App(...)` and `App.add_router`
(ADR 0028), the refound-ldd surface, and the v0.40 `TestClient`
renames.

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
    def __init__(self, name: str, *, config=None, **_kw):
        if _kw:
            raise TypeError(
                f"Unexpected kwargs: {sorted(_kw)}. "
                f"See CHANGELOG for removals."
            )
        ...
```

### Provider-chain configuration (ADR 0022)

Consumer-owned concerns (debug verbosity, wire-format compatibility,
transport bind addresses, secrets, telemetry endpoints, LDD level
threshold) escape source code via `A2kitConfig` (pydantic-settings)
and the `A2KIT_*` env var convention. Precedence is **inverted** from
the pydantic-settings default: env > .env > kwargs > defaults.
Developer kwargs are default **suggestions**, never **locks**. No
`freeze` / `lock` / `bypass_env` surface exists. When you build on
a2kit, apply the same pattern to your own consumer-owned concerns —
your `Settings` class is the recursive instance of a2kit's reference
implementation.

Worked examples currently in `A2kitConfig`:

- `debug` → `A2KIT_DEBUG=true` (tracebacks on stderr / in envelope).
- `mcp.structured_output` → `A2KIT_MCP__STRUCTURED_OUTPUT=true`
  (strict structured-content mode; saves tokens on hosts that
  forward `structuredContent`).
- `ldd.level` → `A2KIT_LDD__LEVEL=debug` (LDD threshold; default
  `info` drops `debug()` calls).
- `ldd.enabled` → `A2KIT_LDD__ENABLED=false` (hard kill-switch).

When you add a new sub-config, the smell to watch for: if every
emission ends up at the same level, the level isn't doing work —
promote consistently-noisy ones up, demote consistently-quiet ones
down. Levels exist to separate signals, not to be uniformly applied.

Sub-configs are DI-resolvable. `A2kitConfig` and each sub-model
(`LddConfig`, `McpConfig`, `HttpConfig`, `CliConfig`) are registered
as singleton providers on every `App`. Subsystems consume them by
typed parameter:

```python
@app.provide
def my_factory(ldd: LddConfig) -> MyService:
    return MyService(level=ldd.level)
```

Adding a new sub-config means: (1) define the pydantic model under
`a2kit.config`, (2) compose it under `A2kitConfig`, (3) add a
provider registration in `App.__init__`. The `app.config.<sub>`
attribute-walk path is reserved for consumer-side introspection,
not subsystem-side reads.

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
- `make markdown-lint` must be green. Config in `.pymarkdown.json`.
- `make adr-check` must be green (frontmatter validity + INDEX
  freshness). Pre-commit enforces this on every ADR change.

## Architecture strategy

The library's public Python surface is structured in **three tiers by
audience size** — Tier 1 `a2kit.*` (95% verb-authoring surface), Tier 2
`a2kit.<domain>` (per-audience discoverable modules like `a2kit.testing`),
Tier 3 `a2kit.packages.*` (canonical implementation home). The boundary
exists to keep the front door coherent: a name lives at top level only
if essentially every tool author uses it.

This is the load-bearing decision behind `src/a2kit/__init__.py`'s lazy
`_LAZY_ATTRS` table and behind every "we won't promote X to top level"
response. Read `docs/adr/0004-package-layout-tiered-by-audience.md`
before proposing any change to the top-level surface, and before
responding to any consumer filing that asks for promotion.

Tier 1 and Tier 2 surfaces are gated by snapshot tests under
`tests/surface/`. Adding or removing a public name produces a diff
against `expected_tier1.txt`, `expected_lazy_attrs.txt`, or one of the
`expected_tier_<domain>.txt` files; pytest fails with an ADR 0004
pointer until the snapshot is regenerated (`make surface-snapshot`)
and the corresponding ADR amendment lands. The paired diff is the
review gate.

`a2kit.App` is the **one public type** — a compose-phase builder. It
carries the mutable composition verbs (`add_router`, `add_cli`,
`add_mcp_middleware`, `provide`, `health_check`) and is handed straight
to a finisher (`a2kit.run`, `build_mcp_server`, `a2kit.testing.client`).
The finisher builds the App into a sealed internal runtime — it
snapshots the composition into a fresh container, validates the provider
graph, and owns the async-CM lifecycle; consumer code never calls a
build step and there is no public `build()`. A composition verb called
after a finisher has built a runtime is harmless — it affects only the
next build, never a running runtime. Test overrides are re-build
(construct a fresh `a2kit.App`, `provide` the fake last), never
post-build container mutation. Read `docs/adr/0019-app-runtime-split.md`
(supersedes ADR 0017) before changing the `App` surface or the DI test
seam.

Consumer-feedback discipline (how filings get triaged, how releases get
re-validated, when to cite an ADR vs ship a primitive vs decline) lives
in `docs/CONSUMER_FEEDBACK_DOCTRINE.md`, adopted by ADR 0005.

The library's **internal import graph** is tiered too — the
internal-graph sibling of the public tiering above. A layer manifest
(`a2kit.packages.lint.layers.LAYER_MANIFEST`) assigns every package and
the `core` pseudo-unit an integer layer (L0 kernel → L1 core → L2
connections/dispatch → L3 transports → L4 testing); a unit may import
only strictly-lower layers, plus its own. Two lint rules enforce it:
`A2K-LAYER` (no upward import, no import cycle — `TYPE_CHECKING` imports
included) and `A2K-PKG-FRONT-DOOR` (a cross-package import targets
`a2kit.packages.X`, never a deep submodule). Read
`docs/adr/0015-internal-layer-dag.md` before moving a package between
layers or adding a cross-package import.

## Project state hooks

- `OPERATIONAL_CONTRACTS.md` — the framework's behaviour contract.
  Updated by changes that touch dispatcher/lifecycle/transport
  semantics. Read first when authoring any change in those areas.
- `ANTIPATTERNS.md` — concrete consumer-facing anti-patterns. Add
  to it when a footgun guard ships.
- `CHANGELOG.md` `Unreleased` section — the wire shape for the next
  release. Every breaking change adds a migration table row. Also
  the primary response medium for consumer feedback per ADR 0005.
- `openspec/specs/<capability>/spec.md` — the canonical behaviour
  spec for each capability. Reference these in proposals.
- `docs/adr/INDEX.md` — **the agent entry point** for the decision
  log. Auto-generated by `scripts/adr_index.py` from YAML frontmatter
  in each ADR. Load this once to see every recorded decision (status,
  tags, Y-statement), then follow links to read full bodies only when
  needed. Never edit by hand — `make adr-index` regenerates it; the
  pre-commit hook enforces freshness. ADR 0007 records the ADR system
  design (template, frontmatter, no static site).
- `docs/adr/` — append-only architecture decision records. See
  `docs/adr/README.md` for the prescription and the required YAML
  frontmatter schema (also at `docs/adr/schema.json`). ADR 0004
  (package layout) and ADR 0002 (pydantic.Field author surface) are
  referenced by recurring consumer filings; cite them when declining.
- `docs/CONSUMER_FEEDBACK_DOCTRINE.md` — framework⇄consumer
  interaction rules (adopted by ADR 0005). Read before responding to
  a friction filing or authoring a release-adoption report.
- `BACKLOG.md` — active queue of deferred work. Each item is parked
  with its trigger condition. Pick items by triggers firing, not by
  date.
