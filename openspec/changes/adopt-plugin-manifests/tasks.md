## 1. BDD specs (write tests first)

- [ ] 1.1 Capability test `tests/capabilities/plugin_manifest/test_manifest_shape.py` — a module exporting `MANIFEST = PluginManifest(name="x", protocol=P, factory=f)` is discoverable by `load_surface(...)`; manifest fields round-trip.
- [ ] 1.2 Capability test `tests/capabilities/plugin_manifest/test_unavailable_drops_before_registry.py` — a factory returning `Unavailable("no key")` does NOT appear in the returned dict; an INFO log line records the drop.
- [ ] 1.3 Capability test `tests/capabilities/plugin_manifest/test_load_surface_sorted_priority.py` — manifests with `priority=10, 5, -1` come back in descending order; `-1` plugins appear last.
- [ ] 1.4 Capability test `tests/capabilities/plugin_manifest/test_manifest_module_no_import_side_effects.py` — every module under `packages/auth/_providers/` declares only the `MANIFEST` constant + the protocol implementation; no top-level side effects (network, env reads, registry mutation).
- [ ] 1.5 Capability test `tests/capabilities/auth/test_api_key_via_manifest.py` — `App.auth(APIKeyAuth(...))` and the manifest-driven discovery path produce structurally identical auth wiring.

## 2. Port `_plugin.py`

- [ ] 2.1 Copy a2web's `src/a2web/_plugin.py` to `src/a2kit/packages/_plugin.py` (private module — `_`-prefix).
- [ ] 2.2 Adjust the logger name (`structlog.get_logger("a2kit._plugin")`).
- [ ] 2.3 Verify imports — `_plugin.py` MUST have zero a2kit-domain imports (only stdlib + structlog).
- [ ] 2.4 Add `__all__ = ("PluginManifest", "Unavailable", "load_surface", "load_surface_sorted")`.

## 3. Pilot migration: auth providers

- [ ] 3.1 Create `src/a2kit/packages/auth/_providers/__init__.py` (empty package marker).
- [ ] 3.2 Create `src/a2kit/packages/auth/_providers/api_key.py` defining a factory `_factory(settings) -> APIKeyAuth | Unavailable` and `MANIFEST = PluginManifest(name="api_key", protocol=APIKeyAuth, factory=_factory)`.
- [ ] 3.3 Wire `App.auth(...)` (or its registration site) to also accept manifest discovery: at app boot, `load_surface("a2kit.packages.auth._providers", APIKeyAuth, settings)` populates a registry; `App.auth(instance)` continues to work for imperative registration.
- [ ] 3.4 Verify the existing auth capability tests pass unchanged.

## 4. Architecture rules

- [ ] 4.1 Add a pytest-archon rule `test_manifest_modules_only_declare_manifest` — any module under a discovered manifest surface MUST NOT do top-level work beyond defining the protocol impl + `MANIFEST`. (Depends on `adopt-arch-fitness-functions` landing; if not yet landed, ship the rule as a `tests/` integration test.)

## 5. Docs

- [ ] 5.1 New `docs/patterns/plugin-manifest.md` — one-page reference: when to use, the `Unavailable` discipline, side-effect-free import invariant.
- [ ] 5.2 Add a one-paragraph entry in `CHANGELOG.md` under `[Unreleased]`.
- [ ] 5.3 BACKLOG: collapse "Registry-driven `expose=` validation" and "`A2K-SURFACE-REGISTRY` lint rule" into a single follow-up — both want the manifest shape to bind against.

## 6. Verification

- [ ] 6.1 `make test` green.
- [ ] 6.2 `App.auth(APIKeyAuth(...))` still works for consumers that already use it.
- [ ] 6.3 An auth provider whose factory returns `Unavailable("no key")` is silently absent from the registry; the boot log carries the reason.
- [ ] 6.4 No package outside `packages/_plugin.py` imports the raw `PluginManifest` symbol from a domain layer (Tach, when present, or an archon rule).
