## Why

The HTTP surface **ignores `visibility`**. `build_http_app` filters
projection tools on `"api" in desc.expose` alone (`http/build.py:83-84`
and again at `:331-332` for the DI wiring) and never consults
`desc._meta.extras.visibility`. The MCP surface, by contrast, *does*
honor it — `server.py:87` skips any tool whose visibility is not
`"all"`, and the selector path at `:302` excludes `"hidden"`.

Consequence: a verb authored as **CLI-only** or **hidden** is still
mounted as `POST /api/<name>` and is fully callable over HTTP.

- `visibility="cli"` means "operator/CLI surface only, hidden from
  MCP/API/GraphQL" (`routers.py`). It is honored on MCP and the CLI but
  **leaks onto HTTP**.
- `visibility="hidden"` (absent from `--help`, still invocable) is
  likewise skipped by MCP but mounted by HTTP.

So an operator command meant never to be network-reachable — exactly the
"CLI-only / operator surface" a2kay asked for (friction #2) — is exposed
as an unauthenticated-by-default REST endpoint the moment the HTTP
transport is served. This is a **correctness/security leak**, not a
feature gap: the intent ("not on the network") is already expressed and
already honored everywhere except HTTP.

This is the leak half of friction #4 and the load-bearing discovery
behind ADR 0028 (the operator surface *half-exists* today; the real
defect is HTTP not honoring it). It is a **standalone, non-breaking**
fix and ships ahead of the unified model (Wave 0).

## What Changes

Make the HTTP surface honor `visibility` exactly as MCP does — a tool is
mounted on `/api` only when it is exposed on `"api"` **and** its
visibility is `"all"`.

- **`packages/http/build.py`**: in both loops that walk
  `runtime.tools()` (route registration ~`:83` and the
  `dependency_overrides` wiring ~`:331`), skip any descriptor whose
  resolved visibility is not `"all"` — mirroring `server.py:87`. A
  CLI-only (`"cli"`) or `"hidden"` verb therefore registers **no** route
  and **no** DI override on the HTTP app.
- The filter reads the descriptor's `_meta.extras.visibility` defaulting
  to `"all"` (same accessor MCP uses), so the two network surfaces apply
  one identical rule.

Expressed in today's `expose` + `visibility` vocabulary. Under ADR 0028
this becomes "HTTP honors the `surfaces` matrix"; the behavior chosen
here (network surfaces drop non-`all` visibility) is forward-compatible
with that matrix — `visibility="cli"` is the `surfaces=("cli",)` /
ABSENT-on-network case.

## Capabilities

### Modified Capabilities

- `http-surface` — projection-tool mounting now filters on visibility in
  addition to `expose`. CLI-only and hidden verbs are structurally absent
  from the HTTP app (no route, no DI override), matching MCP.

## Impact

- Affected code: `src/a2kit/packages/http/build.py` (route loop + DI
  override loop).
- **Behavioral fix, not a breaking API change**: it *removes* endpoints
  that were never intended to exist. Any consumer relying on a CLI-only
  verb being reachable over HTTP was relying on the leak; the correct fix
  for them is to mark the verb `visibility="all"` (or, post-0028,
  `surfaces` include `"api"`).
- Brings HTTP into parity with MCP on visibility; closes the operator-
  surface leak so `visibility="cli"` finally means what it says on every
  surface.
- a2kay can immediately author `visibility="cli"` operator commands with
  the guarantee they are not network-reachable.

## Non-goals

- **Not** the unified `surfaces` axis (ADR 0028 Wave 2) — this keeps
  `expose` + `visibility` as-is and only fixes HTTP to honor the latter.
- **Not** changing MCP or CLI behavior (already correct).
- **Not** the offline `validate_composition` check (the other half of
  friction #4) — that is a separate Wave 3 change.
- **Not** adding auth to the HTTP surface (orthogonal; ADR 0010).
