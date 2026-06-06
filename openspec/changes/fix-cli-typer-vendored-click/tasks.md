# Tasks — fix-cli-typer-vendored-click

BDD-first: the regressing scenario gets a failing test before any code
moves (TDD red → green).

## 1. Reproduce (RED)

- [ ] 1.1 Add a test that assembles the CLI for an `App` with an
      `add_cli`-supplied command present and asserts the subcommand is
      reachable, written so it would have caught the vendored-click
      `TypeError` (assert on reachability, not on the click type). Put it
      next to the existing CLI builder tests.
- [ ] 1.2 If feasible in CI without a full typer bump, parametrize /
      add a job that runs the CLI-assembly tests against `typer >= 0.26`
      so the vendored-click path is actually exercised in-repo. Watch it
      fail (or document the failure observed under a local ≥0.26 env).

## 2. Fix the attachment guard (GREEN)

- [ ] 2.1 `packages/cli/builder.py`: replace the
      `isinstance(command, _click.Group)` guard around the `cli_extras`
      loop with a structural check (the assembled root command supports
      `add_command`). Preserve the existing "not actually a group" error
      path, expressed structurally. Drop the now-unneeded
      `import click as _click` if nothing else uses it.
- [ ] 2.2 `__main__.py`: make `LazyGroup` compose under typer's vendored
      click (subclass the click group typer itself uses, or restructure
      the lazy-load seam so it does not depend on standalone-vs-vendored
      type identity). Verify `a2kit --help` and lazy subcommand dispatch
      still work.

## 3. Verify (GREEN)

- [ ] 3.1 Run the new test(s) — pass.
- [ ] 3.2 Run the full CLI test suite — green, output pristine.
- [ ] 3.3 Manual smoke: build a small App with `add_cli`, confirm the
      subcommand runs end to end.

## 4. Close out

- [ ] 4.1 `make adr-index` / lint / typecheck gates green.
- [ ] 4.2 Note in the change that Wave 1 (`cli-as-surface`) will re-home
      this compat handling into `CliSurface.bind` (ADR 0028) so it is
      not lost as a stopgap.
