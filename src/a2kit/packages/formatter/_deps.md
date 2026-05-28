# formatter — dependency decisions

Per [`CONSTITUTION.md`](../../../../CONSTITUTION.md) Article VIII. Each
adopted or rejected dependency for this package lists its decision
ADR. This file is the **single index** consulted before any dep
discussion for this package.

## Adopted

| Dependency | Version pin | Decision ADR | Last reviewed |
|---|---|---|---|
| `pydantic` | `>=2,<3` (project-level) | implicit via a2kit core | 2026-05-28 (audit) |
| stdlib `json` | — | implicit | 2026-05-28 |
| stdlib `csv` | — | implicit (TSV writer) | 2026-05-28 |

## Rejected

*(none recorded yet — this is a future-facing record per Article VIII.
Rejections will be added as they arise. Example shape below.)*

```
| Dependency | Considered for | Decision ADR | Re-evaluation trigger | Last reviewed |
|---|---|---|---|---|
| `tabulate` | TSV serialization | ADR XXXX | tabulate ships v1.0 with envelope support | 2026-05-28 |
```

## Notes

This package is a **Tier-3 extraction candidate** per
`docs/PROMOTION_AUDIT.md` — when extracted to standalone PyPI
(`a2format`), this file moves with it.
