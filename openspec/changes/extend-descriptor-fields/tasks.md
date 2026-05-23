## 1. Extend `ToolDescriptor`

- [x] 1.1 Add fields to `src/a2kit/tool.py:ToolDescriptor`: `ctx_param_name: str | None`, `timeout: float | None`, `lazy_param_names: frozenset[str] | None`, `wire_param_names: frozenset[str] | None`, plus property-style `annotations_view` and `metadata_view` (cached, lazy on first access — keep dataclass frozen by storing the source meta and projecting on read).
- [x] 1.2 Default `lazy_param_names = None` and `wire_param_names = None` (populated by [[defer-descriptor-materialization]]).
- [x] 1.3 Decide projection mechanism: either store a private `_meta: A2KitMeta | None` field on the descriptor and project via `@property`, OR materialize all projections eagerly at construction. Pick eager materialization for `ctx_param_name`/`timeout`/`annotations_view`/`metadata_view` to keep descriptor self-contained and not retain a back-pointer to mutable `A2KitMeta`.

## 2. Populate at materialization

- [x] 2.1 Update `src/a2kit/app.py:_build_descriptors` to populate `ctx_param_name`, `timeout`, `annotations_view`, `metadata_view`.
- [x] 2.2 `annotations_view` SHALL be the result of `meta.annotations_as_dict()` (dict shape, no `mcp.types` import) wrapped in `types.MappingProxyType` for immutability.
- [x] 2.3 `metadata_view` SHALL flatten `{verb, tags, context_param_name, extras_dict}` from `A2KitMeta`. Use `types.MappingProxyType`.

## 3. BDD test

- [x] 3.1 Write `tests/test_tool_descriptor_projection.py` BEFORE implementation.
- [x] 3.2 Given a tool decorated with `@a2kit.read(timeout=5.0)`, descriptor exposes `timeout == 5.0`.
- [x] 3.3 Given a tool with a `ctx: Context` param, descriptor exposes `ctx_param_name == "ctx"`.
- [x] 3.4 Given a tool with `annotations=ToolAnnotations(read_only_hint=True)`, descriptor's `annotations_view["readOnlyHint"] is True`.
- [x] 3.5 Given any decorated tool, `metadata_view["verb"]` matches the decorator family.
- [x] 3.6 Container-dependent fields default to `None` and tests assert that (sentinel for [[defer-descriptor-materialization]]).

## 4. Spec sync

- [x] 4.1 Modify `openspec/specs/tool-descriptors/spec.md`: add Requirement covering the new fields and projection guarantee.

## 5. Verification

- [x] 5.1 `openspec validate --strict extend-descriptor-fields` passes.
- [x] 5.2 `make lint` green.
- [x] 5.3 `make test` green; new BDD test passes.
