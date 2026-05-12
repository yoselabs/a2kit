## 1. Code removal

- [x] 1.1 Delete `src/a2kit/_docstring.py`.
- [x] 1.2 In `src/a2kit/tool.py`, remove `_augment_annotations_from_docstring`, `_resolve_hints_for_augment`, `_AUGMENT_WARN_ONCE`, and the call to the helper in `_stamp`. Remove the `param_descriptions=param_descriptions` argument passed to `A2KitMeta(...)`.
- [x] 1.3 In `src/a2kit/metadata.py`, remove the `param_descriptions: Mapping[str, str]` field on `A2KitMeta`, the `_EMPTY_PARAM_DESCRIPTIONS` sentinel, and the now-unused `MappingProxyType` / `Mapping` imports.

## 2. Test removal

- [x] 2.1 Delete `tests/test__docstring.py`.
- [x] 2.2 Delete `tests/test_param_docstring_pull.py`.
- [x] 2.3 Delete `tests/test_meta_param_descriptions.py`.
- [x] 2.4 In `tests/test_cleanup_round_5_6_code_shape.py`, remove the two WARN_ONCE tests (`test_extract_warn_once_per_fn_name`, `test_augment_warn_once_per_qualname`) and their imports.

## 3. Doc / README cleanup

- [x] 3.1 Remove the "Param descriptions from docstrings" subsection added to `README.md` in v0.29.1.
- [x] 3.2 Add a CHANGELOG entry under a new `## 0.30.0` heading flagging this as a **Removed** breaking change.

## 4. Version bump + validation

- [x] 4.1 Bump `pyproject.toml` `version` to `0.30.0`.
- [x] 4.2 Refresh `uv.lock`.
- [x] 4.3 Run `openspec validate drop-docstring-param-pull --strict`.
- [x] 4.4 Run `uv run pytest --no-cov -q` — confirm all remaining tests pass.
- [x] 4.5 Run `uv run ruff check src tests`.
