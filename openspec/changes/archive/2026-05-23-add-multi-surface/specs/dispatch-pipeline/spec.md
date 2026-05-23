## ADDED Requirements

### Requirement: Signature installer is substrate-parameterised

The dispatch package SHALL expose `install_substrate_signature(fn, substrate, container)`. Splitter semantics, substrate-reserved allowlists, and wrapper generation are defined by the `substrate-signature-split` capability. The function name `install_mcp_signature` SHALL be removed; any consumer importing the old name SHALL receive an `ImportError`.

#### Scenario: Old name is removed

- **WHEN** any module attempts to import `install_mcp_signature` from any path
- **THEN** an `ImportError` is raised
- **AND** the import-discipline lint (`A2K-IMPORT-DISCIPLINE`) catches stale references in the codebase
