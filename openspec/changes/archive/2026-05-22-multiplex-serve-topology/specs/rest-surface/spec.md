## ADDED Requirements

### Requirement: The REST surface is a mounted ASGI sub-application

The REST surface SHALL be produced by `a2kit.packages.rest.build_rest_app(app)`, which SHALL return an ASGI (Starlette) application built from the `a2kit.App`. The multiplexed server SHALL mount it under `/api`. `build_rest_app` and its dependencies SHALL be importable only on the `serve` path, never at `import a2kit`.

#### Scenario: REST surface is built from the App

- **GIVEN** an `a2kit.App`
- **WHEN** `build_rest_app(app)` is called
- **THEN** it returns an ASGI application
- **AND** the application carries no per-tool route definitions written by the author

#### Scenario: REST module is not imported eagerly

- **WHEN** `import a2kit` runs in a fresh interpreter
- **THEN** `a2kit.packages.rest` is absent from `sys.modules`

### Requirement: The REST surface serves a health route and an OpenAPI document

The REST sub-application SHALL serve a health route that returns a success status when the server is running, and an OpenAPI document describing the surface. The OpenAPI document SHALL carry an `info` section derived from `app.name`. In this capability's initial form the document's `paths` MAY be empty of per-tool routes — per-tool route projection is a later requirement on this capability and is out of scope here.

#### Scenario: Health route responds

- **GIVEN** a multiplexed server started with the REST surface enabled
- **WHEN** an HTTP client requests the health route under `/api`
- **THEN** the response carries a success status code

#### Scenario: OpenAPI document is served

- **GIVEN** a multiplexed server started with the REST surface enabled
- **WHEN** an HTTP client requests the OpenAPI document under `/api`
- **THEN** the response is a valid OpenAPI document whose `info` reflects the App's name
