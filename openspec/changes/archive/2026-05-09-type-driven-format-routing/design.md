## Context

This change builds on `fix-cli-pydantic-render`, which establishes that the formatter normalizes `BaseModel` inputs via `model_dump(mode="json")` before encoding. With that contract in place, the next question is *how the formatter decides which encoder to call*.

Today's `toon_or_json` heuristic walks the runtime payload to choose between TOON and JSON. K research R122 (2026-05-09, `~/Documents/Knowledge/Researches/122-wire-format-token-benchmark/`) measured this empirically: TOON has no win zone in token cost, ties TSV (~4%) only on pure-scalar rows, and *loses to JSON* by 16-20% on every shape with a list or nested-dict column. The walker also makes the *wrong* decision for the dominant tracker shape (`list[dict]` with a list column) — picking TOON when JSON would have been smaller.

Rather than fix the heuristic, this change replaces it. Tools already declare typed return annotations; the format choice is a pure function of the type. We compute it once at app build, cache it on a typed `ToolDescriptor`, and look it up at call time.

The `Page` envelope is the realistic shape for paginated tools. Today it's an opaque dataclass; v1 routes it to JSON. R122 shows that 95% of `Page`'s payload bytes live in `items` — exactly the shape TSV wins. A hybrid format (JSON envelope + embedded TSV string for items) recovers the win without a third top-level wire format.

## Goals / Non-Goals

**Goals:**
- Replace runtime payload-walking with type-driven routing decided at app build.
- Drop TOON from the auto menu (still available via explicit `format_hint="toon"`).
- Reintroduce TSV for the empirically-dominant `list[scalar-BaseModel]` shape.
- Hybrid encoding for `Page[T]` where `T` is scalar-only: JSON envelope, TSV-as-string in `items`, explicit `_items_format` discriminator.
- Provide a typed `ToolDescriptor` introspection surface (closes the original signal's "tools() returns bound methods" complaint).
- Safe fallback to JSON for any unanalyzable type.

**Non-Goals:**
- Generic envelope detection beyond `Page[T]` (any `BaseModel` with a `list[Item]` field plus scalar metadata). Could be added later; v1 special-cases `Page`.
- Comprehension A/B testing (does the model *understand* TSV as well as JSON for tool output). Token cost is the metric; comprehension is a follow-up.
- Custom TSV dialects (ASCII unit separator, etc.). Stdlib csv with QUOTE_MINIMAL.
- Streaming encoders. Full materialization, single-shot encoding, like today.
- Removing `toon_or_json` from the public API. Kept for callers, marked deprecated.

## Decisions

### Decision 1: Type-driven routing, computed at app build

`App.add_router(router)` materializes a `ToolDescriptor` for each tool the router exposes. The descriptor includes `format_hint: Literal["tsv", "json", "page-tsv"]` computed from `typing.get_type_hints(fn)["return"]`. At call time, `_invoke_tool_in_process` reads the cached hint instead of running a heuristic.

Rationale: the tool's return type *is* the contract. We already trust it for FastMCP schema generation; we trust it here too. Walking the payload at every call is wasted work.

Alternative considered: **runtime adaptive routing** (the predicate sketched in earlier discussion — single-pass O(rows) walk with early exit). Rejected as the primary mechanism because (a) it costs work on every call, (b) it can't see Page envelopes from the inside without extra coupling, (c) the introspection-surface bug is fixed for free by materializing descriptors. Kept as a fallback only when the type is unanalyzable (`Any`, untyped, unresolved forward ref) — and even then we just route to JSON.

### Decision 2: Routing rule

```
def _infer_format_hint(rt) -> Literal["tsv", "json", "page-tsv"]:
    if rt is None or rt is Any:
        return "json"

    origin = get_origin(rt) or rt

    # Page[T] (or subclass) — hybrid envelope
    if isinstance(origin, type) and issubclass(origin, Page):
        args = get_args(rt)
        if len(args) == 1 and _is_basemodel(args[0]) and _model_is_scalar_only(args[0]):
            return "page-tsv"
        return "json"

    # list[T] / tuple[T] — TSV if T is scalar-only BaseModel
    if origin in (list, tuple):
        args = get_args(rt)
        if len(args) == 1 and _is_basemodel(args[0]) and _model_is_scalar_only(args[0]):
            return "tsv"
        return "json"

    # Single BaseModel, dict, scalars, Union, anything else
    return "json"
```

`_model_is_scalar_only(cls)` walks `cls.model_fields` and confirms every field's annotation passes `_is_dump_scalar` (after unwrapping `Optional`, `Annotated`).

`_is_dump_scalar` whitelist: `str | int | float | bool | None | datetime | date | time | UUID | Decimal | Enum subclass | Literal[...]`. Matches what `model_dump(mode="json")` produces.

Rationale: every branch defaults to `"json"` on ambiguity. The TSV/page-tsv paths require a positive proof that the data is uniformly tabular. False negatives (route to JSON when TSV would have worked) cost ~30% tokens; false positives (route to TSV when shape isn't uniform) produce malformed output. Asymmetric — bias to safety.

Alternative considered: detect any `BaseModel` envelope shape (one `list[Item]` field + scalar metadata) generically. Rejected for v1 — adds complexity, edge cases (multiple list fields? optional items?), and `Page` is the documented public envelope. If users want hybrid encoding, they use `Page[T]`.

### Decision 3: Hybrid `page-tsv` wire format

Output is JSON-shaped, with `items` as an embedded TSV string and `_items_format` as a discriminator:

```
{"items":"key\tsummary\tstatus\nPROJ-1\tFoo\tOpen\nPROJ-2\tBar\tDone\n","next_cursor":"abc","_items_format":"tsv"}
```

`Response.format` stays `"json"` at the top level. The discriminator lets agents (and tests) tell hybrid pages from plain JSON without inspecting the items string.

Rationale: a single wire string keeps the pipeline simple. Top-level JSON keeps any JSON parser working — agents that don't know about `_items_format` see a string in `items` and can still pull `next_cursor`. Agents that do know split the items string on `\n`, take the first line as the header, comma-split the rest. Standard.

Alternatives considered:
- **Multi-part response** (`Response.data` + `Response.metadata`): rejected — touches the `Response` envelope, which has many callers, and offers no token saving over the embedded string.
- **A new top-level format** `"page-tsv"`: rejected — agents would need a new parser. Embedding inside JSON gives backward-compat.

### Decision 4: `Page` becomes a pydantic generic model

`Page` is rewritten as `class Page(BaseModel, Generic[T])` with `items: list[T] = []` and `next_cursor: str | None = None`. Existing construction (`Page(items=[...], next_cursor="x")`) stays compatible. Field order is preserved (pydantic guarantee), so TSV header order matches declaration.

Rationale: the prereq PR already requires pydantic-awareness in the formatter; making `Page` a `BaseModel` is consistent. Pydantic v2 generics give us `Page[Task]` as a first-class type. Subclassing `Page` to add `total: int | None` becomes natural pydantic field declaration.

Alternative considered: keep `Page` as `@dataclass` with `Generic[T]`. Rejected — dataclass generics are weakly supported (no validation, awkward `__class_getitem__` interplay), and we'd still need a parallel pydantic model for serialization.

Note: `Page` ships in `a2kit/packages/formatter/response.py`. Subclasses living in user code are detected via `issubclass(origin, Page)`.

### Decision 5: TSV encoder uses stdlib csv

`encode_tsv(rows, columns)` uses `csv.DictWriter(delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)`. Header is the declared field order from the `BaseModel.model_fields` (not alphabetical, not `sorted()`). Values come from `row.model_dump(mode="json")`.

Edge case: if a user forces `format_hint="tsv"` on a non-uniform list, the encoder falls back to JSON-blob'ing list/dict cells (just like in R122's TSV measurement). Documented behavior; not the auto path.

Rationale: stdlib csv is correct, well-tested, fast enough. QUOTE_MINIMAL keeps output compact for the common case (no embedded tabs/newlines/quotes). `\n` line terminator keeps tokenizer-friendly (vs `\r\n`).

### Decision 6: Where the descriptor lives

A new module `a2kit/packages/formatter/inference.py` owns `_infer_format_hint`, `_model_is_scalar_only`, `_is_dump_scalar`. The `ToolDescriptor` dataclass lives in `a2kit/tool.py` (next to existing tool plumbing) — this keeps formatter concerns out of the core tool/router types and avoids a circular import (`Page` lives in formatter; descriptor needs `_infer_format_hint`, but `add_router` shouldn't import the whole formatter package eagerly).

Lazy import: `_infer_format_hint` is imported inside `App.add_router` to avoid module-level cycle.

## Risks / Trade-offs

- **Risk:** Users who returned typed pydantic models from CLI tools and got TOON output now get TSV. The wire format changes for the same tool.
  → Mitigation: documented as breaking under "auto menu changes." Hand-written callers can pin `format_hint="toon"` if they want the old behavior. CHANGELOG entry.

- **Risk:** Forward references in return annotations (common with `from __future__ import annotations`) are strings. `get_type_hints` needs the right module globals to resolve them.
  → Mitigation: call `typing.get_type_hints(fn, include_extras=True)` at descriptor build, with `localns=` and `globalns=` from the function's defining module. Standard Python introspection. If resolution fails, log once and fall back to JSON.

- **Risk:** Subclass polymorphism — declared `list[Animal]` but actual values `[Dog, Cat]` with different field sets. Type says TSV; runtime data isn't uniform.
  → Mitigation: trust the type. Document "your declared type is your routing contract." If `Animal` is scalar-only (the only way to reach TSV), all subclasses sharing the same field shape will tabularize fine. If a subclass adds fields, they're dropped at TSV encoding (csv `extrasaction="ignore"`). Consistent with what users get from a typed schema.

- **Risk:** Per-call cost shift from CLI runtime to app-build. Apps with many tools (50+) pay introspection cost at startup.
  → Mitigation: O(tools × fields × annotation depth). Realistic worst case: 100 tools × 20 fields × shallow types ≈ 2000 reflective ops. Sub-millisecond at process start.

- **Risk:** The `_items_format` discriminator is a custom convention. Agents need to know about it.
  → Mitigation: documented in README's wire-format section. Tools that prefer pure JSON can skip `Page[T]` and use a custom envelope; the routing fallback covers them. Backward-compat path for unaware agents: `items` is a string; ignoring `_items_format` still returns *something* meaningful (the raw TSV).

- **Trade-off:** TOON stays available but is unreachable from auto. Code path persists, tests persist, doc persists. Could remove entirely instead.
  → Decision: keep for now. Removal can come later if no one explicitly requests TOON in 2-3 release cycles.

- **Open**: do we need to special-case envelopes other than `Page[T]`? E.g., a user-defined `class Search(BaseModel, Generic[T])` with `items: list[T]` and `total: int`. Out of scope for v1; if signal arrives, generalize the detector.

## Migration Plan

1. **Land `fix-cli-pydantic-render`** first. Establishes `model_dump(mode="json")` as the canonical normalization step.
2. **Implement this change** on a feature branch.
3. **CHANGELOG note** under v0.23 (or whichever release): "`format_hint='auto'` is now type-driven. TOON dropped from auto menu (use `format_hint='toon'` explicitly to keep). `list[ScalarOnlyModel]` returns now encode as TSV (~30% fewer tokens). `Page` is now a generic pydantic model — annotate paginated tools as `-> Page[Task]` to opt into hybrid TSV-in-JSON encoding."
4. **Migration for users**: zero-effort if tools are already typed. Bare `Page` (no parameter) routes to JSON same as today. Bare `list[dict]` routes to JSON (was sometimes TOON, sometimes JSON). Hand-typed `list[Task]` newly gets TSV.
5. **Rollback**: revert is clean — single feature branch, no schema changes.

## Open Questions

- Should `_is_dump_scalar` accept `bytes`? Pydantic dumps bytes as base64 string in mode="json" — technically scalar after dump. Lean yes; document.
- Should `Page[T]` default `items` to `[]` or `Field(default_factory=list)`? Pydantic v2 idiom is `Field(default_factory=list)` for safety. Will use that.
- Is there a need for a `Result[T]` envelope (single record + metadata)? Out of scope; can be added if requested.
