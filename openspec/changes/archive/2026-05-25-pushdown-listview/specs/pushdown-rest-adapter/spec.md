## ADDED Requirements

### Requirement: REST adapter package is opt-in

`a2kit.packages.pushdown_rest` SHALL be opt-in via
`pip install 'a2kit[pushdown-rest]'`. The package SHALL declare
`httpx>=0.27` as its sole runtime dep.

### Requirement: `RestPushdown` is configured per-tool

`RestPushdown(endpoint, *, filter_param, fields_param, cursor_param, size_param, cel_to_query=None)`
SHALL accept per-tool configuration of which query parameter names
the backend uses. Defaults are conservative — if any of the four
`*_param` arguments is `None`, that listview operation raises
`PushdownNotSupported` (the agent surface still works; just no
pushdown for that dimension).

#### Scenario: Param name configuration
- **WHEN** `RestPushdown(endpoint="https://api.example.com/things", fields_param="fields", cursor_param="cursor", size_param="limit")` is constructed
- **THEN** subsequent `fields(...)` / `page(...)` calls accumulate `?fields=...&cursor=...&limit=...` query params

#### Scenario: Missing param config raises
- **WHEN** `RestPushdown` is constructed without a `cursor_param` and a tool tries to paginate
- **THEN** `page(...)` raises `PushdownNotSupported`; the middleware falls back to post-hoc

### Requirement: REST adapter accepts a user-supplied CEL translator

`cel_to_query` SHALL be a `Callable[[str], dict[str, str]] | None`
that the user provides to translate a CEL expression to backend
query params. If `None`, calling `filter(...)` raises
`PushdownNotSupported`.

#### Scenario: User-supplied translator
- **WHEN** the user provides `cel_to_query=lambda expr: {"q": _to_lucene(expr)}` and the agent supplies `filter="title:foo"`
- **THEN** the resulting state has the user-translated query params merged in

#### Scenario: No translator → graceful fallback
- **WHEN** `cel_to_query=None` and a filter is supplied
- **THEN** the adapter raises `PushdownNotSupported`; middleware falls back to post-hoc filtering on the executed result

### Requirement: `execute` issues an authenticated GET

`RestPushdown.execute(state)` SHALL issue an HTTP GET to
`endpoint?<accumulated query params>` and return the response as
parsed JSON. The body SHALL be a list of dicts; if the body is a
dict with a documented "results" key, the adapter accepts that shape
via a `results_path` config option (e.g. `"data.items"`).
