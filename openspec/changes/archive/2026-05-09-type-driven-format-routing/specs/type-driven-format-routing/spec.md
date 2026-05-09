## ADDED Requirements

### Requirement: `_infer_format_hint` maps return types to wire-format hints

`_infer_format_hint(return_type) -> Literal["tsv", "json", "page-tsv"]` SHALL deterministically map a resolved return-type annotation to a wire-format hint per the table below. The function SHALL default to `"json"` for any input it cannot positively prove tabular.

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
- **WHEN** `_infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"tsv"`

#### Scenario: list of model with list field → JSON
- **GIVEN** `class Task(BaseModel): id: str; labels: list[str]` and a tool `-> list[Task]`
- **WHEN** `_infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: list of model with nested model field → JSON
- **GIVEN** `class Reporter(BaseModel): name: str; email: str` and `class Task(BaseModel): id: str; reporter: Reporter` and a tool `-> list[Task]`
- **WHEN** `_infer_format_hint(list[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: single BaseModel → JSON
- **GIVEN** a tool `-> Task` (single record)
- **WHEN** `_infer_format_hint(Task)` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Page[scalar-only] → page-tsv
- **GIVEN** a tool `-> Page[Task]` where `Task` is scalar-only
- **WHEN** `_infer_format_hint(Page[Task])` is evaluated
- **THEN** the result is `"page-tsv"`

#### Scenario: Page[non-scalar] → JSON
- **GIVEN** a tool `-> Page[Task]` where `Task` has a list field
- **WHEN** `_infer_format_hint(Page[Task])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Subclass of Page → same rules apply
- **GIVEN** `class SearchPage(Page[Task]): total: int` (where `Task` is scalar-only)
- **WHEN** `_infer_format_hint(SearchPage)` is evaluated
- **THEN** the result is `"page-tsv"`

#### Scenario: Bare `Page` without parameter → JSON
- **GIVEN** a tool annotated `-> Page` (unparameterized)
- **WHEN** `_infer_format_hint(Page)` is evaluated
- **THEN** the result is `"json"` (no type to inspect)

#### Scenario: list[scalar] → JSON
- **GIVEN** a tool `-> list[str]`
- **WHEN** `_infer_format_hint(list[str])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: dict → JSON
- **GIVEN** a tool `-> dict[str, int]`
- **WHEN** `_infer_format_hint(dict[str, int])` is evaluated
- **THEN** the result is `"json"`

#### Scenario: Any / missing → JSON
- **GIVEN** a tool with no annotation, or annotated `-> Any`
- **WHEN** `_infer_format_hint` is invoked
- **THEN** the result is `"json"`

#### Scenario: Union of incompatible shapes → JSON
- **GIVEN** a tool `-> list[Task] | ErrorEnvelope`
- **WHEN** `_infer_format_hint` is evaluated
- **THEN** the result is `"json"`

### Requirement: `_is_dump_scalar` defines the scalar whitelist

A type annotation SHALL be considered "dump-scalar" if and only if it (or, for `Optional`/`Annotated`, its inner type) is one of: `str`, `int`, `float`, `bool`, `None`/`type(None)`, `bytes`, `datetime.datetime`, `datetime.date`, `datetime.time`, `decimal.Decimal`, `uuid.UUID`, any `enum.Enum` subclass, any `typing.Literal[...]`. Containers (`list`, `tuple`, `set`, `dict`) and any `BaseModel` subclass SHALL NOT be considered scalar.

#### Scenario: Optional[str] is scalar
- **GIVEN** a model field annotated `Optional[str]`
- **WHEN** `_is_dump_scalar(Optional[str])` is evaluated
- **THEN** the result is `True`

#### Scenario: Annotated[int, ...] is scalar
- **GIVEN** a field annotated `Annotated[int, Field(ge=0)]`
- **WHEN** `_is_dump_scalar(Annotated[int, Field(ge=0)])` is evaluated
- **THEN** the result is `True`

#### Scenario: list[str] is not scalar
- **GIVEN** a field annotated `list[str]`
- **WHEN** `_is_dump_scalar(list[str])` is evaluated
- **THEN** the result is `False`

#### Scenario: Enum member type is scalar
- **GIVEN** `class Status(str, Enum): OPEN = "open"; DONE = "done"`
- **WHEN** `_is_dump_scalar(Status)` is evaluated
- **THEN** the result is `True`

### Requirement: TSV encoder uses stdlib csv, declared field order

`encode_tsv(rows, columns)` SHALL emit a header line of `columns` separated by `\t` (tab), one data row per input record, and `\n` (LF) line terminator. The encoder SHALL use `csv.QUOTE_MINIMAL`. `columns` SHALL be passed in declared `BaseModel.model_fields` order — alphabetical sorting is forbidden. Each row SHALL be obtained from `row.model_dump(mode="json")` so dates / UUIDs / enums become wire-friendly scalars. If a value is a `list` or `dict` (only reachable when `format_hint="tsv"` is forced on a non-uniform shape), the encoder SHALL JSON-blob it into the cell.

#### Scenario: Round-trip through stdlib csv
- **GIVEN** rows `[Task(id="a", title="x"), Task(id="b", title="y, z")]` (note comma)
- **WHEN** `encode_tsv(rows, columns=["id", "title"])` is evaluated
- **THEN** the output is `"id\ttitle\na\tx\nb\ty, z\n"` — comma in title does NOT trigger quoting (only tab/newline/quote characters do)

#### Scenario: Header preserves model field order
- **GIVEN** `class Task(BaseModel): id: str; created: datetime; title: str` (note declaration order)
- **WHEN** the TSV encoder is invoked with `columns` from `Task.model_fields`
- **THEN** the header line is `"id\tcreated\ttitle"` — declaration order, not alphabetical

#### Scenario: Datetime fields render via model_dump
- **GIVEN** `Task(id="a", created=datetime(2026,5,9,17,0,0))` with `created: datetime`
- **WHEN** the TSV row is encoded
- **THEN** the `created` cell is the ISO 8601 string `"2026-05-09T17:00:00"` (whatever `model_dump(mode="json")` produces for that field)

### Requirement: `page-tsv` encoder produces JSON envelope with embedded TSV string

`encode_page_tsv(page)` SHALL return a JSON-encoded string conforming to `{"items": <tsv-string>, "next_cursor": <str | null>, "_items_format": "tsv", ...other Page fields}`. The `items` value SHALL be the TSV-encoded items (header + rows, `\n`-separated, trailing `\n`), serialized as a single JSON string. Additional `Page` subclass fields (e.g., `total`, `has_more`) SHALL be passed through as JSON values alongside `items`.

#### Scenario: Plain Page[Task] hybrid encoding
- **GIVEN** `Page[Task](items=[Task(id="a", title="x"), Task(id="b", title="y")], next_cursor="c1")` where `Task` is scalar-only
- **WHEN** `encode_page_tsv(page)` is evaluated
- **THEN** the output is JSON of the form `{"items":"id\ttitle\na\tx\nb\ty\n","next_cursor":"c1","_items_format":"tsv"}` — exact key order may vary, but those three keys are present and `_items_format` is exactly `"tsv"`

#### Scenario: Subclass with extra metadata
- **GIVEN** `class SearchPage(Page[Task]): total: int` and a value `SearchPage(items=[Task(id="a", title="x")], next_cursor=None, total=42)`
- **WHEN** `encode_page_tsv(page)` is evaluated
- **THEN** the output JSON includes `"total":42` alongside the other envelope fields

#### Scenario: Empty items
- **GIVEN** `Page[Task](items=[], next_cursor=None)`
- **WHEN** `encode_page_tsv(page)` is evaluated
- **THEN** the `items` value is the header line followed by `\n` (no data rows) and `_items_format` is `"tsv"`

### Requirement: `format_response` accepts `"tsv"` and `"page-tsv"` as first-class hints

`format_response(raw, *, format_hint)` SHALL accept `format_hint` values `"auto"`, `"toon"`, `"json"`, `"tsv"`, `"page-tsv"`. Explicit hints SHALL bypass type inference and dispatch directly to the corresponding encoder.

#### Scenario: Explicit `"tsv"` honored on a list of scalar-only models
- **GIVEN** `raw = [Task(...), Task(...)]`
- **WHEN** `format_response(raw, format_hint="tsv")` is called
- **THEN** the response data is the output of `encode_tsv` and `Response.format` is `"tsv"`

#### Scenario: Explicit `"page-tsv"` honored on a Page
- **GIVEN** `raw = Page[Task](items=[...], next_cursor="x")`
- **WHEN** `format_response(raw, format_hint="page-tsv")` is called
- **THEN** the response data is the output of `encode_page_tsv` and `Response.format` is `"json"` (the wire format is JSON; `_items_format` discriminates)

### Requirement: Auto-format consults the cached descriptor hint

When `format_hint="auto"` is passed to `format_response` from `_invoke_tool_in_process`, the runtime SHALL pass the descriptor's pre-computed `format_hint` instead of re-running any heuristic. The legacy `toon_or_json` helper SHALL NOT be invoked from `_invoke_tool_in_process`. `toon_or_json` remains exported for backward compatibility but is documented as deprecated.

#### Scenario: Tool with `-> list[Task]` (scalar-only) → TSV at runtime
- **GIVEN** an app with a tool annotated `-> list[Task]` (scalar-only) and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool and formats the response
- **THEN** the wire output is TSV (matches `encode_tsv` byte-for-byte)

#### Scenario: Tool with `-> Page[Task]` (scalar-only) → page-tsv at runtime
- **GIVEN** an app with a tool annotated `-> Page[Task]` and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool
- **THEN** the wire output is the hybrid JSON-with-embedded-TSV

#### Scenario: Tool with `-> Task` (single) → JSON at runtime
- **GIVEN** an app with a tool annotated `-> Task` and the user invokes the CLI with `--format auto`
- **WHEN** the runtime dispatches the tool
- **THEN** the wire output is JSON

#### Scenario: Tool without annotation → JSON at runtime
- **GIVEN** an app with a tool that has no return annotation
- **WHEN** the user invokes the CLI with `--format auto`
- **THEN** the wire output is JSON

### Requirement: `Page` is a generic pydantic model

`Page` (in `a2kit.packages.formatter.response`) SHALL be defined as `class Page(BaseModel, Generic[T])` with at least `items: list[T] = Field(default_factory=list)` and `next_cursor: str | None = None`. Construction `Page(items=[...], next_cursor="x")` SHALL remain valid. The class SHALL preserve declared field order so subclasses adding fields keep their TSV header position predictable.

#### Scenario: Generic parameterization
- **GIVEN** `class Task(BaseModel): id: str`
- **WHEN** `Page[Task](items=[Task(id="a")])` is constructed
- **THEN** the instance validates successfully and `items[0]` is a `Task`

#### Scenario: Subclass with extra metadata
- **GIVEN** `class SearchPage(Page[Task]): total: int = 0`
- **WHEN** `SearchPage(items=[], total=42)` is constructed
- **THEN** the instance validates and `total == 42`

#### Scenario: Bare construction without parameter still works
- **GIVEN** legacy code calling `Page(items=[some_dict], next_cursor=None)` (no generic parameter)
- **WHEN** the call is evaluated
- **THEN** the instance is constructed successfully (back-compat)

