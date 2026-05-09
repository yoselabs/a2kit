"""TSV encoder: stdlib csv with tab delimiter, declared field order."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from pydantic import BaseModel

from a2kit.packages.formatter.tsv import encode_tsv


class Task(BaseModel):
    id: str
    title: str
    status: str


class TaskWithDate(BaseModel):
    id: str
    created: datetime


class TestEncodeTsv:
    def test_header_in_declared_field_order(self):
        rows = [Task(id="a", title="x", status="open")]
        out = encode_tsv(rows, columns=list(Task.model_fields.keys()))
        assert out.splitlines()[0] == "id\ttitle\tstatus"

    def test_row_round_trips_through_stdlib_csv(self):
        rows = [Task(id="a", title="x", status="open"), Task(id="b", title="y", status="done")]
        out = encode_tsv(rows, columns=["id", "title", "status"])
        parsed = list(csv.DictReader(io.StringIO(out), delimiter="\t"))
        assert parsed == [
            {"id": "a", "title": "x", "status": "open"},
            {"id": "b", "title": "y", "status": "done"},
        ]

    def test_comma_in_cell_does_not_quote(self):
        rows = [Task(id="a", title="Fix Cyrillic, comma", status="open")]
        out = encode_tsv(rows, columns=["id", "title", "status"])
        # QUOTE_MINIMAL: only tab/newline/quote trigger quoting
        assert '"' not in out
        assert "Fix Cyrillic, comma" in out

    def test_tab_in_cell_triggers_quote(self):
        rows = [Task(id="a", title="has\ttab", status="open")]
        out = encode_tsv(rows, columns=["id", "title", "status"])
        assert '"has\ttab"' in out

    def test_datetime_renders_via_model_dump_iso(self):
        from datetime import UTC

        rows = [TaskWithDate(id="a", created=datetime(2026, 5, 9, 17, 0, 0, tzinfo=UTC))]
        out = encode_tsv(rows, columns=["id", "created"])
        # model_dump(mode="json") produces ISO string
        assert "2026-05-09T17:00:00" in out

    def test_lf_line_terminator(self):
        rows = [Task(id="a", title="x", status="open"), Task(id="b", title="y", status="open")]
        out = encode_tsv(rows, columns=["id", "title", "status"])
        # Three lines: header + 2 rows + trailing newline
        assert out.endswith("\n")
        assert "\r\n" not in out

    def test_empty_rows_emits_header_only(self):
        out = encode_tsv([], columns=["id", "title", "status"])
        assert out == "id\ttitle\tstatus\n"

    def test_extra_fields_are_ignored(self):
        # If columns omits a field, it doesn't appear.
        rows = [Task(id="a", title="x", status="open")]
        out = encode_tsv(rows, columns=["id", "title"])
        lines = out.splitlines()
        assert lines[0] == "id\ttitle"
        assert lines[1] == "a\tx"

    def test_list_value_is_json_blobbed(self):
        # Forced TSV on a non-uniform shape: list/dict cells are JSON-encoded
        # then CSV-quoted (embedded quotes get doubled per RFC 4180).
        class Wide(BaseModel):
            id: str
            labels: list[str]

        rows = [Wide(id="a", labels=["x", "y"])]
        out = encode_tsv(rows, columns=["id", "labels"])
        # csv.DictReader will re-parse the cell back to the JSON string
        parsed = list(csv.DictReader(io.StringIO(out), delimiter="\t"))
        assert parsed[0]["labels"] == '["x","y"]'
