## Why

a2kit already has substantial layer enforcement: `LAYER_MANIFEST`
(`src/a2kit/packages/lint/layers.py:21`) declares 7 layers (L0 kernel
packages → L6 testing); the `A2K-LAYER` rule
(`packages/lint/rules/importing.py:319-329`) catches upward imports;
`A2K-PKG-FRONT-DOOR` enforces front-door access patterns. The
2026-05-26 audit's initial finding of a `dispatch → signature` layer
inversion turned out to be a misread of the manifest (signature is
L2 authoring, dispatch is L4 — L4→L2 is downward and correctly
allowed). So this change is NOT motivated by "the existing system is
silently broken." It's motivated by what the existing system
**cannot** express cleanly.

Two real gaps:

1. **The "private-by-default per package, `__init__.py` is the only
   public surface" invariant** is enforced by `A2K-PKG-FRONT-DOOR` as
   an AST rule today — workable, but verbose. Tach's `[[interfaces]]`
   model expresses the same invariant declaratively (one block per
   package, `interface_members = ["..."]`), which is the dominant
   rule shape across a2kit's 17 packages. a2web's ADR-0001 (2026-05-26)
   evaluated import-linter against Tach for exactly this rule and
   chose Tach because import-linter can't express
   private-by-default without enumerating every private submodule.

2. **AST-level call-site rules** that the layer DAG can't express
   ("tools must return pydantic, not `str`"; "only
   `_principal_bridge.py` may import `_a2kit_request_principal`"; "no
   `dict[str, Any]` field on internal dataclasses") today live as
   hand-rolled `tests/test_*.py` files or as natural-language prose
   in `ANTIPATTERNS.md`. pytest-archon provides a consistent harness
   for them, and several upcoming changes
   (`adopt-plugin-manifests`, the `A2K-SURFACE-REGISTRY` BACKLOG item,
   `consolidate-principal-bridge`'s "only the bridge imports the raw
   symbol" rule) all want an AST harness to bind against.

The third reason — that a2web ran the experiment on its own codebase
on 2026-05-26 and the tach.toml + pytest-archon adoption took roughly
a day to land, grandfather, and CI-wire — is the practical confidence.
a2web's tach.toml ports almost verbatim, scaled up to a2kit's 17
packages (auth, cli, codemode, connections, context, di, dispatch,
formatter, health, http, ldd, lint, mcp, otel, select, testing).

Adopting Tach + pytest-archon brings two complementary enforcement
layers that **complement, not replace,** the existing system:
- **Tach** for declarative package-interface contracts
  (private-by-default per package via `[[interfaces]]`). Sits beside
  `LAYER_MANIFEST` — the layer DAG stays as the authority on
  inter-unit ordering; Tach owns the per-package public-surface
  invariant that today's `A2K-PKG-FRONT-DOOR` enforces verbosely.
- **pytest-archon** for AST-level / call-site rules that neither the
  layer DAG nor `A2K-PKG-FRONT-DOOR` can express ("tools must return
  pydantic, not `str`"; "only `_principal_bridge.py` may import
  `_a2kit_request_principal`"; "no `dict[str, Any]` field on internal
  dataclasses").

Several existing BACKLOG items collapse into the archon harness:
the `A2K-SURFACE-REGISTRY` lint rule, the "only `_principal_bridge`
imports the raw symbol" enforcement from `consolidate-principal-bridge`,
and the symbol-drift gate for non-README docs all become archon rules
on top of one shared installation.

## What Changes

- New top-level `tach.toml` modelling every package under
  `src/a2kit/packages/*` with `depends_on = []` (and `a2kit` itself
  declaring its allowed package dependencies).
- New dev dependency: `tach` (uvx-runnable, no Python import surface).
- New dev dependency: `pytest-archon`.
- `make arch` target: runs `tach check` + the archon test class.
- `make lint` (or `make check`) wires `make arch` into the default
  quality gate.
- One-shot `tach sync` to grandfather existing violations into
  `tach.toml` exception lists; each grandfathered violation gets a
  comment block citing the BACKLOG/ADR item that retires it (mirrors
  a2web's grandfathering convention).
- Hand-rolled `tests/test_packages_independence.py` (if present) is
  superseded by Tach + a single archon rule; the test file is deleted.
- New `tests/architecture/` directory hosting pytest-archon rules.
  First three rules ship in this change:
  1. `test_packages_init_is_only_public_surface` — Tach already
     enforces module boundaries; this AST rule additionally checks
     that no package's `__init__.py` re-exports a `_`-prefixed name.
  2. `test_tool_returns_are_pydantic` — captures the existing
     `tool-return-type-discipline` spec as code.
  3. `test_no_dict_str_any_on_internal_dataclasses` — captures the
     boundary-typing taste from a2web's frozen-dataclass discipline.
- New OpenSpec capability `arch-fitness-functions` documenting the
  contract that CI fails on any new boundary or AST-rule violation.
- `module-layout-discipline` gains a requirement that Tach is the
  authoritative enforcer for the package private/public split (the
  formula in the existing spec stays as a documentation aid, but
  bypass becomes a Tach failure, not a counting test).

## Capabilities

### New Capabilities
- `arch-fitness-functions` — declarative module-boundary contracts
  (Tach) + AST-level / call-site rules (pytest-archon) form the
  framework's structural enforcement layer.

### Modified Capabilities
- `module-layout-discipline` — Tach is the authoritative private-by-default
  + cross-package-independence enforcer; counting-based tests are
  retired in favour of declarative boundaries.

## Impact

- Affected code: new `tach.toml` (top-level), new `tests/architecture/`
  package, retired `tests/test_packages_independence.py` (if present),
  `Makefile` (`make arch`, `make lint`), `pyproject.toml` (dev deps),
  CI config to fail on `make arch`.
- No public API change. No runtime behaviour change. Pure CI/structure.
- The `consolidate-principal-bridge` change can express its
  "only `_principal_bridge.py` imports the raw ContextVar" requirement
  as a one-line archon rule once this lands.
- Cross-ref: a2web ADR-0001 Pattern 3, archived change
  `openspec/changes/archive/2026-05-26-arch-fitness-functions-bootstrap/`
  in a2web.
