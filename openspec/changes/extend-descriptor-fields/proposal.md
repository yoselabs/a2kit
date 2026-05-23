## Why

`ToolDescriptor` is the framework-internal projection consumed by substrate adapters (MCP server, HTTP build, CLI builder, codemode marshal). Today substrates re-derive `wire_param_names`, `lazy_param_names`, `ctx_param_name`, and read `A2KitMeta` directly to compute per-call shape. This duplicates the projection at every substrate boundary, prevents enforcing a single source of truth for tool shape, and means future substrates pay the same derivation cost.

Extend `ToolDescriptor` with the projected shape so substrates consume one immutable record. Lifecycle change (materializing at `App.build()` instead of `add_router`) is a separate proposal: [[defer-descriptor-materialization]] — without it, `wire_param_names`/`lazy_param_names` can only be populated when the container is known. This proposal lands the *fields* and the populating logic that does not depend on the container; the container-dependent fields are introduced as `None`-default until the lifecycle move lands.

## What Changes

- ADD fields to `ToolDescriptor` (frozen dataclass at `src/a2kit/tool.py`):
  - `ctx_param_name: str | None` — projection of `find_context_param(fn)` / `A2KitMeta.context_param_name`.
  - `annotations_view: Mapping[str, Any]` — read-only view of `A2KitMeta.annotations_as_dict()`; lazy-computed on first read.
  - `timeout: float | None` — projection of `A2KitMeta.extras.timeout_seconds`.
  - `lazy_param_names: frozenset[str] | None` — params whose annotation is `Lazy[T]`. `None` until [[defer-descriptor-materialization]] lands (requires container).
  - `wire_param_names: frozenset[str] | None` — params NOT resolved by container and not `Lazy[T]` and not ctx. `None` until [[defer-descriptor-materialization]].
  - `metadata_view: Mapping[str, Any]` — read-only projection of the full `A2KitMeta` (verb, tags, extras flattened). Always populated.
- POPULATE container-independent fields in existing `app._build_descriptors`.
- TEST: BDD `tests/test_tool_descriptor_projection.py` asserting each new field projects from the source meta.

## Impact

- Affected specs: `tool-descriptors` (MODIFIED — extend with new fields)
- Affected code: `src/a2kit/tool.py`, `src/a2kit/app.py` (`_build_descriptors`)
- Breaking: NO (adds fields; container-dependent fields default `None`)
- Future deps: container-dependent fields finalize via [[defer-descriptor-materialization]]; substrate adapters switch to descriptor reads via [[privatize-tool-metadata]].
