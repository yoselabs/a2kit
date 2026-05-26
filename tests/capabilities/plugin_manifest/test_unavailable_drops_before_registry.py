"""Capability: a factory returning ``Unavailable`` does NOT appear in the
returned dict; an INFO log line records the drop.
"""

from __future__ import annotations

import logging

import pytest

from a2kit.packages._plugin import load_surface


def test_unavailable_plugin_is_absent_and_logged(tmp_path, monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    pkg_dir = tmp_path / "unavailpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "missing_key.py").write_text(
        "from a2kit.packages._plugin import PluginManifest, Unavailable\n"
        "class P:\n"
        "    pass\n"
        "def _factory(_ctx):\n"
        "    return Unavailable('ANTHROPIC_API_KEY missing')\n"
        "MANIFEST = PluginManifest(name='anthropic', protocol=P, factory=_factory)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    proto = __import__("unavailpkg.missing_key", fromlist=["P"]).P
    caplog.set_level(logging.INFO, logger="a2kit._plugin")
    registry = load_surface("unavailpkg", proto, context=None)
    assert "anthropic" not in registry
    assert registry == {}
    drops = [r for r in caplog.records if "plugin_unavailable" in r.getMessage()]
    assert drops, "expected at least one INFO log line recording the drop"
    assert "ANTHROPIC_API_KEY missing" in drops[0].getMessage()
