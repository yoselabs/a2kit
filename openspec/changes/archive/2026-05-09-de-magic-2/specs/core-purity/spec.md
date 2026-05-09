## ADDED Requirements

### Requirement: Core source contains no feature-specific identifiers

`src/a2kit/*.py` (excluding the `packages/` subtree) MUST NOT reference, by identifier name, any of the following domain concerns: `connection`, `enricher`, `list_view`, `report_type`, `report_schema`, `router_slug`. This applies to module-level names, attribute access, function/parameter names, and class member names. String literals (including docstrings) are exempt.

#### Scenario: Lint catches enricher kwarg in core
- **WHEN** `src/a2kit/tool.py` declares a function parameter named `enricher`
- **THEN** `a2kit lint static` reports `A2K-CORE-CLEAN` against that line

#### Scenario: Lint catches connection_key attribute in core
- **WHEN** `src/a2kit/exceptions.py` defines `self.connection_key = ...`
- **THEN** `a2kit lint static` reports `A2K-CORE-CLEAN`

#### Scenario: Docstring mentioning "connection" is allowed
- **WHEN** `src/a2kit/app.py` has a docstring containing the word "connection" in prose
- **THEN** `A2K-CORE-CLEAN` does not fire (string-literal exemption)

#### Scenario: packages/ subtree is exempt
- **WHEN** `src/a2kit/packages/connections/store.py` references `connection_key` everywhere
- **THEN** `A2K-CORE-CLEAN` does not fire (rule scope is core only)

### Requirement: Extension keys on A2KitMeta.extra are namespaced

Any string-literal key written to `A2KitMeta.extra` (via subscript assignment or constructor) MUST start with the prefix `a2kit.` or with a registered package prefix matching `^[a-z][a-z0-9_]*\.`. Bare keys are rejected by lint.

#### Scenario: Lint accepts a2kit. namespace
- **WHEN** code writes `meta.extra["a2kit.enricher"] = fn`
- **THEN** `A2K-EXTRA-NAMESPACE` does not fire

#### Scenario: Lint rejects bare key
- **WHEN** code writes `meta.extra["enricher"] = fn`
- **THEN** `A2K-EXTRA-NAMESPACE` reports the line

#### Scenario: Lint accepts third-party package prefix
- **WHEN** code writes `meta.extra["acme_plugin.policy"] = "strict"`
- **THEN** `A2K-EXTRA-NAMESPACE` does not fire

### Requirement: WriteNotAllowed lives in the connections package

The `WriteNotAllowed` exception MUST be defined in `a2kit.packages.connections.exceptions` and MUST NOT be importable from `a2kit.exceptions` or re-exported by `a2kit/__init__.py`.

#### Scenario: Importing from connections package works
- **WHEN** a tool imports `from a2kit.packages.connections.exceptions import WriteNotAllowed`
- **THEN** the import succeeds

#### Scenario: Importing from core fails
- **WHEN** code attempts `from a2kit.exceptions import WriteNotAllowed`
- **THEN** the import raises `ImportError`

### Requirement: No monkey-patching in CLI builder

`a2kit.packages.cli.builder` MUST NOT mutate methods of `click.Group` or `click.Command` instances after construction. The `_wrap_main_with_app_ctx` pattern is forbidden.

#### Scenario: Build CLI does not replace group.main
- **WHEN** `build_full_cli(app)` is called
- **THEN** the returned group's `.main` attribute IS the original `click.Group.main` bound method (not a wrapper)

### Requirement: No module-level ContextVar for App propagation

Neither `a2kit.packages.cli.builder` nor `a2kit.packages.cli.app_ctx` MAY define a module-level `ContextVar` whose purpose is to propagate the active `App` to subcommands. App access in handlers must come from closures established at build time.

#### Scenario: app_ctx module is gone or empty
- **WHEN** I grep `src/a2kit/packages/cli/` for `ContextVar`
- **THEN** no result references App propagation

## ADDED Requirements

### Requirement: Verb decorators carry no feature kwargs

`@a2kit.read`, `@a2kit.write`, `@a2kit.list_`, `@a2kit.tool` MUST accept only `name`, `tags`, and `annotations` keyword arguments. Other behavior is attached via stacked feature decorators.

#### Scenario: Reject enricher kwarg
- **WHEN** code calls `@a2kit.read(enricher=fn)`
- **THEN** Python raises `TypeError: read() got an unexpected keyword argument 'enricher'`

#### Scenario: Reject report kwarg
- **WHEN** code calls `@a2kit.read(report=MyReport)`
- **THEN** Python raises `TypeError`

#### Scenario: Stacked feature decorators compose
- **WHEN** a function is decorated with `@a2kit.read()` outside `@enriches(fn)` outside `@reports(MyReport)`
- **THEN** the resulting `A2KitMeta.extra` contains both `a2kit.enricher` and `a2kit.report_type` keys

### Requirement: Router slug is explicit, with verbatim class-name fallback

A `Router` instance's `slug` MUST be one of, in order of precedence: the `name=` constructor argument, the class-level `name` attribute, or `type(self).__name__` verbatim. No string transformations (no suffix stripping, no case conversion, no character substitution) are permitted.

#### Scenario: Constructor name takes precedence
- **WHEN** `Router(name="tasks")` is instantiated on a class with `name = "X"`
- **THEN** `instance.slug == "tasks"`

#### Scenario: Class attribute used when no constructor name
- **WHEN** `class R(Router): name = "tasks"` is instantiated with no args
- **THEN** `instance.slug == "tasks"`

#### Scenario: Class name verbatim when nothing set
- **WHEN** `class TasksRouter(Router): pass` is instantiated with no args
- **THEN** `instance.slug == "TasksRouter"` (not "tasks", not "task")
