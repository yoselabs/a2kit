## Why

`add-auth` and the substrate-DI bridge both need a substrate-neutral identity record. Today each transport (FastAPI `Security` outputs, FastMCP `Context`) carries its own shape. Defining `Principal` once, owned by the framework (not by any auth wrapper), lets every downstream piece consume `principal: Principal` by type annotation alone and lets auth wrappers stay producers rather than redefining the type.

This is carved out of the larger [[bridge-di-to-substrate-native]] umbrella as a single-cycle foundational piece: nothing in this change references substrates, bridges, or the dispatch pipeline. The `Principal` lands first so [[propagate-principal-and-authorize]] and [[add-auth]] can refer to it.

## What Changes

- ADD `Principal` frozen dataclass at `src/a2kit/packages/context/principal.py`. Shape: `{subject: str, scopes: frozenset[str], claims: Mapping[str, Any], issued_by: str, raw_token: str | None}`. `raw_token` is opaque, frame-of-reference for downstream re-validation; the framework never parses it.
- RE-EXPORT `Principal` from the `a2kit.packages.context` front door.
- RE-EXPORT lazily from `a2kit.Principal` via the existing PEP 562 `__getattr__` on `a2kit/__init__.py` (no eager import).
- Cold-start budget check unchanged: `import a2kit` does not pay any new cost; reading `a2kit.Principal` pays the one-time `packages.context` import.

## Impact

- Affected specs: NEW `principal-type` capability (owns the dataclass shape + ownership rule).
- Affected code: new `packages/context/principal.py`; `packages/context/__init__.py` re-export; `a2kit/__init__.py` lazy attr.
- Breaking: none.
- Depends on: none.
- Unblocks: [[propagate-principal-and-authorize]], [[add-auth]].
