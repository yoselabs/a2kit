# Tasks — fix-cli-typer-vendored-click

BDD-first: the regressing scenario gets a failing test before any code
moves (TDD red → green).

## 1. Reproduce (RED)

- [x] 1.1 Add a test that assembles the CLI for an `App` with an
      `add_cli`-supplied command present and asserts the subcommand is
      reachable, written so it would have caught the vendored-click
      `TypeError` (assert on reachability, not on the click type). Put it
      next to the existing CLI builder tests.
      → `test_add_cli_attaches_under_vendored_click` in
      `tests/packages/cli/test_builder.py`. Confirmed RED: raised the exact
      downstream `TypeError` at `builder.py:601`.
- [x] 1.2 If feasible in CI without a full typer bump, parametrize /
      add a job that runs the CLI-assembly tests against `typer >= 0.26`
      so the vendored-click path is actually exercised in-repo.
      → Done in-repo *without* a typer bump: the RED test monkeypatches
      `typer.main.get_command` to return a foreign Group-like object (not a
      standalone `click.Group`), faithfully reproducing typer ≥0.26's
      vendored-click identity. This exercises the path under the pinned
      `typer 0.25.1` and survives future bumps — preferable to a CI matrix
      entry (no extra job, deterministic).

## 2. Fix the attachment guard (GREEN)

- [x] 2.1 `packages/cli/builder.py`: replace the
      `isinstance(command, _click.Group)` guard around the `cli_extras`
      loop with a structural check (the assembled root command supports
      `add_command`). Preserve the existing "not actually a group" error
      path, expressed structurally. Drop the now-unneeded
      `import click as _click` if nothing else uses it.
      → Guard now reads `getattr(command, "add_command", None)` /
      `callable`; the standalone-click import is dropped.
- [~] 2.2 `__main__.py` `LazyGroup`: **no change needed.** Investigated —
      the dev CLI is built entirely with *standalone* click
      (`@click.group(cls=LazyGroup)`, `LazyGroup(click.Group)`) and its only
      lazy subcommand (`a2kit.packages.lint.cli:main`) is also standalone
      click. There is no typer in this command tree, so the
      vendored-vs-standalone identity mismatch cannot arise. Per TDD/YAGNI,
      no failing test exists to justify a speculative change; the proposal's
      "latent seam" does not manifest. Revisit only if the dev CLI ever
      composes a typer-built command.

## 3. Verify (GREEN)

- [x] 3.1 Run the new test(s) — pass.
- [x] 3.2 Run the full CLI test suite — green, output pristine
      (full suite: 1522 passed, 50 skipped, 90.42% coverage).
- [x] 3.3 Manual smoke: covered by the connections `add_cli` end-to-end
      tests (`test_connections_subgroup_only_when_added` + the vendored
      simulation), which assemble and invoke the `add_cli` subcommand.

## 4. Close out

- [x] 4.1 lint / ruff / `ty check src/` / a2kit-static gates green on all
      touched files. (Repo-wide `ty` shows 15 pre-existing diagnostics in
      `tests/` from the in-flight `refound-ldd-on-stdlib-logging` change —
      none in files touched here; the pre-commit `ty` hook scans `src/`
      only, which is clean.)
- [x] 4.2 Wave 1 (`cli-as-surface`, ADR 0028) will re-home this compat
      handling into `CliSurface.bind` so the structural guard lives in one
      place rather than inline in `build_full_cli`.
