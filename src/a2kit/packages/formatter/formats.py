"""Wire-format vocabulary — the leaf type home shared by the formatter package."""

from __future__ import annotations

from typing import Literal

FormatHint = Literal["auto", "json", "tsv", "page-tsv"]
FormatName = Literal["json", "tsv"]

__all__ = ["FormatHint", "FormatName"]
