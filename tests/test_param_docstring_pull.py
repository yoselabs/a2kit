"""Tests — Google-style docstring → param description (round-5 gap 4).

The verb decorators augment `fn.__annotations__` at decoration time:
a parameter that has a docstring entry but no explicit
`Annotated[T, Param(description=...)]` gets one synthesised. Explicit
`Param`/`Field` descriptions always win; Numpy/Sphinx formats are
explicit non-goals.
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from pydantic import Field

import a2kit
from a2kit._docstring import extract_param_descriptions
from a2kit.params import Param, description_of


def test_extract_basic_args_section() -> None:
    doc = """One-line summary.

    Args:
        url: Absolute http(s) URL to fetch.
        timeout: Seconds to wait. Default 30.

    Returns:
        Fetched body.
    """
    out = extract_param_descriptions(doc)
    assert out == {
        "url": "Absolute http(s) URL to fetch.",
        "timeout": "Seconds to wait. Default 30.",
    }


def test_extract_handles_type_annotation_in_parens() -> None:
    doc = """Summary.

    Args:
        url (str): The URL.
        count (int): The count.
    """
    out = extract_param_descriptions(doc)
    assert out == {"url": "The URL.", "count": "The count."}


def test_extract_joins_continuation_lines() -> None:
    doc = """Summary.

    Args:
        url: The URL.
            Continues on next line.
        timeout: Timeout.
    """
    out = extract_param_descriptions(doc)
    assert out["url"] == "The URL. Continues on next line."
    assert out["timeout"] == "Timeout."


def test_extract_recognises_parameters_and_arguments_headers() -> None:
    for header in ("Arguments", "Parameters", "arguments", "PARAMETERS"):
        doc = f"summary\n\n{header}:\n    x: Description here."
        out = extract_param_descriptions(doc)
        assert out == {"x": "Description here."}


def test_extract_returns_empty_for_numpy_style() -> None:
    """Explicit non-goal: numpy-style docstrings are not supported."""
    doc = """Summary.

    Parameters
    ----------
    url : str
        The URL.
    """
    # The numpy header is not "Parameters:" (with colon), so this should
    # return empty.
    out = extract_param_descriptions(doc)
    assert out == {}


def test_extract_stops_on_returns_section() -> None:
    doc = """Summary.

    Args:
        url: The URL.

    Returns:
        url: This is the returned URL, not a param.
    """
    out = extract_param_descriptions(doc)
    assert out == {"url": "The URL."}


def test_extract_returns_empty_for_none_or_empty_doc() -> None:
    assert extract_param_descriptions(None) == {}
    assert extract_param_descriptions("") == {}
    assert extract_param_descriptions("just a summary") == {}


# --- End-to-end: descriptions land on the tool's annotations --- #


class _R(a2kit.Router):
    @a2kit.read()
    async def fetch(
        self,
        url: str,
        timeout: int = 30,
    ) -> dict[str, int]:
        """Fetch a URL.

        Args:
            url: Absolute http(s) URL to fetch.
            timeout: Seconds to wait. Default 30.

        Returns:
            Status code dict.
        """
        return {"status": 200, "_timeout": timeout, "_url_len": len(url)}


def _resolved_hints(method: object) -> dict:
    from typing import get_type_hints

    fn = method.__func__ if hasattr(method, "__func__") else method  # type: ignore[union-attr]
    return get_type_hints(fn, include_extras=True)


def test_decoration_injects_descriptions_into_annotations() -> None:
    ann = _resolved_hints(_R.fetch)
    assert description_of(ann["url"]) == "Absolute http(s) URL to fetch."
    assert description_of(ann["timeout"]) == "Seconds to wait. Default 30."


# --- Explicit Param/Field wins --- #


class _ExplicitWinsRouter(a2kit.Router):
    @a2kit.read()
    async def fetch_explicit(
        self,
        url: Annotated[str, Param(description="EXPLICIT param wins")],
        body: Annotated[str, Field(description="EXPLICIT field wins")],
    ) -> dict[str, str]:
        """Fetch.

        Args:
            url: Docstring should NOT override Param.
            body: Docstring should NOT override Field.
        """
        return {"url": url, "body": body}


def test_explicit_param_wins_over_docstring() -> None:
    ann = _resolved_hints(_ExplicitWinsRouter.fetch_explicit)
    assert description_of(ann["url"]) == "EXPLICIT param wins"
    assert description_of(ann["body"]) == "EXPLICIT field wins"


# --- Tool runs end-to-end through TestClient --- #


def test_tool_invokes_normally_after_augmentation() -> None:
    from a2kit.testing import client

    app = a2kit.App("t").add_router(_R())

    async def go() -> None:
        async with client(app) as c:
            result = await c.invoke("fetch", url="https://x.test/", timeout=5)
            assert result == {"status": 200, "_timeout": 5, "_url_len": len("https://x.test/")}

    asyncio.run(go())


# --- Skip-conditions --- #


class _NoDocRouter(a2kit.Router):
    @a2kit.read()
    async def no_docstring(self, x: int) -> int:
        return x * 2


def test_no_doc_means_no_injection() -> None:
    ann = _resolved_hints(_NoDocRouter.no_docstring)
    # `x` annotation should be unchanged — bare `int`, no Annotated wrapper.
    assert ann["x"] is int
    assert description_of(ann["x"]) is None
