# Tasks — refine A2K-CORE-CLEAN and tighten Router type fidelity

## 0. Prerequisites

- [ ] 0.1 Baseline: `make test` + `make lint` green.
- [ ] 0.2 Inventory: count A2K-CORE-CLEAN noqas (`grep -rln
      "noqa: A2K-CORE-CLEAN" src/`) — expect ~7 files, ~24 lines.
      Record the baseline so the post-change diff is verifiable.

## 1. Retire A2K-CORE-CLEAN rule

- [ ] 1.1 Delete `_rule_a2k_core_clean` / equivalent in
      `src/a2kit/packages/lint/rules/purity.py`. Keep
      `A2K-EXTRA-NAMESPACE` and any other purity rules.
- [ ] 1.2 Remove `A2K_CORE_CLEAN` registration in
      `src/a2kit/packages/lint/static.py` (constant export +
      `_RULES` tuple entry + `__all__`).
- [ ] 1.3 Drop the rule code from any test fixture in
      `tests/packages/lint/` that pinned its existence.
- [ ] 1.4 Sweep `src/a2kit/metadata.py`, `tool.py`, `schema.py`,
      `routers.py`, `__init__.py` for `# noqa: A2K-CORE-CLEAN`
      and `# noqa: A2K-CORE-CLEAN, <other>` — remove the
      A2K-CORE-CLEAN token. Where it's the only suppression, drop
      the entire `# noqa` comment.
- [ ] 1.5 `uv run a2kit lint static src/ tests/ examples/` shows
      zero `A2K-CORE-CLEAN` warnings (confirms 1.1-1.4 wired).

## 2. Spec delta — core-purity

- [ ] 2.1 Author `openspec/changes/refine-core-clean-and-router-types/
      specs/core-purity/spec.md`:
      - REMOVED Requirement: the A2K-CORE-CLEAN requirement
        (whatever it's titled in the canonical spec)
      - Rationale block citing typed-extras structural enforcement
        as the replacement
- [ ] 2.2 Verify the spec still asserts A2K-EXTRA-NAMESPACE and any
      other live purity rules — they don't move.

## 3. Router.slug type fidelity

- [ ] 3.1 In `src/a2kit/routers.py`: change `slug: ClassVar[str]` to
      `slug: str`. Update the docstring comment to note that
      subclass class-scope assignment continues to work but the
      annotation no longer claims class-only ownership.
- [ ] 3.2 Remove `self.slug = slug` from `Router.__init__` (the
      Python class-attribute resolution path already returns the
      class-level value via `self.slug`; no instance shadow needed).
- [ ] 3.3 Drop `# ty: ignore[invalid-attribute-access]` from
      `src/a2kit/routers.py:73`.
- [ ] 3.4 Sweep call sites that read `self.slug` / `router.slug` —
      confirm they read through to class-level value unchanged.
      Grep: `\.slug\b` in src/ and tests/.

## 4. Router.lifespan protocol

- [ ] 4.1 Decide location: `src/a2kit/lifespan.py` (existing) or
      inline in `app.py`. Prefer `lifespan.py` since the protocol
      is about lifespan semantics.
- [ ] 4.2 Define `HasLifespan` Protocol:
      ```python
      class HasLifespan(Protocol):
          def lifespan(self) -> AbstractAsyncContextManager[None]: ...
      ```
      Use `typing.Protocol` with `@runtime_checkable` only if the
      runtime check is needed (probably not).
- [ ] 4.3 Update `_router_lifespan_factory` in `src/a2kit/app.py` to
      type its parameter as `Router | HasLifespan` (or just
      `HasLifespan` if Router is widened to declare lifespan in
      4.4 instead).
- [ ] 4.4 Alternative (lighter): declare `lifespan: HasLifespan |
      None = None` as a class-level attribute on `Router` itself
      with a sentinel. Decide between 4.3 and 4.4 in design.md.
- [ ] 4.5 Drop `# type: ignore[attr-defined]  # ty: ignore[unresolved
      -attribute]` from `src/a2kit/app.py:553`.

## 5. Spec delta — router-conventions

- [ ] 5.1 Author `openspec/changes/refine-core-clean-and-router-types/
      specs/router-conventions/spec.md`:
      - MODIFIED Requirement: "Router slug derives from class name
        with explicit override" — note the typing change is
        non-breaking; subclass `slug = "x"` continues to be the
        documented form
- [ ] 5.2 Optional: ADD requirement documenting `HasLifespan` if
      we want it as a contractual surface (vs. internal helper).

## 6. Verify

- [ ] 6.1 `make lint` green; baseline a2kit-static warning count
      drops by ~24.
- [ ] 6.2 `uv run ty check src/` reports zero diagnostics (down
      from current zero — confirms no regressions).
- [ ] 6.3 `make test` green.
- [ ] 6.4 Grep `# noqa: A2K-CORE-CLEAN` returns nothing in src/.
- [ ] 6.5 Grep `# ty: ignore` in src/ returns only the two
      builder.py callback-attribute lines (Typer setattr ergonomics
      — pre-existing pattern, not in scope).

## 7. Out-of-scope (documented, not done here)

- [ ] 7.1 The `builder.py` callback `__signature__` /
      `_a2kit_short_help` `ty: ignore`s — Typer-specific pattern.
      Could be replaced by `setattr(callback, ...)` but that
      changes how Typer introspects; out of scope.
- [ ] 7.2 A2K-EXTRA-NAMESPACE rule refinement (routers.py:111 has
      a comma-list noqa including this code) — separate concern;
      A2K-EXTRA-NAMESPACE is doing useful work; leave it.
