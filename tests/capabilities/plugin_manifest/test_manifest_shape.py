"""Capability: a module exporting ``MANIFEST = PluginManifest(...)`` is
discoverable by :func:`load_surface`. Per ``adopt-plugin-manifests``.
"""

from __future__ import annotations

from typing import Protocol

from a2kit.packages._plugin import PluginManifest, load_surface


class _P(Protocol):
    def kind(self) -> str: ...


class _Foo:
    def kind(self) -> str:
        return "foo"


def test_manifest_round_trip_via_load_surface(tmp_path, monkeypatch) -> None:
    pkg_dir = tmp_path / "pluginpkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "foo_plugin.py").write_text(
        "from a2kit.packages._plugin import PluginManifest\n"
        "class Foo:\n"
        "    def kind(self) -> str:\n"
        "        return 'foo'\n"
        "\n"
        "_FACTORY_FOO = Foo\n"
        "def _factory(_ctx):\n"
        "    return _FACTORY_FOO()\n"
        "MANIFEST = PluginManifest(name='foo', protocol=Foo, factory=_factory)\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    registry = load_surface("pluginpkg", __import__("pluginpkg.foo_plugin", fromlist=["Foo"]).Foo, context=None)
    assert "foo" in registry
    assert registry["foo"].kind() == "foo"


def test_manifest_fields_are_frozen() -> None:
    m = PluginManifest(name="x", protocol=_P, factory=lambda _c: _Foo())
    import dataclasses

    assert dataclasses.is_dataclass(m)
    # frozen=True: assigning should raise
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        # frozen=True: assignment is rejected at runtime. setattr
        # exercises the same path without the static checker flagging
        # a read-only-property write.
        setattr(m, "name", "y")  # noqa: B010
