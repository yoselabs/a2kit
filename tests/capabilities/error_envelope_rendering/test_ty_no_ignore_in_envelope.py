"""Capability: ``packages/dispatch/envelope.py`` is free of
``ty: ignore[unresolved-attribute]`` after the side-channel migration.
"""

from __future__ import annotations

from pathlib import Path

_ENVELOPE = Path(__file__).resolve().parents[3] / "src" / "a2kit" / "packages" / "dispatch" / "envelope.py"


def test_no_unresolved_attribute_ignores_in_envelope_module() -> None:
    source = _ENVELOPE.read_text()
    assert "ty: ignore[unresolved-attribute]" not in source, (
        f"{_ENVELOPE.relative_to(_ENVELOPE.parents[5])}: side-channel migration must remove "
        "all `# ty: ignore[unresolved-attribute]` comments."
    )
