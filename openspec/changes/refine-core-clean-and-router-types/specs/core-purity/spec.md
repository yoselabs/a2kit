# core-purity — refine-core-clean-and-router-types delta

## REMOVED Requirements

### Requirement: Core source MUST NOT reference feature identifiers

**Reason for removal**: the rule was authored before
`A2KitMetaExtras` (the typed pydantic-`BaseModel` extras namespace)
became the canonical surface for per-tool feature metadata. Verb
decorators in `src/a2kit/tool.py` and the `Router` base in
`src/a2kit/routers.py` legitimately reference `report_type`,
`list_view`, `report_schema`, `router_slug`, `visibility`,
`timeout_seconds` — they stamp values into the typed
`A2KitMetaExtras` slots. The lint rule's intent ("don't leak feature
identifiers into core as untyped string keys") is **already enforced
structurally**: a new extras key cannot be added without editing
the `A2KitMetaExtras` pydantic model, which lives in
`src/a2kit/metadata.py`. The rule was redundant with the type
system and produced ~24 noqa suppressions in normal use.

**Migration**: the sister `A2K-EXTRA-NAMESPACE` rule (which fires
when `meta.extras.<name>` references an attribute not declared on
`A2KitMetaExtras`) still runs. That rule continues to catch the
true architectural concern — feature identifiers entering the
extras namespace without typed registration. The retired
`A2K-CORE-CLEAN` rule's coverage is subsumed by the typed model
itself.
