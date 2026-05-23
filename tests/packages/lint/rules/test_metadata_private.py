"""Tests for `a2kit.packages.lint.rules.metadata_private` (A2K-METADATA-PRIVATE)."""

from __future__ import annotations

from pathlib import Path

from a2kit.packages.lint.static import A2K_METADATA_PRIVATE, run_static_rules


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _codes(findings: object) -> set[str]:
    return {f.rule for f in findings}  # type: ignore[union-attr]  # ty: ignore[not-iterable]


def test_packages_module_importing_private_meta_helper_is_flagged(tmp_path: Path) -> None:
    body = "from a2kit.metadata import _get_meta\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "cli" / "userland.py", body)
    findings = run_static_rules([p])
    assert A2K_METADATA_PRIVATE in _codes(findings)


def test_set_meta_outside_allowlist_is_flagged(tmp_path: Path) -> None:
    body = "from a2kit.metadata import _set_meta\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "mcp" / "rogue.py", body)
    findings = run_static_rules([p])
    assert A2K_METADATA_PRIVATE in _codes(findings)


def test_allowlisted_module_is_not_flagged(tmp_path: Path) -> None:
    # The rule resolves the file's module from its path; the allowlist
    # includes `a2kit.app`, so this import must not trigger.
    body = "from a2kit.metadata import _get_meta\n"
    p = _write(tmp_path / "src" / "a2kit" / "app.py", body)
    findings = run_static_rules([p])
    assert A2K_METADATA_PRIVATE not in _codes(findings)


def test_public_metadata_import_is_not_flagged(tmp_path: Path) -> None:
    # Importing the meta types is fine — only the private accessors are gated.
    body = "from a2kit.metadata import A2KitMeta\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "cli" / "ok.py", body)
    findings = run_static_rules([p])
    assert A2K_METADATA_PRIVATE not in _codes(findings)


def test_noqa_suppresses_finding(tmp_path: Path) -> None:
    body = "from a2kit.metadata import _get_meta  # noqa: A2K-METADATA-PRIVATE\n"
    p = _write(tmp_path / "src" / "a2kit" / "packages" / "cli" / "exempt.py", body)
    findings = run_static_rules([p])
    assert A2K_METADATA_PRIVATE not in _codes(findings)
