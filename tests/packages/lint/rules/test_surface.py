"""Mirror tests for ``a2kit.packages.lint.rules.surface``."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.surface import rule_surface_explicit


def _findings(source: str) -> list[str]:
    tree = ast.parse(source)
    return [m.message for m in rule_surface_explicit(tree, "f.py", source)]


def test_login_without_visibility_fires() -> None:
    src = """
import a2kit
@a2kit.read()
async def login() -> dict:
    return {}
"""
    out = _findings(src)
    assert len(out) == 1
    assert "'login'" in out[0]
    assert 'visibility="cli"' in out[0]


def test_login_with_explicit_visibility_does_not_fire() -> None:
    src = """
import a2kit
@a2kit.read(visibility="cli")
async def login() -> dict:
    return {}
"""
    assert _findings(src) == []


def test_explicit_visibility_all_suppresses() -> None:
    src = """
import a2kit
@a2kit.read(visibility="all")
async def login() -> dict:
    return {}
"""
    assert _findings(src) == []


def test_non_credential_name_does_not_fire() -> None:
    src = """
import a2kit
@a2kit.read()
async def list_projects() -> dict:
    return {}
"""
    assert _findings(src) == []


def test_logout_signin_signout_fires() -> None:
    src = """
import a2kit
@a2kit.read()
async def logout() -> dict: return {}
@a2kit.read()
async def signin() -> dict: return {}
@a2kit.read()
async def signout() -> dict: return {}
"""
    assert len(_findings(src)) == 3


def test_write_and_tool_verbs_also_covered() -> None:
    src = """
import a2kit
@a2kit.write()
async def rotate_key() -> dict: return {}
@a2kit.write()
async def issue_token() -> dict: return {}
"""
    assert len(_findings(src)) == 2


def test_authenticate_substring_match() -> None:
    src = """
import a2kit
@a2kit.read()
async def authenticate_user() -> dict: return {}
"""
    assert len(_findings(src)) == 1
