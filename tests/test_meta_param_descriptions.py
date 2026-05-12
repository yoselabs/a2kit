"""Tests — A2KitMeta.param_descriptions (cleanup-round-5-6-docs-alignment, item J).

The Google-style docstring `Args:` block is resolved at decoration
time and stored on `A2KitMeta.param_descriptions` (authoritative
mapping for downstream readers) AND mirrored on
`fn.__annotations__` via `Annotated[T, Param(...)]` (carrier for
FastMCP schema gen).
"""

from __future__ import annotations

from typing import Annotated

import a2kit
from a2kit.metadata import get_meta
from a2kit.params import Param


class _DocstringRouter(a2kit.Router):
    @a2kit.read()
    async def fetch(
        self,
        *,
        url: str,
        timeout: int = 30,
    ) -> dict[str, int | str]:
        """Fetch content from a URL.

        Args:
            url: Absolute http(s) URL to fetch.
            timeout: Seconds to wait before giving up.
        """
        return {"status": 200, "_timeout": timeout, "_url_len": len(url)}


def test_meta_param_descriptions_populated_from_docstring() -> None:
    meta = get_meta(_DocstringRouter.fetch)
    assert meta is not None
    assert meta.param_descriptions["url"] == "Absolute http(s) URL to fetch."
    assert meta.param_descriptions["timeout"] == "Seconds to wait before giving up."


def test_meta_param_descriptions_empty_when_no_args_section() -> None:
    class _NoArgsRouter(a2kit.Router):
        @a2kit.read()
        async def ping(self) -> dict[str, str]:
            """No Args section here."""
            return {"ok": "yes"}

    meta = get_meta(_NoArgsRouter.ping)
    assert meta is not None
    assert dict(meta.param_descriptions) == {}


class _ExplicitWinsRouter(a2kit.Router):
    @a2kit.read()
    async def fetch_explicit(
        self,
        *,
        url: Annotated[str, Param(description="EXPLICIT wins")],
    ) -> dict[str, str]:
        """Fetch.

        Args:
            url: From docstring (should not appear in annotations).
        """
        return {"url": url}


def test_meta_keeps_docstring_value_even_when_annotation_overrides() -> None:
    """`param_descriptions` is the raw docstring resolution. The
    precedence rule (explicit Annotated wins) applies to the annotation
    surface only; meta keeps the docstring's view of the world so
    downstream tools can show both."""
    meta = get_meta(_ExplicitWinsRouter.fetch_explicit)
    assert meta is not None
    assert meta.param_descriptions["url"] == "From docstring (should not appear in annotations)."
