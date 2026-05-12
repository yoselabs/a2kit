## REMOVED Requirements

### Requirement: Per-parameter descriptions resolved from the docstring

**Reason**: The Google-style regex parser is a hand-rolled DSL on the
hot decoration path with two sources of truth (docstring text vs.
`Annotated[T, Param(...)]`). User rejected the approach in v0.29.1
review. Tool authors revert to explicit `Annotated[T, a2kit.Param(...)]`
or `pydantic.Field(description=...)` — the v0.28 surface.

**Migration**: Replace any tool that relied on docstring `Args:` for
parameter descriptions with explicit
`Annotated[T, a2kit.Param(description="...")]` wrappers.

### Requirement: Explicit Param or Field description wins over the docstring

**Reason**: With docstring resolution removed there is no precedence
question. `Annotated[T, FieldInfo(description=...)]` is the only path.

**Migration**: No action — explicit annotation is now the sole source.

### Requirement: No new third-party dependency is introduced

**Reason**: The clause existed to forbid `docstring-parser` / `griffe`
when the in-tree resolver was the in-tree alternative. With the
in-tree resolver gone the prohibition is moot.

**Migration**: None.

### Requirement: Non-goal — Numpy / Sphinx / reST docstring styles

**Reason**: The clause scoped what the resolver did *not* parse.
With the resolver gone the scope clause has nothing to scope.

**Migration**: None.
