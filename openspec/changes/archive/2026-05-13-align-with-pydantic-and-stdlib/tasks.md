# Tasks — align-with-pydantic-and-stdlib

## 0. Prerequisites

- [x] 0.1 Baseline: `uv run pytest --no-cov` green; `make lint` green.
- [x] 0.2 Confirm `pydantic` and `weakref` are usable everywhere
      the change touches (pydantic is already a hard dep; weakref
      is stdlib).
- [x] 0.3 Grep external pinned consumers (examples/, tests/, docs/)
      for `a2kit.Param` and `meta.extra` to size the migration.

## 1. R1 — Drop `a2kit.Param`

- [x] 1.1 Delete the `Param` function from `src/a2kit/params.py`.
- [x] 1.2 Move `description_of` to `src/a2kit/_field_introspect.py`
      (new private module). Adjust internal imports
      (`src/a2kit/packages/mcp/schema.py`, `src/a2kit/packages/cli/builder.py`,
      anywhere else that imports it).
- [x] 1.3 Remove the `"Param"` entry from `_LAZY_ATTRS` in
      `src/a2kit/__init__.py`. Also remove it from `__dir__` (auto
      via dict removal).
- [x] 1.4 Migrate `examples/` call sites:
      `a2kit.Param("desc")` → `pydantic.Field(description="desc")`.
      Update imports.
- [x] 1.5 Migrate `README.md`, `examples/*/README.md`, and any
      `docs/` references.
- [x] 1.6 Add a `CHANGELOG.md` BREAKING entry with the migration
      regex.
- [x] 1.7 Test: pre-existing `Param`-using tests are rewritten in
      place to use `pydantic.Field`. The MCP-schema-description
      and CLI-help-description scenarios remain green.

## 2. R4 — Typed `A2KitMetaExtras`

- [x] 2.1 Add `class A2KitMetaExtras(BaseModel)` to
      `src/a2kit/metadata.py` with fields per design D-EXTRAS-TYPED
      (`report_type`, `report_schema`, `router_slug`, `surfaces`,
      `list_view`) and `model_config = ConfigDict(arbitrary_types_allowed=True)`.
- [x] 2.2 Change `A2KitMeta.extra: dict[str, Any]` →
      `A2KitMeta.extras: A2KitMetaExtras` with
      `default_factory=A2KitMetaExtras`.
- [x] 2.3 Reshape `stage_extra(fn, attr_name, value)` to take an
      attribute name (no string-key translation table) and `setattr`
      it on the typed model. The sibling `explicit-router-surface`
      proposal removes `stage_extra` entirely.
- [x] 2.5 Migrate readers to typed access:
  - [x] 2.5.1 `src/a2kit/packages/mcp/server.py:290` —
        `meta.extras.surfaces or Surface.ALL`.
  - [x] 2.5.2 `src/a2kit/packages/mcp/server.py:302` —
        `meta.extras.report_type`.
  - [x] 2.5.3 `src/a2kit/packages/cli/builder.py:329` —
        `meta.extras.report_type if meta is not None else None`.
  - [x] 2.5.4 `src/a2kit/packages/cli/builder.py:382` —
        `meta.extras.surfaces or Surface.ALL`.
  - [x] 2.5.5 `src/a2kit/packages/cli/schemas.py:115` —
        `meta.extras.router_slug`.
  - [x] 2.5.6 `src/a2kit/packages/cli/schemas.py:117` —
        `meta.extras.report_schema`.
  - [x] 2.5.7 `src/a2kit/packages/testing/client.py:233` —
        `meta.extras.report_type`.
  - [x] 2.5.8 `src/a2kit/packages/otel/middleware.py:83` —
        reads the **wire-dict projection** (`meta_a2kit`); per
        design D-WIRE-PROJECTION rewrite to
        `meta_a2kit.get("extras", {}).get("router_slug")`.
  - [x] 2.5.9 `src/a2kit/packages/mcp/server.py:43-45` — currently
        **mutates** `extra["a2kit.list_view"] = asdict(list_view)`
        as a wire-serialization step. Per design D-WIRE-PROJECTION
        this mutation moves to the wire-projection layer and reads
        `list_view.model_dump()` inline (no mutation of typed
        extras). Rewrite `_meta_to_dict` to dump
        `meta.extras.model_dump(mode="json")` and avoid touching
        the typed model.
- [x] 2.6 Migrate writers:
  - [x] 2.6.1 `src/a2kit/routers.py:58` — write
        `meta.extras.router_slug = self.slug` (replacing
        `meta.extra.setdefault(_ROUTER_SLUG_KEY, self.slug)`).
  - [x] 2.6.2 `src/a2kit/tool.py:176` — write `surfaces` via
        `stage_extra(fn, "surfaces", value)`.
  - [x] 2.6.3 `src/a2kit/tool.py:379` — same for `list_view`.
  - [x] 2.6.4 `src/a2kit/packages/mcp/reports.py` — same for
        `report_type` and `report_schema`.
- [x] 2.7 Drop the obsolete string constants once readers/writers
      are migrated: `_ROUTER_SLUG_KEY`, `SURFACE_META_KEY`,
      `EXTRA_TYPE_KEY`, `EXTRA_SCHEMA_KEY`. Keep the public
      `Surface` symbol in `src/a2kit/surface.py`.
- [x] 2.8 Remove `_EXTRA_DROP_FROM_WIRE` from
      `src/a2kit/packages/mcp/server.py` (declared L27, used L41).
      Grep confirms two live references, both inside `_meta_to_dict`.
      After `_meta_to_dict` is rewritten to call
      `meta.extras.model_dump(mode="json", exclude={"report_type"})`,
      the string-key filter loop is dead and the constant deletes
      with it. The `report_type` key continues to be excluded from
      the wire (it's a `type` object, not JSON-safe); this is now
      expressed via `model_dump(exclude=...)` rather than a
      separate constant.
- [x] 2.9 Lint: re-aim
      `src/a2kit/packages/lint/rules/purity.py:90` AST matcher.
      Currently `_extra_subscript_writes` walks for `ast.Subscript`
      whose `value` is `ast.Attribute(attr="extra")` with a string-
      constant slice — i.e. `<x>.extra["<key>"] = ...`. After R4
      the literal-subscript AST shape disappears entirely; writes
      become `meta.extras.<attr> = ...` (an `ast.Assign` whose
      target is an `ast.Attribute` chain ending in
      `Attribute(attr="extras")` with a child attribute). Rewrite
      the matcher to:
      - Walk `ast.Assign` targets.
      - Match `ast.Attribute` targets whose `.value` is an
        `ast.Attribute` with `attr == "extras"`.
      - Yield `(node, target.attr)` where `target.attr` is the
        new typed-field name.
      Also re-aim `_extra_dict_in_meta` (constructor-call form):
      after R4, `A2KitMeta(extra={...})` becomes
      `A2KitMeta(extras=A2KitMetaExtras(...))`; the matcher walks
      keyword `extras=` whose value is an `ast.Call` to
      `A2KitMetaExtras` and yields `(node, kw.arg)` for each
      inner keyword. Update `_FORBIDDEN_EXTRA_KEYS` (or equivalent)
      to the new attribute-name set. The larger rule rework lives
      in `loud-degrade-everywhere`.
- [x] 2.10 Test: add `tests/test_meta_extras_typed.py` covering
      attribute access for each known extra and the `stage_extra`
      string-to-attribute translation path. Existing tests that
      reach into `meta.extra` adjust to `meta.extras`.

## 3. R12 — `_param_cache` → `WeakKeyDictionary`

- [x] 3.1 In `src/a2kit/packages/di/container.py` import `weakref`
      at module top.
- [x] 3.2 Change `self._param_cache: dict[int, list[_ParamSpec]] = {}`
      to `self._param_cache: weakref.WeakKeyDictionary[Factory, list[_ParamSpec]] = weakref.WeakKeyDictionary()`.
- [x] 3.3 Update the cache read site (currently keyed by
      `id(factory)`) to key on `factory` directly. Same for the
      write site.
- [x] 3.4 Update the comment on line 132 to describe the new
      keying and reference the `signature.py` design note.
- [x] 3.5 Test: add `tests/test_container_param_cache_weak.py`:
  - [x] 3.5.1 Register a factory inside a nested function, capture
        its cache entry, drop the function from scope, force GC,
        register a new factory, assert the cache holds only the
        new entry (no stale reference).
  - [x] 3.5.2 Register a `functools.partial` and assert the
        `TypeError` at `register()` time is precise (mentions
        weak-reference unavailability and recommends a `def`
        wrapper).

## 4. Spec edits (NOT implementation)

- [x] 4.1 `openspec/specs/tool-description-contract/spec.md` — see
      delta in this change's `specs/tool-description-contract/spec.md`.
- [x] 4.2 `openspec/specs/di-container-package/spec.md` — see delta
      in this change's `specs/di-container-package/spec.md`.
- [x] 4.3 `openspec/specs/tool-descriptors/spec.md` — see delta.

## 5. Documentation

- [x] 5.1 README.md: code samples that show `a2kit.Param` switch to
      `pydantic.Field(description="...")` with a one-line note.
- [x] 5.2 `ANTIPATTERNS.md`: new entry "Reaching into
      `meta.extras` by string key" with the typed-attribute form.
- [x] 5.3 `CHANGELOG.md`: BREAKING entries for R1 and R4; R12 is
      internal-only and goes under "Fixed".

## 6. Verification

- [x] 6.1 Full suite: `make test` + `make lint` green.
- [x] 6.2 Grep `src tests examples` for `a2kit.Param` — zero hits
      expected.
- [x] 6.3 Grep `src tests examples` for `meta.extra` (singular,
      not `meta.extras`) — zero hits expected.
- [x] 6.4 Grep `src` for `id(factory)` in container code — zero
      hits expected.

## 7. Out-of-scope follow-ups

- [x] 7.1 `explicit-router-surface` removes `stage_extra` outright.
- [x] 7.2 `loud-degrade-everywhere` reworks `rule_purity`'s
      detection model. This change only adjusts the rule's key
      list minimally.
