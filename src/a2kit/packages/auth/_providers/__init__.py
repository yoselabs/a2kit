"""Manifest-discoverable auth providers.

Every module under this package SHALL declare exactly one
``MANIFEST = PluginManifest(...)`` constant alongside its factory and
protocol implementation. ``load_surface("a2kit.packages.auth._providers",
APIKeyAuth, context)`` walks this package and returns
``{name: instance}`` of the ready-to-use providers; unavailable ones
(missing keys, missing creds) are dropped before reaching the caller.

See ``docs/patterns/plugin-manifest.md`` and ADR 0001 (a2web).
"""
