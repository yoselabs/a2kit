"""Mirror tests for `a2kit._docstring` — see test_param_docstring_pull.py
for the full extractor + end-to-end coverage."""

from __future__ import annotations

from a2kit._docstring import extract_param_descriptions


def test_smoke() -> None:
    assert extract_param_descriptions("Args:\n    x: y.") == {"x": "y."}
    assert extract_param_descriptions(None) == {}
