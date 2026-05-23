## 1. BDD first

- [x] 1.1 Write `tests/packages/dispatch/test_substrate_dep_classification.py`: FastAPI `Depends` -> substrate_dep bucket; FastAPI `Security` -> substrate_dep bucket; `Annotated[T, "non-marker-string"]` -> still wire; substrate-dep param on `fastmcp` substrate -> `SubstrateSignatureError`.

## 2. Splitter extension

- [x] 2.1 Add `substrate_dep: tuple[inspect.Parameter, ...]` to `SplitSignature`.
- [x] 2.2 Extend `split_signature` to inspect `Annotated[...]` metadata for `fastapi.params.Depends|Security` instances. Import `fastapi.params` lazily inside the function (cold-start budget).
- [x] 2.3 Update `install_substrate_signature` for `substrate="fastapi"` to include substrate-dep params in the generated `__signature__` (preserving their original `Annotated` metadata).
- [x] 2.4 Update `install_substrate_signature` for `substrate="fastmcp"` to raise `SubstrateSignatureError` with the documented hint when substrate-dep params are present.

## 3. Lint rule

- [x] 3.1 BDD: `tests/packages/lint/rules/test_substrate_dep.py` — marker-on-default-expose tool flagged; marker-on-`expose=("api",)` tool passes; non-marker `Annotated` ignored.
- [x] 3.2 New rule module `src/a2kit/packages/lint/rules/substrate_dep.py` implementing `A2K-SUBSTRATE-DEP`.
- [x] 3.3 Wire into `packages/lint/static.py` (constant + import + dispatch table).

## 4. Spec sync

- [x] 4.1 New spec `openspec/specs/substrate-dep-class/spec.md`.
- [x] 4.2 Modify `openspec/specs/module-layout-discipline/spec.md` with the new lint rule requirement.

## 5. Final gates

- [x] 5.1 `openspec validate --strict add-substrate-dep-class` passes.
- [x] 5.2 `make lint` green.
- [x] 5.3 `make test` green.
- [x] 5.4 Cold-start budget unaffected: `import a2kit` still does not import `fastapi`.
