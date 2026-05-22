## Why

Web-only AI agents (ChatGPT custom connectors, Claude web, Gemini web) can only reach a remote MCP — they cannot run an a2kit CLI on the user's machine. ADR 0010 deliberately keeps a2kit's CLI auth-agnostic and parks this gap in BACKLOG, and ADR 0011 prescribes a Google OAuth recipe at the FastMCP layer, but neither tells tool authors *how* to actually build a remote MCP that serves these clients responsibly. The two unanswered questions are: (a) how does a verb running on a remote server know *which* authenticated user it's serving, and (b) which operation shapes lift cleanly to remote vs stay CLI-only. Without a documented pattern, every downstream consumer (knowledge-mcp is first, more will follow) reinvents the wiring — and reinvents the security mistakes.

## What Changes

- Add `docs/patterns/remote-mcp-access.md` documenting the canonical shape for an a2kit-based remote MCP serving web-only AI clients. Auth layer is Google per ADR 0011; no auth alternatives in scope.
- Add `examples/mcp-google-auth/` lintable reference implementation embodying the pattern end-to-end. Closes the BACKLOG "Lintable reference example for ADR 0011" entry by extending it to also cover the remote-access pattern.
- Establish the **per-user workspace** convention: a per-call DI provider reads the authenticated email from `ToolContext` and produces a `UserSession` (email + workspace dir + any per-user state) that verbs receive via DI. Uses existing a2kit primitives only — per-call DI from ADR 0009, composition-root wiring from ADR 0006, `ToolContext` passthrough from `mcp-context-passthrough`. **No new framework code.**
- Establish a **liftability rubric**: which operation shapes belong in a remote MCP (read/search over server-owned state, content generation, structured queries) vs stay CLI-only (local filesystem mutation outside the workspace, OS interop, anything assuming the user's local machine). The rubric is doc-only; the framework does not enforce it.
- Add a CI smoke test (`make example-smoke` or equivalent) that boots the example server against the bearer-token escape hatch (skipping interactive OAuth) and asserts the per-user workspace contract — so a2kit-side changes that break the pattern fail at the framework boundary, not in downstream consumers.
- Close two BACKLOG entries on landing: "Remote-MCP-only clients lose CLI access" (answered by the pattern) and "Lintable reference example for the ADR 0011 recipe" (answered by the example).

## Capabilities

### New Capabilities

- `remote-mcp-access-pattern`: the documented contract for building an a2kit-based remote MCP that serves web-only AI clients with per-user state isolation. Specifies what the pattern guarantees (authenticated identity reaches verb bodies via DI; per-user workspace paths never escape the user's namespace; liftability rubric is followed in worked examples) without adding new framework primitives.

### Modified Capabilities

None. The pattern composes existing primitives (`mcp-context-passthrough`, `di-per-call-scope`, `core-composition`); no requirement on those specs changes.

## Impact

- **New files**: `docs/patterns/remote-mcp-access.md`, `examples/mcp-google-auth/` (FastMCP server with GoogleProvider per ADR 0011, one read verb, one write verb, per-user workspace DI wiring, smoke test).
- **Modified files**: `BACKLOG.md` (remove the two now-resolved entries).
- **CI**: new `example-smoke` target invoked from `Makefile` and the existing pipeline; runs in <10s using the bearer escape hatch.
- **a2kit core**: no source changes. `a2kit.ToolContext` is the existing surface the pattern consumes; the example's per-user DI provider lives entirely in example code.
- **Downstream**: knowledge-mcp (in flight) adopts the pattern on day one and becomes the second reference point. Future themed MCPs follow the same shape.
- **Not in scope**: gateway / aggregator topology (rejected in ADR 0012), CLI-side auth (rejected in ADR 0010), non-Google auth (covered by ADR 0011's sub-recipe but not by this pattern doc), multi-tenant scenarios beyond per-Google-user isolation (separate problem).
