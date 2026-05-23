## ADDED Requirements

### Requirement: `A2K-ONE-SIGNATURE-INSTALLER` lint rule

A new lint rule `A2K-ONE-SIGNATURE-INSTALLER` SHALL AST-scan `src/a2kit/packages/` and fail if more than one symbol matching `install_*_signature` is defined as a real function. Migration-hint raises (functions whose body is a single `raise TypeError(...)` pointing at the canonical installer) SHALL not count.

#### Scenario: Adding a second real installer is rejected

- **GIVEN** a new file defining `def install_grpc_signature(fn, ...): ...` with a real body
- **WHEN** `make lint` runs
- **THEN** `A2K-ONE-SIGNATURE-INSTALLER` raises naming the duplicate
