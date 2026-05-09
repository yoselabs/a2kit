# Mirror gaps (working doc — delete at end of Phase 3)

A2K-TEST-MIRROR reports 18 missing mirrors at HEAD (run:
`uv run a2kit lint static src/ tests/`).

## Top-level core (4)

| Source | Expected mirror |
|---|---|
| `src/a2kit/exceptions.py` | `tests/test_exceptions.py` |
| `src/a2kit/routers.py` | `tests/test_routers.py` |
| `src/a2kit/signature.py` | `tests/test_signature.py` |
| `src/a2kit/tool.py` | `tests/test_tool.py` |

## Lint subsystem (9)

| Source | Expected mirror | Coverage source today |
|---|---|---|
| `src/a2kit/packages/lint/cli.py` | `tests/packages/lint/test_cli.py` | (none) |
| `src/a2kit/packages/lint/rules/budget.py` | `tests/packages/lint/rules/test_budget.py` | `test_rules_misc.py` |
| `src/a2kit/packages/lint/rules/caps.py` | `tests/packages/lint/rules/test_caps.py` | `test_rules_misc.py` |
| `src/a2kit/packages/lint/rules/conn.py` | `tests/packages/lint/rules/test_conn.py` | `test_rules_misc.py` |
| `src/a2kit/packages/lint/rules/cross.py` | `tests/packages/lint/rules/test_cross.py` | `test_rules_misc.py` |
| `src/a2kit/packages/lint/rules/importing.py` | `tests/packages/lint/rules/test_importing.py` | `test_rules_misc.py` |
| `src/a2kit/packages/lint/rules/ldd.py` | `tests/packages/lint/rules/test_ldd.py` | `test_rules_ldd.py` |
| `src/a2kit/packages/lint/rules/purity.py` | `tests/packages/lint/rules/test_purity.py` | `test_core_purity.py` + `test_extra_namespace.py` |
| `src/a2kit/packages/lint/rules/shape.py` | `tests/packages/lint/rules/test_shape.py` | `test_rules_shape.py` |

## Plugin packages (5)

| Source | Expected mirror |
|---|---|
| `src/a2kit/packages/connections/exceptions.py` | `tests/packages/connections/test_exceptions.py` |
| `src/a2kit/packages/mcp/reports.py` | `tests/packages/mcp/test_reports.py` |
| `src/a2kit/packages/otel/tracer.py` | `tests/packages/otel/test_tracer.py` |
| `src/a2kit/packages/testing/exceptions.py` | `tests/packages/testing/test_exceptions.py` |
| `src/a2kit/packages/testing/fixtures.py` | `tests/packages/testing/test_fixtures.py` |

## Plan per design.md D-MIRROR-SPLIT-VS-MERGE

- **Top-level core**: split — each file is large enough to warrant its own per-file test mirror.
- **Lint rules**: split into per-rule mirrors. The omnibus files (`test_rules_*`) stay temporarily as re-exports until tests are migrated; then deleted.
- **Plugin packages**: split for `reports.py`, `tracer.py`, `fixtures.py` (all > 30 LOC); stub mirrors for `exceptions.py` files (small enums of exception classes).
