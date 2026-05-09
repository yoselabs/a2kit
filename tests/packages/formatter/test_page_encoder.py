"""Hybrid page-tsv encoder: JSON envelope, embedded TSV string for items."""

from __future__ import annotations

import csv
import io
import json

from pydantic import BaseModel

from a2kit.packages.formatter.page import encode_page_tsv
from a2kit.packages.formatter.response import Page


class Task(BaseModel):
    id: str
    title: str


class TestEncodePageTsv:
    def test_basic_envelope(self):
        page = Page[Task](
            items=[Task(id="a", title="x"), Task(id="b", title="y")],
            next_cursor="c1",
        )
        out = encode_page_tsv(page)
        parsed = json.loads(out)
        assert parsed["next_cursor"] == "c1"
        assert parsed["_items_format"] == "tsv"
        # items is a TSV string
        items_str = parsed["items"]
        rows = list(csv.DictReader(io.StringIO(items_str), delimiter="\t"))
        assert rows == [{"id": "a", "title": "x"}, {"id": "b", "title": "y"}]

    def test_empty_items_emits_header_only(self):
        page = Page[Task](items=[], next_cursor=None)
        out = encode_page_tsv(page)
        parsed = json.loads(out)
        assert parsed["next_cursor"] is None
        assert parsed["_items_format"] == "tsv"
        # header line + trailing newline, no data rows
        assert parsed["items"] == "id\ttitle\n"

    def test_subclass_extra_fields_pass_through(self):
        class SearchPage(Page[Task]):
            total: int = 0

        page = SearchPage(items=[Task(id="a", title="x")], total=42)
        out = encode_page_tsv(page)
        parsed = json.loads(out)
        assert parsed["total"] == 42
        assert parsed["_items_format"] == "tsv"
        rows = list(csv.DictReader(io.StringIO(parsed["items"]), delimiter="\t"))
        assert rows == [{"id": "a", "title": "x"}]

    def test_top_level_is_compact_json(self):
        page = Page[Task](items=[Task(id="a", title="x")], next_cursor="c")
        out = encode_page_tsv(page)
        # Compact: no spaces between fields
        assert ", " not in out
        assert json.loads(out)  # valid JSON
