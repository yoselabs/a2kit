"""Unit tests for the FieldInfo -> typer.Option Annotated rewriter."""

from __future__ import annotations

from typing import Annotated, get_args

import typer
from pydantic import Field

from a2kit.packages.cli._field_to_typer import field_to_typer_annotation


def _get_typer_option(annotation):
    args = get_args(annotation)
    for meta in args[1:]:
        if isinstance(meta, typer.models.OptionInfo):
            return meta
    return None


def test_field_with_description_rewrites_to_typer_option_help() -> None:
    ann = Annotated[int, Field(description="batch size")]
    rewritten = field_to_typer_annotation(ann)
    opt = _get_typer_option(rewritten)
    assert opt is not None
    assert opt.help == "batch size"


def test_field_without_description_wraps_in_bare_option() -> None:
    ann = Annotated[int, Field(ge=0)]
    rewritten = field_to_typer_annotation(ann)
    opt = _get_typer_option(rewritten)
    assert opt is not None
    assert opt.help is None
    assert get_args(rewritten)[0] is int


def test_unannotated_wraps_in_bare_option() -> None:
    rewritten = field_to_typer_annotation(int)
    opt = _get_typer_option(rewritten)
    assert opt is not None
    assert get_args(rewritten)[0] is int


def test_annotated_with_non_field_metadata_passes_through() -> None:
    ann = Annotated[int, "custom-marker"]
    rewritten = field_to_typer_annotation(ann)
    assert rewritten is ann


def test_str_annotation_with_description() -> None:
    ann = Annotated[str, Field(description="user id")]
    rewritten = field_to_typer_annotation(ann)
    opt = _get_typer_option(rewritten)
    assert opt is not None
    assert opt.help == "user id"
    assert get_args(rewritten)[0] is str
