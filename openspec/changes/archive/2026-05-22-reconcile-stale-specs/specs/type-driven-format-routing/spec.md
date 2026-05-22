## ADDED Requirements

### Requirement: `infer_format_hint` maps return types to wire-format hints

`infer_format_hint(return_type) -> Literal["tsv", "json", "page-tsv"]` SHALL deterministically map a resolved return-type annotation to a wire-format hint per the table below. The function SHALL default to `"json"` for any input it cannot positively prove tabular. The function is a public symbol of `a2kit.packages.formatter` — exported as `infer_format_hint`, not underscore-prefixed.

| Return annotation | Hint |
|---|---|
| `None`, `Any`, missing annotation | `"json"` |
| `list[T]` / `tuple[T]` where `T` is a `BaseModel` and `T` is dump-scalar-only | `"tsv"` |
| `list[T]` / `tuple[T]` where `T` is *not* a scalar-only `BaseModel` | `"json"` |
| `Page[T]` (or subclass) where `T` is a `BaseModel` and `T` is dump-scalar-only | `"page-tsv"` |
| `Page[T]` (or subclass) where `T` is *not* a scalar-only `BaseModel` | `"json"` |
| Single `BaseModel`, `dict[K, V]`, `list[scalar]`, scalars | `"json"` |
| `Union[A, B]`, `Optional[non-scalar]` at the top level | `"json"` |

#### Scenario: list of scalar-only model → TSV

- **GIVEN** `class Task(BaseModel): id: str; title: str; status: str` and a tool `-> list[Task]`
- **WHEN** `infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"tsv"`

#### Scenario: list of model with list field → JSON

- **GIVEN** `class Task(BaseModel): id: str; labels: list[str]` and a tool `-> list[Task]`
- **WHEN** `infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: list of model with nested model field → JSON

- **GIVEN** `class Reporter(BaseModel): name: str; email: str` and `class Task(BaseModel): id: str; reporter: Reporter` and a tool `-> list[Task]`
- **WHEN** `infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: single BaseModel → JSON

- **GIVEN** a tool `-> Task` (single record)
- **WHEN** `infer_format_hint(Task)` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Page[scalar-only] → page-tsv

- **GIVEN** a tool `-> Page[Task]` where `Task` is scalar-only
- **WHEN** `infer_format_hint(Page[Task])` is evaluated
- **THEN** the result is `"page-tsv"`

#### Scenario: Page[non-scalar] → JSON

- **GIVEN** a tool `-> Page[Task]` where `Task` has a list field
- **WHEN** `infer_format_hint(Page[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Subclass of Page → same rules apply

- **GIVEN** `class SearchPage(Page[Task]): total: int` (where `Task` is scalar-only)
- **WHEN** `infer_format_hint(SearchPage)` is evaluated
- **THEN** the result is `"page-tsv"`

#### Scenario: Bare `Page` without parameter → JSON

- **GIVEN** a tool annotated `-> Page` (unparameterized)
- **WHEN** `infer_format_hint(Page)` is evaluated
- **THEN** the result is `"json"` (no type to inspect)

#### Scenario: list[scalar] → JSON

- **GIVEN** a tool `-> list[str]`
- **WHEN** `infer_format_hint(list[str])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: dict → JSON

- **GIVEN** a tool `-> dict[str, int]`
- **WHEN** `infer_format_hint(dict[str, int])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Any / missing → JSON

- **GIVEN** a tool with no annotation, or annotated `-> Any`
- **WHEN** `infer_format_hint` is invoked
- **THEN** the result is `"json"`

#### Scenario: Union of incompatible shapes → JSON

- **GIVEN** a tool `-> list[Task] | ErrorEnvelope`
- **WHEN** `infer_format_hint` is evaluated
- **THEN** the result is `"json"`

## REMOVED Requirements

### Requirement: `_infer_format_hint` maps return types to wire-format hints

**Reason**: The function is named `infer_format_hint` (public, no underscore prefix) and is exported from `a2kit.packages.formatter`. The spec named it `_infer_format_hint`, an underscore-private name that does not match the code. The behavior is unchanged; only the symbol name drifted. Replaced by the ADDED "`infer_format_hint` maps return types to wire-format hints" requirement.

**Migration**: Reference `infer_format_hint` (importable as `from a2kit.packages.formatter import infer_format_hint`). There is no underscore-prefixed `_infer_format_hint`.
