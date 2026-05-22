"""BDD specs — value-driven rendering of the ``execute`` output.

The ``execute`` tool's return value has no static type, so it is rendered
for the ``llm`` consumer by sampling the head of the value: a uniform flat
list → TSV, anything else → JSON, with a JSON fallback when TSV encoding
raises.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from a2kit.packages.formatter import render_execute


class TestValueDrivenInference:
    """Requirement: The execute output is rendered by value-driven inference."""

    def test_flat_list_of_records_is_tsv(self):
        # WHEN sandboxed code returns a list of uniform flat dicts
        out = render_execute([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
        # THEN the execute output is rendered as TSV
        assert out.format == "tsv"
        assert out.text.splitlines()[0] == "id\tname"
        assert out.text.splitlines()[1] == "1\ta"

    def test_nested_result_is_json(self):
        # WHEN sandboxed code returns a nested structure
        out = render_execute({"query": "q", "hits": [{"score": 1}]})
        # THEN the execute output is rendered as JSON
        assert out.format == "json"
        assert json.loads(out.text) == {"query": "q", "hits": [{"score": 1}]}

    def test_list_of_nested_records_is_json(self):
        # head record has a list-valued field — not flat → JSON
        out = render_execute([{"id": 1, "tags": ["x"]}, {"id": 2, "tags": []}])
        assert out.format == "json"

    def test_tsv_encoding_failure_falls_back_to_json(self):
        # the head is a flat dict, but a later item is a bare string —
        # TSV encoding raises, so the renderer falls back to JSON
        out = render_execute([{"id": 1}, "not a record"])
        assert out.format == "json"
        assert json.loads(out.text) == [{"id": 1}, "not a record"]

    def test_scalar_is_json(self):
        assert render_execute("hello").format == "json"
        assert render_execute(7).format == "json"

    def test_empty_list_is_json(self):
        assert render_execute([]).format == "json"

    def test_dataclass_mirror_output_is_tsv(self):
        # the sandbox returns dataclass mirror instances — asdict → flat
        # dicts → TSV
        @dataclass
        class Row:
            id: int
            name: str

        out = render_execute([Row(1, "a"), Row(2, "b")])
        assert out.format == "tsv"
        assert out.text.splitlines()[0] == "id\tname"

    def test_structured_channel_is_plain(self):
        out = render_execute([{"id": 1, "name": "a"}])
        # content is TSV, structured is the equivalent JSON-able list
        assert out.format == "tsv"
        assert out.structured == [{"id": 1, "name": "a"}]
