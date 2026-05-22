#!/usr/bin/env python3
"""Generate docs/COMPONENT_MAP.md from the layer manifest + the import graph.

The component map is the agent-loadable view of a2kit's internal
dependency DAG — the structural sibling of `docs/adr/INDEX.md`. It
renders every layer-manifest unit with its layer, file count,
dependency edges, and fan-in / fan-out, plus a layer-ordered DAG.

Run modes
---------
    uv run python scripts/component_map.py            # regenerate the map
    uv run python scripts/component_map.py --check    # nonzero if stale

The --check mode is wired into pre-commit so a committer cannot land an
import-graph change without regenerating the map in the same commit.

The generator is a pure projection: it imports the unit-and-layer
assignment from `a2kit.packages.lint.layers` (the single source of
truth) and reuses the lint's own import-graph parser
(`collect_layer_imports`). It maintains no second manifest.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from a2kit.packages.lint.layers import LAYER_MANIFEST, layer_of, unit_for_path
from a2kit.packages.lint.rules.importing import collect_layer_imports

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src" / "a2kit"
MAP_PATH = REPO_ROOT / "docs" / "COMPONENT_MAP.md"

_HEADER = """# Component Map

Auto-generated from the layer manifest (`src/a2kit/packages/lint/layers.py`)
and the parsed `src/a2kit/` import graph by `scripts/component_map.py`. Do
not edit by hand — regenerate with `make component-map` (the pre-commit
hook enforces freshness).

This is the agent-loadable view of a2kit's internal dependency DAG, the
structural sibling of `docs/adr/INDEX.md`. A unit may import only
strictly-lower layers; the `A2K-LAYER` lint rule enforces it. Edges to
the foundational leaf modules (`a2kit.exceptions`,
`a2kit._context_protocol`) are layer-exempt and omitted here, matching
the lint's own view of the graph.
"""


def build_graph() -> tuple[dict[str, int], dict[str, set[str]]]:
    """Parse `src/a2kit/` and return ``(file_count, deps)`` per unit.

    ``file_count`` maps each layer-manifest unit to the number of `.py`
    files assigned to it. ``deps`` maps each unit to the set of units it
    imports (cross-unit edges only — intra-unit and foundational edges
    are dropped by the shared `collect_layer_imports` parser).
    """
    file_count: dict[str, int] = dict.fromkeys(LAYER_MANIFEST, 0)
    deps: dict[str, set[str]] = {unit: set() for unit in LAYER_MANIFEST}

    for path in sorted(SRC_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        unit = unit_for_path(rel)
        if unit in file_count:
            file_count[unit] += 1
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        own, edges = collect_layer_imports(tree, rel, source)
        if own is None or own not in deps:
            continue
        for target_unit, _lineno, _suppressed in edges:
            if target_unit in deps:
                deps[own].add(target_unit)

    return file_count, deps


def render(file_count: dict[str, int], deps: dict[str, set[str]]) -> str:
    """Render the component-map markdown from the parsed graph."""
    fan_out = {unit: len(deps[unit]) for unit in LAYER_MANIFEST}
    fan_in = {unit: sum(unit in deps[other] for other in LAYER_MANIFEST) for unit in LAYER_MANIFEST}
    units = sorted(LAYER_MANIFEST, key=lambda u: (layer_of(u) or 0, u))

    lines: list[str] = [_HEADER.rstrip(), "", "## Units", ""]
    lines.append("| Unit | Layer | Files | Fan-in | Fan-out | Depends on |")
    lines.append("|------|-------|-------|--------|---------|------------|")
    for unit in units:
        dep_list = ", ".join(f"`{d}`" for d in sorted(deps[unit])) or "—"
        lines.append(f"| `{unit}` | {layer_of(unit)} | {file_count[unit]} | {fan_in[unit]} | {fan_out[unit]} | {dep_list} |")

    lines += ["", "## Layer-ordered DAG", ""]
    for layer in sorted(set(LAYER_MANIFEST.values())):
        lines.append(f"### Layer {layer}")
        lines.append("")
        for unit in sorted(u for u in LAYER_MANIFEST if layer_of(u) == layer):
            dep_list = ", ".join(f"`{d}`" for d in sorted(deps[unit])) or "no cross-unit dependencies"
            lines.append(f"- `{unit}` → {dep_list}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if the on-disk COMPONENT_MAP.md is stale.",
    )
    args = parser.parse_args()

    file_count, deps = build_graph()
    new_content = render(file_count, deps)

    if args.check:
        existing = MAP_PATH.read_text(encoding="utf-8") if MAP_PATH.exists() else ""
        if existing != new_content:
            sys.stderr.write("docs/COMPONENT_MAP.md is stale. Run `make component-map` and commit the result.\n")
            return 1
        return 0

    MAP_PATH.write_text(new_content, encoding="utf-8")
    sys.stdout.write(f"Wrote {MAP_PATH} ({len(LAYER_MANIFEST)} units).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
