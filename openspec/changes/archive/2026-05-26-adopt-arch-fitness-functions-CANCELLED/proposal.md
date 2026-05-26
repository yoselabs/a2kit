## Why

a2kit already has substantial layer enforcement: `LAYER_MANIFEST`
(`src/a2kit/packages/lint/layers.py:21`) declares 7 layers (L0 kernel
packages → L6 testing); the `A2K-LAYER` rule
(`packages/lint/rules/importing.py:319-329`) catches upward imports;
`A2K-PKG-FRONT-DOOR` enforces front-door access patterns;
`FOUNDATIONAL_CORE_MODULES` and `FACADE_MODULES` carve out exemptions
that boundary tools generally can't express. The 2026-05-26 audit's
initial finding of a `dispatch → signature` layer inversion turned out
to be a misread of the manifest (signature is L2 authoring, dispatch
is L4 — L4→L2 is downward and correctly allowed by the existing
system).

A first-pass experiment with Tach 0.35.0 against a2kit's tree
confirmed the model mismatch: Tach's flat dependency graph flagged
40+ legitimate downward / facade / foundational imports as violations
because Tach has no concept of foundational-core exempt modules,
facade modules, or layer ordering. `tach sync` would just snapshot
today's graph, losing the structural value the proposal originally
promised. The honest conclusion: **Tach is the wrong shape for this
codebase** — a2kit's existing system is already more expressive than
Tach's interface model for the codebase's needs.

What a2kit's existing system **cannot** express cleanly:

**AST-level call-site rules** that the layer DAG doesn't reach
("tools must return pydantic, not `str`"; "only `_principal_bridge.py`
may import `_a2kit_request_principal`"; "no `dict[str, Any]` field on
internal dataclasses"; the planned `A2K-SURFACE-REGISTRY` rule from
BACKLOG; the "only `MANIFEST`-bearing modules under a plugin surface"
rule from `adopt-plugin-manifests`). Today these live as hand-rolled
one-off `tests/test_*.py` files or as natural-language prose in
`ANTIPATTERNS.md`. Each new rule re-discovers the AST-walk harness.

This change adopts **pytest-archon** as the shared harness for that
class of rule, and ships three foundational rules. It does NOT adopt
Tach.

Several existing BACKLOG items collapse onto the archon harness:
the `A2K-SURFACE-REGISTRY` lint rule, the "only `_principal_bridge`
imports the raw symbol" enforcement from `consolidate-principal-bridge`
(now archived), the symbol-drift gate extension to non-README docs,
and the upcoming "manifest modules only declare MANIFEST" rule from
`adopt-plugin-manifests` all become one-file archon rules on top of
one shared installation.

## What Changes

- New dev dependency: `pytest-archon`.
- New `tests/architecture/` package hosting pytest-archon rule
  modules. First three rules ship in this change:
  1. `test_packages_init_is_only_public_surface` — no `_`-prefixed
     re-exports from any `packages/<name>/__init__.py`. (Complements
     `A2K-PKG-FRONT-DOOR`, which today catches `_`-prefixed imports
     past the front door but not `_`-prefixed re-exports through it.)
  2. `test_tool_returns_are_pydantic` — captures the
     `tool-return-type-discipline` spec as an AST rule.
  3. `test_no_dict_str_any_on_internal_dataclasses` — flags
     `dict[str, Any]` fields on `@dataclass` types inside `packages/`.
     This rule is expected to find legitimate uses (JSON envelopes,
     wire-format payloads) which become explicit allowlist entries
     documented inline — the value is making each `Any` deliberate,
     not eradicating it.
- New `make arch` Makefile target: `uv run pytest tests/architecture -q`.
- `make lint` (or the umbrella check target) wires `make arch` into
  the default quality gate. CI fails on `make arch` non-zero exit.
- New OpenSpec capability `arch-fitness-functions` documenting the
  pytest-archon harness contract: every architectural invariant
  that's an AST or call-site rule SHALL be expressible as one
  pytest-archon test module under `tests/architecture/`.
- Tach is explicitly out of scope for this change. The model
  mismatch (no foundational-core exemption, no facade exemption, no
  layer ordering) is documented as a known limitation; revisit only
  if Tach's interface model evolves to express those concepts.

## Capabilities

### New Capabilities
- `arch-fitness-functions` — pytest-archon hosts AST-level /
  call-site architectural rules. The suite is wired into `make arch`
  and CI.

## Impact

- Affected code: new `tests/architecture/` package (~4 files: 3 rules
  + conftest), `Makefile` (`arch` target + `lint` dependency),
  `pyproject.toml` (one dev dep added).
- No public API change. No runtime behaviour change. Pure CI gate.
- Several BACKLOG items become trivial follow-ups: each is a new
  one-file rule under `tests/architecture/` rather than a new
  hand-rolled `tests/test_*.py`.
- Cross-ref: a2web ADR-0001 Pattern 3 (which adopted both Tach AND
  archon — a2kit takes only the archon half because the layer-DAG
  half is already substantially covered by the existing
  `A2K-LAYER` / `A2K-PKG-FRONT-DOOR` / `FOUNDATIONAL_CORE_MODULES`
  / `FACADE_MODULES` system).

## Non-goals

- **Not** adopting Tach. The model mismatch was investigated on
  2026-05-26 (during the apply session for this change) and Tach was
  removed from scope. The existing `LAYER_MANIFEST` system is the
  authority on inter-unit ordering and remains so.
- **Not** retiring any existing lint rule. `A2K-LAYER`,
  `A2K-PKG-FRONT-DOOR`, `A2K-IMPORT-DISCIPLINE`, etc. continue to
  enforce what they enforce today. Archon is additive.
- **Not** writing a `tach.toml` or any boundary-tool config.
