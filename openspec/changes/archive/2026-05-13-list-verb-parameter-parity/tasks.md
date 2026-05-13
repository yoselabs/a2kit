# Tasks — list_ parameter parity

## 0. Prerequisites

- [ ] 0.1 Baseline green: `make lint` + `make test`.
- [ ] 0.2 `replace-surfaces-with-visibility` has landed (provides
      `visibility` kwarg shape for the parity addition).

## 1. Add the four kwargs

- [ ] 1.1 In `src/a2kit/tool.py` `list_()` signature, add
      `idempotent: bool = False`, `open_world: bool = False`,
      `title: str | None = None`,
      `visibility: Visibility | None = None`.
- [ ] 1.2 Inside the `deco` body, call `_build_annotation_kwargs`
      (the same helper used by `read`/`write`/`tool`) instead of
      hand-rolling the `annotations_kwargs={"readOnlyHint": True, ...}`
      dict.
- [ ] 1.3 Plumb `visibility` into `_stamp` like on the other verbs.

## 2. Tests

- [ ] 2.1 Test: `@a2kit.list_("id", title="My List", idempotent=True)`
      stamps `meta.annotations` with `title="My List"`,
      `idempotentHint=True`, `readOnlyHint=True`.
- [ ] 2.2 Test: `@a2kit.list_("id", visibility="cli")` stamps
      `meta.extras.visibility == "cli"`.
- [ ] 2.3 Test: `@a2kit.list_("id", destructive=True)` raises
      `TypeError` (same as `@read(destructive=True)`).
- [ ] 2.4 Test: existing `@a2kit.list_("id", "name", page_size=20)`
      unchanged (regression).

## 3. Examples + docs

- [ ] 3.1 No example app changes required.
- [ ] 3.2 If `docs/adr/0001-typer-cli.md` or any user-facing doc
      enumerates per-verb kwargs, update the `list_` row.

## 4. Verify

- [ ] 4.1 `make lint` clean.
- [ ] 4.2 `make test` — all green plus the four new tests.
- [ ] 4.3 No CHANGELOG breaking entry (pure addition).
