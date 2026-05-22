"""The component-map generator and its staleness gate.

Covers the `component-map` capability: `scripts/component_map.py`
projects the layer manifest + import graph into `docs/COMPONENT_MAP.md`,
and a pre-commit gate keeps the committed file current. See ADR 0007
(the analogous `adr-index` pattern).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from a2kit.packages.lint.layers import LAYER_MANIFEST

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GENERATOR = _REPO_ROOT / "scripts" / "component_map.py"
_MAP = _REPO_ROOT / "docs" / "COMPONENT_MAP.md"


def _load_generator() -> ModuleType:
    """Import `scripts/component_map.py` as a module without polluting sys.path."""
    spec = importlib.util.spec_from_file_location("component_map", _GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_imports_assignment_from_the_manifest() -> None:
    """The generator reads `layers.py`; it does not redefine the manifest."""
    source = _GENERATOR.read_text(encoding="utf-8")
    assert "from a2kit.packages.lint.layers import" in source
    assert "LAYER_MANIFEST: dict" not in source, "generator must not redefine the manifest"


def test_build_graph_covers_every_manifest_unit() -> None:
    """`build_graph()` returns file-count and deps keyed by every unit."""
    gen = _load_generator()
    file_count, deps = gen.build_graph()
    assert set(file_count) == set(LAYER_MANIFEST)
    assert set(deps) == set(LAYER_MANIFEST)
    # Every assigned unit owns at least one source file.
    for unit, count in file_count.items():
        assert count > 0, f"unit {unit!r} has no source files"


def test_rendered_map_lists_every_unit_with_layer_and_edges() -> None:
    """The rendered document carries every unit, its layer, and the DAG."""
    gen = _load_generator()
    rendered = gen.render(*gen.build_graph())
    assert "| Unit | Layer | Files | Fan-in | Fan-out | Depends on |" in rendered
    assert "## Layer-ordered DAG" in rendered
    for unit in LAYER_MANIFEST:
        assert f"`{unit}`" in rendered, f"unit {unit!r} missing from the component map"


def test_committed_map_is_not_stale() -> None:
    """The committed COMPONENT_MAP.md matches fresh generator output."""
    gen = _load_generator()
    fresh = gen.render(*gen.build_graph())
    assert _MAP.exists(), "docs/COMPONENT_MAP.md is missing — run `make component-map`"
    assert _MAP.read_text(encoding="utf-8") == fresh, "docs/COMPONENT_MAP.md is stale — run `make component-map` and commit it"
