# Tasks — prune dead decorator surface

## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint` + `make test`. Record test count.
- [ ] 0.2 Confirm zero in-repo usage of each target symbol via grep
      (`tags=`, `a2kit.Cap`, `capabilities.register`,
      `App(.*debug=`).
- [ ] 0.3 Confirm zero downstream usage by grepping the four
      consumer repos (a2web, a2db, a2atlassian, fox).

## 1. Drop `tags=` kwarg from decorators

- [ ] 1.1 Remove `tags` parameter from `tool()`, `read()`,
      `write()`, `list_()` in `src/a2kit/tool.py`.
- [ ] 1.2 Inline the auto-stamped verb tags (`"read"`, `"write"`,
      `"list"`) at the `_stamp` call site — they are no longer mixed
      with caller-supplied tags.
- [ ] 1.3 Remove any test that asserts custom-tag stamping. Keep tests
      that assert the auto-stamped verb tag.
- [ ] 1.4 Update `examples/` decorator usage if any (audit says none).

## 2. Drop `Cap` / `capabilities`

- [ ] 2.1 Delete `src/a2kit/capabilities.py`.
- [ ] 2.2 Delete `tests/test_capabilities.py`.
- [ ] 2.3 Remove `"Cap"` and `"capabilities"` from
      `src/a2kit/__init__.py` `_LAZY_ATTRS` and `__all__`.
- [ ] 2.4 Remove `TYPE_CHECKING` import in `src/a2kit/__init__.py`.
- [ ] 2.5 Remove the Cap-suggestion branch from
      `src/a2kit/packages/lint/rules/caps.py`. If the rule has no
      other purpose, delete the file and its test.

## 3. Drop `App.debug=`

- [ ] 3.1 Remove `debug` parameter from `App.__init__` in
      `src/a2kit/app.py`.
- [ ] 3.2 Remove `self.debug = debug` line.
- [ ] 3.3 Remove any test that constructs `App(..., debug=True)`.

## 4. Verify

- [ ] 4.1 `make lint` clean.
- [ ] 4.2 `make test` — same test count minus the removed test files,
      no failures.
- [ ] 4.3 `import a2kit; a2kit.Cap` raises `AttributeError`.
- [ ] 4.4 Cold-start: `python -c "import a2kit; print('ok')"`
      timing unchanged or better.

## 5. Release notes

- [ ] 5.1 CHANGELOG entry under "Breaking" with two-line migration note.
- [ ] 5.2 Notify downstream maintainers (a2web, a2db, a2atlassian, fox)
      that the next release drops `Cap` / `tags=` / `debug=`.
