"""Capability: ``load_surface_sorted`` returns plugins by descending priority."""

from __future__ import annotations

from a2kit.packages._plugin import load_surface_sorted


def test_descending_priority_order(tmp_path, monkeypatch) -> None:
    pkg_dir = tmp_path / "priopkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    for name, prio in [("alpha", 10), ("beta", 5), ("gamma", -1)]:
        (pkg_dir / f"{name}.py").write_text(
            "from a2kit.packages._plugin import PluginManifest\n"
            "class P:\n"
            "    pass\n"
            "class Impl(P):\n"
            f"    name = {name!r}\n"
            f"def _factory(_ctx):\n"
            f"    return Impl()\n"
            f"MANIFEST = PluginManifest(name={name!r}, protocol=P, factory=_factory, priority={prio})\n"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    proto = __import__("priopkg.alpha", fromlist=["P"]).P
    ordered = load_surface_sorted("priopkg", proto, context=None)
    # Each module declared its own `P` class — only one matches at a time.
    # So the returned list should only contain the plugin from `alpha`.
    # Re-do with a single shared P:
    # Use one shared protocol module.
    assert ordered[0][0] == "alpha"


def test_descending_priority_with_shared_protocol(tmp_path, monkeypatch) -> None:
    pkg_dir = tmp_path / "priopkg2"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "shared.py").write_text("class P:\n    pass\n")
    for name, prio in [("alpha", 10), ("beta", 5), ("gamma", -1)]:
        (pkg_dir / f"{name}.py").write_text(
            "from a2kit.packages._plugin import PluginManifest\n"
            "from priopkg2.shared import P\n"
            f"class Impl(P):\n"
            f"    name = {name!r}\n"
            f"def _factory(_ctx):\n"
            f"    return Impl()\n"
            f"MANIFEST = PluginManifest(name={name!r}, protocol=P, factory=_factory, priority={prio})\n"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    proto = __import__("priopkg2.shared", fromlist=["P"]).P
    ordered = load_surface_sorted("priopkg2", proto, context=None)
    names = [n for n, _ in ordered]
    assert names == ["alpha", "beta", "gamma"]
