## MODIFIED Requirements

### Requirement: Verb decorators carry no feature kwargs

`@a2kit.read`, `@a2kit.write`, and `@a2kit.list_` MUST accept only the documented annotation keyword arguments and MUST NOT accept feature kwargs such as `enricher=` or `report=`. Other behavior is attached via stacked feature decorators where such decorators exist. The bare `@a2kit.tool` verb does not exist (removed in v0.33); this requirement covers only `read`, `write`, and `list_`.

#### Scenario: Reject enricher kwarg

- **WHEN** code calls `@a2kit.read(enricher=fn)`
- **THEN** Python raises `TypeError` for the unexpected keyword argument

#### Scenario: Reject report kwarg

- **WHEN** code calls `@a2kit.read(report=MyReport)`
- **THEN** Python raises `TypeError`

## REMOVED Requirements

### Requirement: Core exposes only a typed dispatch hook protocol

**Reason**: This requirement's only scenario polices the lint rule `A2K-CORE-CLEAN`, the string-token blocklist on core source. `A2K-CORE-CLEAN` was retired in v0.34 (documented at `src/a2kit/packages/lint/rules/purity.py:7`): the typed-extras model plus the `A2K-EXTRA-NAMESPACE` rule catch the same class of bug structurally rather than by token-matching. A scenario whose `WHEN` invokes a retired rule can never be satisfied. The import-layering discipline that this requirement gestured at is now owned by the `import-acyclicity` capability and the `A2K-LAYER` / `A2K-PKG-FRONT-DOOR` rules (see `module-layout-discipline`).

**Migration**: For core import discipline, consult the `import-acyclicity` and `module-layout-discipline` capabilities. There is no `A2K-CORE-CLEAN` rule to run; `a2kit lint static` enforces layering via `A2K-LAYER`.

### Requirement: Apps without a Connections plugin get an identity hook

**Reason**: This requirement is framed around a "Connections plugin" and "provider registry" model that predates the current DI surface. The current framework routes hookless apps through `Container.dispatch` with no `pre_hook` argument; the no-hook path is owned by the `request-scoped-di` capability's "Hookless dispatch composes without `identity_dispatch_hook`" requirement. The "identity dispatch hook" object this requirement names is not the current mechanism.

**Migration**: For hookless dispatch behavior, consult the `request-scoped-di` capability's "Hookless dispatch composes without `identity_dispatch_hook`" requirement. An App with no connections and no custom hook dispatches through `Container.dispatch(fn, wire_kwargs)` directly.

### Requirement: A2KitMeta.extra remains the only extension point

**Reason**: This requirement asserts `A2KitMeta.extra: dict[str, Any]` as a free-form namespaced carrier and forbids the DI feature from adding typed fields. The current model is the opposite: feature-specific attributes are declared on a typed `A2KitMetaExtras` class, and the `A2K-EXTRA-NAMESPACE` lint rule enforces that only declared field names are assigned. The free-form `extra` dict with `a2kit.di.*` key prefixes is no longer the contract.

**Migration**: For tool-metadata extension, declare the field on `a2kit.metadata.A2KitMetaExtras` and assign through the typed attribute. The `A2K-EXTRA-NAMESPACE` rule rejects undeclared extras. A dedicated `metadata` / `A2KitMeta` capability spec is a follow-up of the `reconcile-stale-specs` change (currently unspecced).

### Requirement: Router slug is explicit, with verbatim class-name fallback

**Reason**: This requirement asserts a three-tier slug resolution ending in a `type(self).__name__` verbatim fallback. The code (`src/a2kit/routers.py`) does not derive the slug at all: `slug: str` is a required class attribute, and `Router.__init_subclass__` raises `TypeError` if a subclass omits it. There is no constructor `name=` argument, no class-level `name` attribute, and no verbatim fallback. This requirement also directly contradicts `router-conventions`, which asserted a different (also wrong) derivation. The contradiction is resolved in favor of the code; the single true requirement lives in `router-conventions`.

**Migration**: A `Router` subclass MUST declare `slug = "..."` explicitly as a class attribute. See the `router-conventions` capability's "Router slug is an explicit class attribute" requirement for the canonical statement.
