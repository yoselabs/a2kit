"""BDD specs for the consumer-aware rendering seam.

Covers OpenSpec change ``consumer-aware-format-routing`` →
``consumer-aware-rendering``: ``render(value, consumer)`` across the
``llm`` / ``code`` / ``machine`` profiles, ``build_encoding_plan`` for
nested flat-array fields, and single-pass encoding straight from typed
objects.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from a2kit.packages.formatter import Page
from a2kit.packages.formatter.inference import EncodingPlan, build_encoding_plan
from a2kit.packages.formatter.render import render, render_plain


class Task(BaseModel):
    id: int
    title: str


class Hit(BaseModel):
    score: float
    label: str


class Result(BaseModel):
    query: str
    rows: list[Hit]


class Nested(BaseModel):
    name: str
    inner: Task


class TestRenderConsumerProfiles:
    """Requirement: Tool results render per a consumer profile."""

    def test_llm_consumer_compresses_a_tabular_result(self):
        # GIVEN a tool whose result is a list of scalar-only records
        rows = [Task(id=1, title="a"), Task(id=2, title="b")]
        # WHEN rendered for the llm consumer with a tabular plan
        r = render(rows, "llm", plan=EncodingPlan("tsv"))
        # THEN the wire form is TSV
        assert r.format == "tsv"
        assert r.text.splitlines()[0] == "id\ttitle"
        assert r.text.splitlines()[1] == "1\ta"

    def test_llm_consumer_page_is_page_tsv(self):
        page = Page[Task](items=[Task(id=1, title="a")], next_cursor="c1")
        r = render(page, "llm", plan=EncodingPlan("page-tsv"))
        assert r.format == "json"
        envelope = json.loads(r.text)
        assert envelope["_items_format"] == "tsv"
        assert envelope["next_cursor"] == "c1"

    def test_code_consumer_keeps_structure(self):
        # WHEN the same result is rendered for the code consumer
        rows = [Task(id=1, title="a"), Task(id=2, title="b")]
        r = render(rows, "code", plan=EncodingPlan("tsv"))
        # THEN it is delivered as structured values, not an encoded string
        assert r.structured == [
            {"id": 1, "title": "a"},
            {"id": 2, "title": "b"},
        ]
        assert r.format == "json"

    def test_machine_consumer_is_json(self):
        # WHEN rendered for the machine consumer
        rows = [Task(id=1, title="a")]
        r = render(rows, "machine", plan=EncodingPlan("tsv"))
        # THEN the wire form is plain JSON, never TSV
        assert r.format == "json"
        assert json.loads(r.text) == [{"id": 1, "title": "a"}]


class TestRenderStructuredChannel:
    """The structured payload is always the JSON-able plain structure."""

    def test_llm_tabular_carries_equivalent_structured(self):
        rows = [Task(id=1, title="a")]
        r = render(rows, "llm", plan=EncodingPlan("tsv"))
        # content is TSV, structured is the equivalent JSON object
        assert r.format == "tsv"
        assert r.structured == [{"id": 1, "title": "a"}]


class TestBuildEncodingPlan:
    """Requirement: The encoding plan covers nested flat-array fields."""

    def test_nested_flat_array_field_is_marked_tsv(self):
        # GIVEN Result(query: str, rows: list[Hit]) where Hit is scalar-only
        plan = build_encoding_plan(Result)
        # THEN the plan marks rows as TSV-encoded and the envelope JSON
        assert plan.kind == "envelope"
        assert plan.tsv_fields == ("rows",)

    def test_top_level_page_is_the_depth_1_case(self):
        plan = build_encoding_plan(Page[Task])
        assert plan.kind == "page-tsv"

    def test_top_level_flat_list_is_tsv(self):
        plan = build_encoding_plan(list[Task])
        assert plan.kind == "tsv"

    def test_deeply_nested_non_tabular_structure_stays_json(self):
        # Nested has no scalar-only-model array anywhere
        plan = build_encoding_plan(Nested)
        assert plan.kind == "json"

    def test_single_record_stays_json(self):
        plan = build_encoding_plan(Task)
        assert plan.kind == "json"


class TestEnvelopeEncoding:
    """An envelope plan embeds TSV for the flat-array fields."""

    def test_envelope_embeds_tsv_for_flat_array_field(self):
        result = Result(
            query="q",
            rows=[Hit(score=0.9, label="x"), Hit(score=0.5, label="y")],
        )
        plan = build_encoding_plan(Result)
        r = render(result, "llm", plan=plan)
        assert r.format == "json"
        envelope = json.loads(r.text)
        # the envelope stays JSON; query is a plain field
        assert envelope["query"] == "q"
        # rows is an embedded TSV string with a discriminator
        assert envelope["_rows_format"] == "tsv"
        assert envelope["rows"].splitlines()[0] == "score\tlabel"
        # the structured channel keeps rows as a real list
        assert r.structured["rows"] == [
            {"score": 0.9, "label": "x"},
            {"score": 0.5, "label": "y"},
        ]


class TestSinglePassEncoding:
    """Requirement 2.5: encode straight from typed objects, no double walk."""

    def test_json_render_encodes_basemodel_without_prenormalize(self):
        r = render(Task(id=7, title="z"), "llm", plan=EncodingPlan("json"))
        assert json.loads(r.text) == {"id": 7, "title": "z"}

    def test_json_render_handles_nested_basemodels(self):
        value = Nested(name="n", inner=Task(id=1, title="a"))
        r = render(value, "machine")
        assert json.loads(r.text) == {
            "name": "n",
            "inner": {"id": 1, "title": "a"},
        }

    def test_list_of_basemodels_json_render(self):
        r = render([Task(id=1, title="a"), Task(id=2, title="b")], "llm", plan=EncodingPlan("json"))
        assert json.loads(r.text) == [
            {"id": 1, "title": "a"},
            {"id": 2, "title": "b"},
        ]


class TestRenderEdgeCases:
    """Plan/value mismatches and the render_plain helper."""

    def test_page_tsv_plan_on_non_page_falls_back_to_json(self):
        # plan says page-tsv but the value is not a Page
        r = render([Task(id=1, title="a")], "llm", plan=EncodingPlan("page-tsv"))
        assert r.format == "json"
        assert json.loads(r.text) == [{"id": 1, "title": "a"}]

    def test_render_without_plan_defaults_to_json(self):
        r = render({"a": 1}, "llm")
        assert r.format == "json"

    def test_render_repr_is_concise(self):
        r = render([Task(id=1, title="a")], "llm", plan=EncodingPlan("tsv"))
        assert "Rendered(" in repr(r)

    def test_render_plain_tsv_from_dict_rows(self):
        text = render_plain([{"id": 1, "name": "a"}], EncodingPlan("tsv"))
        assert text.splitlines()[0] == "id\tname"

    def test_render_plain_page_tsv_from_dict(self):
        text = render_plain({"items": [{"id": 1}], "next_cursor": None}, EncodingPlan("page-tsv"))
        assert '"_items_format":"tsv"' in text

    def test_render_plain_json_falls_through(self):
        text = render_plain({"a": 1}, EncodingPlan("json"))
        assert json.loads(text) == {"a": 1}
