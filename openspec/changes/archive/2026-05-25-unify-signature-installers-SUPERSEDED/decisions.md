# Decisions — unify-signature-installers (SUPERSEDED-by-architecture)

**Status:** Dropped 2026-05-25 without applying. Closed as
SUPERSEDED-by-architecture rather than completed.

## Why dropped

The proposal frames `install_mcp_signature` and
`install_substrate_signature` as redundant. They are not.

- `install_mcp_signature(fn, wrapped, app, meta)` **relabels**
  `__signature__` / `__annotations__` on a pre-built `wrapped`
  callable. The body it relabels is the folded transport-neutral
  dispatch pipeline (timeout → enrichers → router-lazy-enter →
  dispatch-hook+DI → ldd-state → error-capture, plus the
  MCP-only error-render stage). It does no body wrapping itself.

- `install_substrate_signature(fn, surface, container)` **builds a
  fresh wrapper** around `fn` that opens `Container.call_scope` per
  call. It folds nothing.

Replacing the first with the second on the MCP path would erase the
folded pipeline — ldd ambient, format routing, error capture, dispatch
hooks, timeout — from MCP-exposed tools. That is a regression, not a
refactor.

Looking for a non-trivial shared helper:

- The signature-construction body is `inspect.Signature(parameters=...)`
  — already stdlib. Extracting a wrapper named after it would be
  cosmetic.
- The two functions classify parameters differently:
  `install_mcp_signature` uses `wire_input_params` (returns
  `(wire_params, wire_scopes)` so it can synthesize `connection: str`
  when a router scope needs it); `install_substrate_signature` uses
  `split_signature` (4-bucket classification with `substrate_dep`).
  Forcing one classifier on both paths surfaces edge cases the other
  doesn't handle.
- The Context-annotation swap (`a2kit.ToolContext` → `fastmcp.Context`,
  done so pydantic can schema-generate) is MCP-only. The
  `connection`-synthesis is router-scope-aware and MCP-only.

So even a partial unification reduces to "move a one-line
`inspect.Signature(...)` call into a helper." Not worth the diff.

## The honest unification path

The two paths converge only if the HTTP path also folds the
transport-neutral dispatch pipeline. Today HTTP wraps `fn` from
scratch in `install_substrate_signature`; tomorrow it could fold the
pipeline (gaining ldd ambient, format routing, error capture, dispatch
hooks on FastAPI — desirable on its own merits). Once both paths fold
the pipeline, projection becomes "fold pipeline + relabel signature"
uniformly, and one signature-relabel function handles both surfaces.

That work is a separate change (`fold-dispatch-pipeline-on-http`,
unfiled), bigger in scope than this one, and lands a real
consolidation rather than a cosmetic one.

## ADR 0020 amendment

ADR 0020 §Consequences note 1 ("Two FastMCP code paths coexist by
design") stands. The amendment in that ADR records:

1. The Substrate-Literal architecture is superseded by Surface
   Protocol (`add-surface-protocol-additive` +
   `remove-substrate-literal`).
2. The two-installer Option-B clause stands; its discharge is gated
   on HTTP folding the dispatch pipeline.

## What this change DOES NOT touch

- No source edits.
- No spec deltas (the proposed `A2K-ONE-SIGNATURE-INSTALLER` lint
  rule is not added — the duplication is essential at the current
  architecture, so a rule forbidding it would be wrong).
- ADR 0020 gets the amendment described above.

## Next viable step

When someone is ready to fold the dispatch pipeline on the HTTP path:

1. File `fold-dispatch-pipeline-on-http` change.
2. Validate ldd ambient / format routing / error capture / dispatch
   hooks work uniformly on both paths.
3. Then re-open `unify-signature-installers` — at that point the
   unification is real, not cosmetic.
