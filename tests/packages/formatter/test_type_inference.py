"""Type-driven format hint inference.

The router decides ``"tsv" | "json" | "page-tsv"`` purely from the tool's
return-type annotation, computed once at app build. JSON is the safe fallback
for any input the inference can't positively prove tabular.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, Field

from a2kit.packages.formatter.inference import (
    _is_dump_scalar,
    _model_is_scalar_only,
    infer_format_hint,
)
from a2kit.packages.formatter.response import Page


class Status(StrEnum):
    OPEN = "open"
    DONE = "done"


class FlatTask(BaseModel):
    id: str
    title: str
    status: Status
    created: datetime
    story_points: int


class TaskWithList(BaseModel):
    id: str
    labels: list[str]


class Reporter(BaseModel):
    name: str
    email: str


class TaskWithNested(BaseModel):
    id: str
    reporter: Reporter


class SearchPage(Page[FlatTask]):
    total: int = 0


class TestIsDumpScalar:
    def test_str_int_float_bool_none_are_scalar(self):
        assert _is_dump_scalar(str)
        assert _is_dump_scalar(int)
        assert _is_dump_scalar(float)
        assert _is_dump_scalar(bool)
        assert _is_dump_scalar(type(None))

    def test_datetime_family_is_scalar(self):
        assert _is_dump_scalar(datetime)
        assert _is_dump_scalar(date)
        assert _is_dump_scalar(time)

    def test_uuid_decimal_bytes_are_scalar(self):
        assert _is_dump_scalar(UUID)
        assert _is_dump_scalar(Decimal)
        assert _is_dump_scalar(bytes)

    def test_optional_scalar_is_scalar(self):
        assert _is_dump_scalar(str | None)
        assert _is_dump_scalar(str | None)

    def test_annotated_scalar_is_scalar(self):
        assert _is_dump_scalar(Annotated[int, Field(ge=0)])

    def test_enum_subclass_is_scalar(self):
        assert _is_dump_scalar(Status)

    def test_list_dict_are_not_scalar(self):
        assert not _is_dump_scalar(list[str])
        assert not _is_dump_scalar(dict[str, str])
        assert not _is_dump_scalar(tuple[str, ...])

    def test_basemodel_is_not_scalar(self):
        assert not _is_dump_scalar(FlatTask)

    def test_optional_non_scalar_is_not_scalar(self):
        assert not _is_dump_scalar(list[str] | None)


class TestModelIsScalarOnly:
    def test_flat_task_is_scalar_only(self):
        assert _model_is_scalar_only(FlatTask)

    def test_task_with_list_field_is_not_scalar_only(self):
        assert not _model_is_scalar_only(TaskWithList)

    def test_task_with_nested_model_is_not_scalar_only(self):
        assert not _model_is_scalar_only(TaskWithNested)


class TestInferFormatHint:
    # list[T] cases
    def test_list_of_scalar_only_model_is_tsv(self):
        assert infer_format_hint(list[FlatTask]) == "tsv"

    def test_list_of_model_with_list_field_is_json(self):
        assert infer_format_hint(list[TaskWithList]) == "json"

    def test_list_of_model_with_nested_model_is_json(self):
        assert infer_format_hint(list[TaskWithNested]) == "json"

    def test_list_of_scalar_is_json(self):
        assert infer_format_hint(list[str]) == "json"

    def test_list_of_dict_is_json(self):
        assert infer_format_hint(list[dict]) == "json"

    # tuple[T] follows list rules
    def test_tuple_of_scalar_only_model_is_tsv(self):
        assert infer_format_hint(tuple[FlatTask, ...]) == "tsv"

    # Single BaseModel
    def test_single_basemodel_is_json(self):
        assert infer_format_hint(FlatTask) == "json"

    # Page[T] cases
    def test_page_of_scalar_only_model_is_page_tsv(self):
        assert infer_format_hint(Page[FlatTask]) == "page-tsv"

    def test_page_of_model_with_list_field_is_json(self):
        assert infer_format_hint(Page[TaskWithList]) == "json"

    def test_subclass_of_page_with_scalar_only_model_is_page_tsv(self):
        assert infer_format_hint(SearchPage) == "page-tsv"

    def test_bare_page_without_parameter_is_json(self):
        assert infer_format_hint(Page) == "json"

    # Other shapes
    def test_dict_is_json(self):
        assert infer_format_hint(dict[str, int]) == "json"

    def test_any_is_json(self):
        assert infer_format_hint(Any) == "json"

    def test_none_is_json(self):
        assert infer_format_hint(None) == "json"

    def test_scalar_is_json(self):
        assert infer_format_hint(str) == "json"
        assert infer_format_hint(int) == "json"

    def test_union_of_incompatible_shapes_is_json(self):
        assert infer_format_hint(list[FlatTask] | FlatTask) == "json"

    def test_optional_top_level_is_json(self):
        # Optional at the top — even list[FlatTask] | None — is JSON
        # because the result might be None and the encoder dispatches per
        # call site.
        assert infer_format_hint(list[FlatTask] | None) == "json"
