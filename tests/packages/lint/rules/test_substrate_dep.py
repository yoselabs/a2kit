"""Tests for `a2kit.packages.lint.rules.substrate_dep` (A2K-SUBSTRATE-DEP)."""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import A2K_SUBSTRATE_DEP, run_static_rules


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]


def test_marker_on_default_expose_tool_flagged(tmp_path: Path) -> None:
    body = (
        "from typing import Annotated\n"
        "from fastapi import Depends\n"
        "import a2kit\n"
        "from a2kit import Principal\n"
        "class _D: pass\n"
        "def _f(): return _D()\n"
        "class R(a2kit.Router):\n"
        "    slug = 'r'\n"
        "    @a2kit.read()\n"
        "    async def fetch(self, *, who: Annotated[Principal, Depends(_f)], id: str) -> dict:\n"
        "        return {'id': id}\n"
        "    tools = (fetch,)\n"
    )
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_SUBSTRATE_DEP in _codes(findings)


def test_marker_on_api_only_tool_passes(tmp_path: Path) -> None:
    body = (
        "from typing import Annotated\n"
        "from fastapi import Depends\n"
        "import a2kit\n"
        "from a2kit import Principal\n"
        "class _D: pass\n"
        "def _f(): return _D()\n"
        "class R(a2kit.Router):\n"
        "    slug = 'r'\n"
        "    @a2kit.read(surfaces=('api',))\n"
        "    async def fetch(self, *, who: Annotated[Principal, Depends(_f)], id: str) -> dict:\n"
        "        return {'id': id}\n"
        "    tools = (fetch,)\n"
    )
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_SUBSTRATE_DEP not in _codes(findings)


def test_non_marker_annotated_passes(tmp_path: Path) -> None:
    body = (
        "from typing import Annotated\n"
        "import a2kit\n"
        "class R(a2kit.Router):\n"
        "    slug = 'r'\n"
        "    @a2kit.read()\n"
        "    async def fetch(self, *, label: Annotated[str, 'help text']) -> dict:\n"
        "        return {'l': label}\n"
        "    tools = (fetch,)\n"
    )
    p = _write(tmp_path / "src" / "a2kit" / "user_app.py", body)
    findings = run_static_rules([p])
    assert A2K_SUBSTRATE_DEP not in _codes(findings)
