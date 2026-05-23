## Context

`add-multi-surface` introduces three decorator families and a registration model. Operators now need a way to filter which registrations are exposed at runtime — for read-only audits, surface-only deploys, or demo subsets — without forking the codebase. CEL was considered and rejected for v1 (cold-start cost, expression-language docs/sandbox burden, operators rarely need OR-across-categories). A small key=value DSL with stdlib-only parsing covers the stated cases.

## Goals / Non-Goals

**Goals:**

- A shell-friendly selector syntax that's teachable in one line.
- Categories that match how operators think about deploys: verb (read-only mode), name (glob for specific tools), tag (logical grouping), surface (MCP-only or REST-only).
- Frozen on `AppRuntime` at build time — zero per-call cost.
- Composable: multiple `--select` flags AND across categories; values within a category OR; `!` for AND-NOT.
- Clean error UX at CLI parse time — exit 2 with a message naming the offending fragment.

**Non-Goals:**

- CEL or any general-purpose expression language (parked for future).
- Boolean OR across categories (`verb=read OR name=create_session`) — not expressible in v1; future-CEL escape hatch.
- Per-request re-evaluation — selector applies once at build, never at dispatch.
- `Router` class for grouping (deferred; `tag=` covers the use case).
- A `--deselect` inverse flag — negation lives inside the DSL via `!`.

## Decisions

### D1. Stdlib-only parser

```python
@dataclass(frozen=True)
class Selector:
    category: Literal["verb", "name", "tag", "surface"]
    include: frozenset[str]
    exclude: frozenset[str]

    def matches(self, desc: ToolDescriptor) -> bool: ...

def compile_selector(expr: str) -> Selector: ...
```

Parser is ~20 LOC. No `lark`, no PEG, no regex grammar — a `split("=", 1)` followed by a `split(",")` is enough for the grammar we've committed to. If/when CEL lands, the `Selector` ABI stays; only the parser changes.

**Alternatives considered:**

- *CEL via `cel-python`*: rejected for v1. Adds ~4 transitive deps, ~80-120ms cold-import. The cases operators actually need (read-only, specific tools, surface-only) don't require OR across categories.
- *JMESPath*: rejected — it's a query language for extracting values, not a predicate language for filtering. Awkward for `verb=read OR verb=list`.
- *simpleeval*: rejected — encourages Python-syntax expressions, leaking semantics, harder error UX.

### D2. Categories

| Category | Source attribute | Match semantics |
|---|---|---|
| `verb` | `desc.verb` (`read`/`list`/`write`) | string equality, OR within category |
| `name` | `desc.name` | `fnmatch.fnmatchcase()` glob, OR within category |
| `surface` | `desc.expose` (tuple of `Literal["mcp","api"]`) | accepts only values `mcp` and `api`; filter reduces `expose` to the intersection of include and the original; tool is filtered out entirely if `expose` becomes empty |

**Why these three and no more:**

- `verb` — covers "read-only mode" cleanly.
- `name` — covers "specific tools" with fnmatch wildcards.
- `surface` — covers "MCP-only deployment of a mixed app" structurally, replacing the rejected `--no-api`/`--no-mcp` flags.

**Deferred:**

- `tag=` — a2kit's verb decorators do not currently accept author-supplied `tags=` (per `verb-decorators` capability). The auto-stamped verb tags (`"read"`, `"write"`, `"list"`) would be redundant with `verb=`. `tag=` lands when (and if) a real author-tagging story arrives.
- `router=` — depends on a future `Router` class.

### D3. `surface=` interaction with auto-mount

`surface=` filtering happens before `surface-auto-mount` (from `add-multi-surface`). A projection tool with `expose=("mcp","api")` filtered by `--select 'surface=mcp'` has its effective exposure reduced to `("mcp",)` for that runtime. If post-filter no registration remains on a substrate, that substrate's mount is skipped — `--select 'surface=mcp'` thus structurally disables `/api` without any flag.

This is the clean answer to the "I wrote both projection tools and `.api` routes, but for this deploy I want MCP-only" case. Operators don't need an extra `--no-api` flag.

### D4. Negation discipline

`!value` excludes; positive values include. Within a category:

- Include-only (no `!` in values): match if descriptor's attribute is in the include set.
- Include + exclude: match if (in include) AND (not in exclude).
- Exclude-only: match if (not in exclude). Less common but legal — operators sometimes want "everything except X".

**Alternatives considered:**

- *No negation; require explicit "all-except"*: rejected — `!internal` is more ergonomic than enumerating every non-internal tag.

### D5. AND across `--select` flags

Multiple `--select` flags are ANDed. This composes the categories without needing to invent a top-level boolean DSL:

```
--select 'verb=read,list' --select 'tag=public'
   ⇒  (verb in [read,list]) AND (tag includes public)
```

**Alternatives considered:**

- *One flag with `;` separating categories*: rejected — shell quoting is worse and visual scan is harder.

### D6. Error UX

```python
class SelectorError(ValueError):
    pass
```

Raised by `compile_selector` for any parse problem. CLI wrapper catches and prints:

```
error: --select expression invalid: unknown category 'rooter'; expected verb|name|tag|surface
```

Exit code 2.

### D7. Parked future: CEL

If/when an operator needs `(verb=read OR name=create_session) AND tag=public`, the natural escape is to swap the `Selector` implementation for a CEL-backed one behind the same `Selector.matches()` interface. `cel-python` is the chosen library if/when this lands. No work today.

## Risks / Trade-offs

- **Expressiveness ceiling.** OR-across-categories not expressible. → Documented; CEL escape hatch ready if needed. Empirical observation: operators rarely cross categories — they're either filtering by audience (verb), by name, or by surface, not all at once.

- **`!`-only selectors might confuse.** `--select 'tag=!internal'` (exclude only) reads as "tag is !internal" instead of "tag includes nothing and excludes internal". → Mitigation: the documentation example explicitly shows exclude-only; the parser accepts it.

- **`surface=` is the structural surface-disable.** Operators who learn it from docs are fine; those who guess based on flag naming might miss it. → Mitigation: README's "deployment recipes" section opens with `--select 'surface=mcp'` as the canonical "MCP-only" pattern.

- **`fnmatch` is not regex.** Some operators expect regex on `name=`. → Mitigation: `--help` text explicitly states "shell-style glob; not regex"; an example shows the difference.

## Migration Plan

1. Land the DSL parser + evaluator in `packages/select/` with full unit coverage.
2. Wire `App.build(select=...)` to apply selectors before producing the `AppRuntime`.
3. Add the typer option to `serve`. Verify `--select` errors exit 2 with the expected message.
4. Update `surface-auto-mount` capability (in `add-multi-surface`) to consult filtered registrations — this is a contract refinement; no code change in the auto-mount logic itself if the rule is already "mount iff registrations remain post-filter".
5. Document in `docs/SELECT.md` with 5 worked examples. Link from `--help`.

**Rollback:** revert the change as a single commit. Operators who started using `--select` see `--select: unknown argument` and can re-pin their entry point command.

## Open Questions

None. The DSL surface, category set, error UX, and freeze point are locked. `surface=cli` is intentionally not accepted in v1 (CLI exposure is not currently modelled in `expose=`; can be added when CLI gets its own expose value). Empty selectors (`select=None` and `select=[]`) both pass through unfiltered.
