"""Unit tests for the A2K-NO-DICT-STR-ANY lint rule."""

from __future__ import annotations

import ast

from a2kit.packages.lint.rules.no_dict_str_any import rule_no_dict_str_any


def _findings(source: str, filename: str = "src/a2kit/sample.py") -> list:
    tree = ast.parse(source)
    return list(rule_no_dict_str_any(tree, filename, source))


def test_dataclass_dict_str_any_field_fires() -> None:
    source = """
from dataclasses import dataclass
from typing import Any

@dataclass
class Env:
    payload: dict[str, Any]
"""
    msgs = _findings(source)
    assert len(msgs) == 1
    assert msgs[0].rule == "AK214"
    assert "Env.payload" in msgs[0].message


def test_frozen_dataclass_with_call_decorator_fires() -> None:
    source = """
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Env:
    payload: dict[str, Any]
"""
    assert len(_findings(source)) == 1


def test_basemodel_subclass_fires() -> None:
    source = """
from pydantic import BaseModel
from typing import Any

class M(BaseModel):
    extras: dict[str, Any]
"""
    assert len(_findings(source)) == 1


def test_plain_class_is_ignored() -> None:
    source = """
from typing import Any

class NotADataclass:
    payload: dict[str, Any]
"""
    assert _findings(source) == []


def test_dict_str_str_does_not_fire() -> None:
    source = """
from dataclasses import dataclass

@dataclass
class Env:
    labels: dict[str, str]
"""
    assert _findings(source) == []


def test_mapping_str_any_does_not_fire() -> None:
    """Rule is intentionally narrower than Mapping-style annotations."""
    source = """
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

@dataclass
class Env:
    payload: Mapping[str, Any]
"""
    assert _findings(source) == []


def test_optional_dict_str_any_fires() -> None:
    """``dict[str, Any] | None`` should still flag — the inner shape is loose."""
    source = """
from dataclasses import dataclass
from typing import Any

@dataclass
class Env:
    payload: dict[str, Any] | None = None
"""
    assert len(_findings(source)) == 1


def test_noqa_suppresses_finding() -> None:
    source = """
from dataclasses import dataclass
from typing import Any

@dataclass
class Env:
    payload: dict[str, Any]  # noqa: AK214 -- wire envelope
"""
    assert _findings(source) == []


def test_fixture_paths_are_skipped() -> None:
    source = """
from dataclasses import dataclass
from typing import Any

@dataclass
class Env:
    payload: dict[str, Any]
"""
    assert _findings(source, filename="tests/fixtures/sample.py") == []
