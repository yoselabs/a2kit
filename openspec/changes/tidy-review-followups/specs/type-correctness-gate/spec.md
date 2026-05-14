## MODIFIED Requirements

### Requirement: ty diagnostics suppressed only via inline `# ty: ignore[code]`

ty diagnostics in `src/a2kit/` SHALL only be suppressed via inline `# ty: ignore[<rule-code>]` comments. Each such comment SHALL include a `# why:` explanation on the same line or the line above. The total count of `# ty: ignore` comments across `src/a2kit/` SHALL be ≤ 10.

#### Scenario: Inline ignore has rationale
- **WHEN** a file contains `# ty: ignore[<code>]`
- **THEN** an adjacent `# why: ...` comment explains the third-party-stub
  or framework constraint forcing the suppression

#### Scenario: Ignore budget enforced
- **WHEN** `grep -rE "# ty: ignore" src/a2kit/ | wc -l` runs
- **THEN** the count is ≤ 10
