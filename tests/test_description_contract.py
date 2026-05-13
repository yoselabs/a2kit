"""Section 5 of `a2web-feedback-round-2`: tool description contract.

Gherkin scenarios (mirroring `specs/tool-description-contract/spec.md`):

  Scenario: first non-empty line becomes short_help
    GIVEN a tool whose docstring's first line is "Fetch content from a URL."
    THEN the click subcommand's short_help is that line

  Scenario: full body forwarded to click --help body, markdown stripped
    GIVEN a multi-paragraph docstring with **bold** and [link](url)
    THEN the click subcommand's help has bold→bold, link→"text (url)"

  Scenario: pydantic.Field description forwarded to click option help
    GIVEN url: Annotated[str, pydantic.Field(description="Absolute URL.")]
    THEN the click option's help is "Absolute URL."

  Scenario: pydantic.Field description forwarded to schema
    GIVEN the same annotation
    THEN typing.get_type_hints(fn, include_extras=True) carries a FieldInfo
         with description set
"""

from __future__ import annotations

from typing import Annotated

import pydantic
from click.testing import CliRunner

import a2kit
from a2kit.packages.cli.builder import _docstring_to_help, _strip_md, build_full_cli


def test_strip_md_inline_emphasis() -> None:
    assert _strip_md("This is **bold** and *italic*.") == "This is bold and italic."


def test_strip_md_links() -> None:
    assert _strip_md("See [the docs](https://example.com).") == "See the docs (https://example.com)."


def test_strip_md_inline_code() -> None:
    assert _strip_md("Use `await ctx.info(...)` to log.") == "Use await ctx.info(...) to log."


def test_strip_md_passes_plain_text() -> None:
    assert _strip_md("plain text with no markup") == "plain text with no markup"


def test_docstring_first_line_is_short_help() -> None:
    def fn() -> dict:
        """Fetch content from a URL.

        Tries an adaptive cascade.
        """

    short, _long = _docstring_to_help(fn)
    assert short == "Fetch content from a URL."


def test_docstring_long_body_includes_dedented_paragraphs() -> None:
    def fn() -> dict:
        """First line summary.

        A second paragraph with **bold** text.
        """

    _short, long_help = _docstring_to_help(fn)
    assert "First line summary." in long_help
    assert "A second paragraph with bold text." in long_help
    assert "**" not in long_help


def test_docstring_empty_returns_empty_strings() -> None:
    def fn() -> dict:
        return {}

    assert _docstring_to_help(fn) == ("", "")


# --- End-to-end CLI rendering --- #


class FetchRouter(a2kit.Router):
    slug = "fetch"

    @a2kit.read()
    async def fetch(
        self,
        *,
        url: Annotated[str, pydantic.Field(description="Absolute http(s) URL to fetch.")],
        timeout: Annotated[int, pydantic.Field(description="Per-call budget in seconds.")] = 30,
    ) -> dict[str, str]:
        """Fetch content from a URL.

        Tries an adaptive cascade: handlers, then raw HTTP, then the reader API.
        Returns the extracted markdown plus a structured **diagnostic** trace.
        See [the docs](https://example.com) for tier details.
        """
        return {"url": url, "timeout": str(timeout)}

    tools = (fetch,)


def _build_cli() -> object:
    app = a2kit.App("descriptions")
    app.add_router(FetchRouter())
    return build_full_cli(app)


def test_cli_short_help_uses_first_docstring_line() -> None:
    cli = _build_cli()
    result = CliRunner().invoke(cli, ["fetch", "--help"])
    assert result.exit_code == 0, result.output
    # Router-group --help lists tool subcommands with their short_help string.
    assert "Fetch content from a URL." in result.output


def test_cli_help_strips_markdown() -> None:
    cli = _build_cli()
    result = CliRunner().invoke(cli, ["fetch", "fetch", "--help"])
    assert result.exit_code == 0, result.output
    # `**diagnostic**` rendered without markers.
    assert "diagnostic" in result.output
    assert "**diagnostic**" not in result.output
    # Link rewritten to "text (url)" — click wraps lines so collapse whitespace
    # before the substring check.
    collapsed = " ".join(result.output.split())
    assert "the docs (https://example.com)" in collapsed


def test_cli_param_description_forwarded() -> None:
    cli = _build_cli()
    result = CliRunner().invoke(cli, ["fetch", "fetch", "--help"])
    assert result.exit_code == 0, result.output
    assert "Absolute http(s) URL to fetch." in result.output
    assert "Per-call budget in seconds." in result.output


def test_param_returns_pydantic_field_info() -> None:
    """`pydantic.Field(description=...)` returns a pydantic FieldInfo so MCP
    schema generation (which delegates to pydantic) picks up the description
    automatically.
    """
    import typing

    from pydantic.fields import FieldInfo

    def fn(*, url: Annotated[str, pydantic.Field(description="The URL.")]) -> dict:
        return {}

    hints = typing.get_type_hints(fn, include_extras=True)
    args = typing.get_args(hints["url"])
    metadata = args[1]
    assert isinstance(metadata, FieldInfo)
    assert metadata.description == "The URL."
