# Promotion Audit — 2026-05-28

First applied audit under [`CONSTITUTION.md`](../CONSTITUTION.md). Maps
every package under `a2kit/src/a2kit/packages/` and
`a2web/src/a2web/packages/` against Articles I-IV (substrate/product,
placement hierarchy, adopt-before-build, promotion triggers).

**Audit method:** three parallel research agents (one per package
surface), each reading the Constitution, applying article checklists,
and running OSS landscape research per Article III. Verdicts
cross-confirmed across agents.

**Key structural insight (cross-confirmed):**

> **a2kit has exactly ONE confirmed consumer today: a2web.**
>
> Per Article IV, no Tier-5 (a2kit core) promotions are justified.
> Most Tier-4→Tier-3 extractions are speculative until
> a2atlassian/a2db/joi-hub/a2kay actually import. Article I's
> Two-Consumer Test is bottlenecked by the migration backlog.

---

## Unified promotion table

### Tier 2 → Tier 3 (extract to standalone PyPI)

| Package | Target name | Why |
|---|---|---|
| `a2kit/packages/formatter` | `a2format` | 745 LOC, **zero a2kit imports** — trivial detach. Solves real OSS gap (`Page[T]` + JSON/TSV/page-tsv routing not in FastAPI/FastMCP/Click/pydantic). |
| `a2kit/packages/log` | `a2log` | 977 LOC, 2 exception types to inline. Tool-call telemetry with ambient context + MCP/CLI dual sinks is recurring reinvention. |

### Tier 4 → Tier 3 (extract, but Article-III research required FIRST)

| Package | Article-III gap |
|---|---|
| `a2kit/packages/di` | No `_deps.md` rejecting `dishka` / `lagom` / `punq` exists. Must write before extraction. |
| `a2kit/packages/connections` | Validate by importing in a2atlassian first; if cross-product use materializes, extract. |

### Tier 2 → Tier 3 (a2web/packages/)

| Package | Target | Trigger needed |
|---|---|---|
| `a2web/packages/proxy_routing` | `a2proxyroute` | Named 2nd consumer (a2atlassian upstream rotation plausible). (host, tier, fallback, CB, quarantine) primitive is genuine PyPI gap. |

### DEMOTE / REPLACE (Article III says adopt OSS)

| Package | Replace with | Why |
|---|---|---|
| `a2web/packages/http_cache` | [hishel](https://github.com/karpetrosyan/hishel) | RFC 9111-correct, SQLite backend, ETag/Last-Modified, httpx-native. Citable rejection required if NOT adopting (likely `profile_hash` composition logic). |

### SLIM aggressively (Article V refusal applied)

| Package | LOC | Why |
|---|---|---|
| `a2kit/packages/dispatch` | 1553 | 8 stages where 3 self-skip — self-justifying complexity. Collapse `TimeoutStage`+`ErrorCaptureStage`+`CallScopeStage` into one middleware; keep `EnricherStage`/`AuthorizeGateStage`/`DispatchHookStage` as the only polymorphic seams. |
| `a2kit/packages/codemode` | 580 | Wrapper around FastMCP's own CodeMode + SandboxProvider protocol. Dissolve into ~50 lines in a2web; delete the wrapper. |

### HIGH Article-III DEBT (research before any move)

| Package | LOC | Why |
|---|---|---|
| `a2web/packages/llm_extract/` | 1345 | Competes with `instructor` + `litellm` + `diskcache`. Plausible 2nd consumer (a2kay) — but needs *very* citable rejection of instructor or risks "rewrote tenacity because we didn't want a decorator" anti-pattern. |

### STAY (correctly placed today)

**a2web:** `browser_pool` (no 2nd consumer), `block_detector` (single-consumer + asset value), `content_extract` (already thin wrapper over trafilatura).

**a2kit:** `lint`*, `otel` (thin adopt-not-build), `testing` (a2kit-coupled harness), `_plugin` (Article I 2-consumer test fails today), `http`, `mcp`, `cli`, `auth` (substrate but a2kit-coupled; no Tier-5 trigger).

\* **One nuance**: `lint` is actually two things — (a) generic Rego engine + generic rules (body_dup, name_collision, pyproject, github_actions) which IS standalone-valuable, and (b) a2kit-specific `A2K-*` rules. Splitting is a separate future decision; defer until generic-rules audience materializes.

---

## Recommended sequencing

```
ACTIONABLE NOW (no new consumers needed)
  - Write Article-III research for: di, llm_extract, http_cache
  - Decide: split lint into generic Rego + a2kit-specific
  - Dissolve codemode (likely safe; verify a2web doesn't use it)

WAITS FOR a2web upgrade (validates against a real consumer)
  - http_cache → hishel adoption (refactor needed)
  - dispatch slim (high blast-radius — do with consumer on it)

WAITS FOR 2ND PRODUCT MIGRATION
  - Promote proxy_routing → a2proxyroute (need 2nd consumer)
  - Promote connections → standalone (need a2atlassian to import)
  - Reconsider plugin / http / mcp / cli for Tier 5 (need ≥3 products)
  - Extract a2format / a2log (extract AS SIDE EFFECT of 2nd-consumer
    migration, not before — extraction's value materializes only when
    a2atlassian/a2db imports the standalone package instead of a2kit)
```

## Honest recommendation

**Don't act on extractions yet.** The 1-consumer reality (only a2web)
means extractions today give nothing — a2web already imports
`a2kit.packages.formatter`. Extraction's value materializes when
a2atlassian or a2db imports `a2format` *instead of* a2kit.

The audit IS the deliverable. Reference it from ADRs when future
migrations happen. Pay Article-III debts incrementally as packages
are touched.

## Cross-reference

- [CONSTITUTION.md](../CONSTITUTION.md) — Articles I-IX
- [BACKLOG.md](../BACKLOG.md) — open framework + ecosystem work
- a2web wish list: `~/Workspaces/a2web/docs/history/A2KIT_WISHES_DEFERRED.md`
