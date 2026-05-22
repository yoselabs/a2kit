## REMOVED Requirements

### Requirement: Per-parameter descriptions via `a2kit.Param`

**Reason**: This requirement specifies an `a2kit.Param` class — `Annotated[T, a2kit.Param(description="...")]` on tool kwargs, a positional-string shorthand, and a `TypeError` on mixing positional and `description=`. No `Param` class exists anywhere in `src/a2kit/`. The capability is unimplemented: there is no per-parameter-description type. The requirement additionally references a Typer `--help` rendering path and a `_field_to_typer` adapter; a2kit's CLI is Click-based, not Typer-based.

**Migration**: There is no `a2kit.Param`. Per-parameter descriptions for tool kwargs come from the Google-style `Args:` block in the tool method's docstring (see the `router-conventions` capability's "Router tool methods may rely on the docstring for parameter descriptions" requirement). For Pydantic model body kwargs, `pydantic.Field(description=...)` continues to work (see the "Pydantic Field descriptions continue to work for body models" requirement). If a per-parameter-description type is wanted, that is a new proposal, not a reconciliation.
