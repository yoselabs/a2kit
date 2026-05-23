## 1. BDD first

- [x] 1.1 Write `tests/packages/context/test_principal.py` covering: construction, frozen invariant (`FrozenInstanceError` on mutation), equality semantics by field, default `raw_token=None`, `claims` accepted as any `Mapping`.

## 2. Define the type

- [x] 2.1 New file `src/a2kit/packages/context/principal.py`: frozen `@dataclass(frozen=True, slots=True)` `Principal` with the documented fields.
- [x] 2.2 Re-export from `src/a2kit/packages/context/__init__.py`.
- [x] 2.3 Add lazy `a2kit.Principal` via the existing `__getattr__` in `src/a2kit/__init__.py`.

## 3. Cold-start verification

- [x] 3.1 Existing cold-start test still green (`import a2kit` does not import `packages.context.principal`).
- [x] 3.2 New micro-assertion (in the same cold-start test file) that `a2kit` module dict does not contain `Principal` until first attribute access.

## 4. Spec sync

- [x] 4.1 New spec `openspec/specs/principal-type/spec.md` with the dataclass-shape + framework-ownership requirements + scenarios.

## 5. Final gates

- [x] 5.1 `openspec validate --strict add-principal-type` passes.
- [x] 5.2 `make lint` green.
- [x] 5.3 `make test` green.
