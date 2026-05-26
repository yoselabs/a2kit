"""Unit tests for the plugin manifest framework module."""

from __future__ import annotations

from a2kit.packages._plugin import PluginManifest, Unavailable


def test_unavailable_is_a_namedtuple_with_reason() -> None:
    u = Unavailable(reason="x")
    assert u.reason == "x"
    assert u == ("x",)


def test_plugin_manifest_has_documented_defaults() -> None:
    class _P:
        pass

    m = PluginManifest(name="n", protocol=_P, factory=lambda _c: _P())
    assert m.requires == ()
    assert m.settings_prefix is None
    assert m.priority == 0


def test_plugin_manifest_module_all_is_documented_surface() -> None:
    from a2kit.packages import _plugin as mod

    assert mod.__all__ == ("PluginManifest", "Unavailable", "load_surface", "load_surface_sorted")
