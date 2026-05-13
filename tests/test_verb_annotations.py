"""MCP ``ToolAnnotations`` kwargs on verb decorators — v0.33 spec.

Read-shaped verbs (``@read``, ``@list_``) reject ``idempotent=`` and
``destructive=`` at decoration time per MCP spec (those hints are
meaningful only when ``readOnlyHint=false``).

``annotations=`` is the full escape hatch — mixing it with flag kwargs
raises ``TypeError``.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.metadata import get_meta


def _meta_for(fn):
    return get_meta(fn)


def test_read_with_annotations() -> None:
    @a2kit.read(open_world=True, title="Fetch Web Page")
    async def fetch() -> dict:
        return {}

    ann = _meta_for(fetch).annotations
    assert ann.readOnlyHint is True
    assert ann.idempotentHint is False
    assert ann.destructiveHint is False
    assert ann.openWorldHint is True
    assert ann.title == "Fetch Web Page"


def test_read_destructive_raises() -> None:
    with pytest.raises(TypeError, match="destructive"):

        @a2kit.read(destructive=True)
        async def boom() -> dict:
            return {}


def test_read_idempotent_raises() -> None:
    """v0.33: `idempotent=` on @read raises (MCP spec: meaningful only when readOnlyHint=false)."""
    with pytest.raises(TypeError, match="idempotent"):

        @a2kit.read(idempotent=True)
        async def boom() -> dict:
            return {}


def test_list_idempotent_raises() -> None:
    """v0.33: `idempotent=` on @list_ raises (mirror of @read)."""
    with pytest.raises(TypeError, match="idempotent"):

        @a2kit.list_("id", idempotent=True)
        async def boom() -> list[dict]:
            return []


def test_list_destructive_raises() -> None:
    """v0.33: `destructive=` on @list_ raises."""
    with pytest.raises(TypeError, match="destructive"):

        @a2kit.list_("id", destructive=True)
        async def boom() -> list[dict]:
            return []


def test_list_non_collection_return_raises() -> None:
    """v0.33: @list_ on a non-collection return annotation raises at decoration."""
    with pytest.raises(TypeError, match="list"):

        @a2kit.list_("id")
        async def boom() -> dict:
            return {}


def test_list_missing_return_raises() -> None:
    """v0.33: @list_ requires a return annotation."""
    with pytest.raises(TypeError, match="return annotation"):

        @a2kit.list_("id")
        async def boom():  # no return annotation
            return []


def test_list_page_size_zero_raises() -> None:
    """v0.33: @list_(page_size=0) raises ValueError."""
    with pytest.raises(ValueError, match="page_size"):

        @a2kit.list_("id", page_size=0)
        async def boom() -> list[dict]:
            return []


def test_list_page_size_negative_raises() -> None:
    """v0.33: @list_(page_size=-1) raises ValueError."""
    with pytest.raises(ValueError, match="page_size"):

        @a2kit.list_("id", page_size=-1)
        async def boom() -> list[dict]:
            return []


def test_read_name_kwarg_rejected() -> None:
    """v0.33: `name=` removed from public verb decorators."""
    with pytest.raises(TypeError, match="name"):
        a2kit.read(name="custom")  # type: ignore[call-arg]


def test_write_name_kwarg_rejected() -> None:
    with pytest.raises(TypeError, match="name"):
        a2kit.write(name="custom")  # type: ignore[call-arg]


def test_list_name_kwarg_rejected() -> None:
    with pytest.raises(TypeError, match="name"):
        a2kit.list_("id", name="custom")  # type: ignore[call-arg]


def test_write_destructive_override() -> None:
    @a2kit.write(destructive=False, idempotent=True, title="Mark Complete")
    async def mark_complete() -> dict:
        return {}

    ann = _meta_for(mark_complete).annotations
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is False
    assert ann.idempotentHint is True
    assert ann.title == "Mark Complete"


def test_write_default_destructive_true() -> None:
    @a2kit.write()
    async def delete_thing() -> dict:
        return {}

    ann = _meta_for(delete_thing).annotations
    assert ann.destructiveHint is True
    assert ann.openWorldHint is False
    assert ann.idempotentHint is False


def test_read_defaults_conservative() -> None:
    @a2kit.read()
    async def get_thing() -> dict:
        return {}

    ann = _meta_for(get_thing).annotations
    assert ann.readOnlyHint is True
    assert ann.idempotentHint is False
    assert ann.openWorldHint is False
    assert ann.destructiveHint is False
    assert ann.title is None


def test_explicit_annotations_kwarg_conflicts_with_flag_kwargs() -> None:
    """v0.33: mixing `annotations=` with any flag kwarg raises TypeError."""
    from mcp.types import ToolAnnotations

    explicit = ToolAnnotations(readOnlyHint=False, idempotentHint=True, title="Custom")

    with pytest.raises(TypeError, match="annotations"):

        @a2kit.write(annotations=explicit, idempotent=False)
        async def custom() -> dict:
            return {}


def test_explicit_annotations_kwarg_conflicts_with_title() -> None:
    """v0.33: even title= conflicts with annotations=."""
    from mcp.types import ToolAnnotations

    explicit = ToolAnnotations(readOnlyHint=False, title="X")

    with pytest.raises(TypeError, match="annotations"):

        @a2kit.write(annotations=explicit, title="Y")
        async def custom() -> dict:
            return {}


def test_explicit_annotations_kwarg_alone_accepted() -> None:
    """`annotations=` alone (no flag kwargs) is accepted as the escape hatch."""
    from mcp.types import ToolAnnotations

    explicit = ToolAnnotations(readOnlyHint=False, idempotentHint=True, title="Custom")

    @a2kit.write(annotations=explicit)
    async def custom() -> dict:
        return {}

    ann = _meta_for(custom).annotations
    assert ann is explicit


def test_tool_function_removed() -> None:
    """``a2kit.tool.tool()`` function was deleted in v0.33.

    Note: ``a2kit.tool`` remains as a submodule (internal code imports from
    it), so a direct attribute hint via ``__getattr__`` is unreliable once
    the submodule has loaded. The robust check is import of the missing
    function.
    """
    with pytest.raises(ImportError):
        from a2kit.tool import tool  # noqa: F401


def test_a2kit_tool_attribute_in_subprocess_raises_with_hint() -> None:
    """v0.33: a fresh `import a2kit` + `a2kit.tool` raises AttributeError with v0.33 hint.

    Uses subprocess isolation to bypass Python's module cache — in-process
    tests can't reliably check this because other tests may import the
    ``a2kit.tool`` submodule first, which then masks the ``__getattr__``
    fallback. The subprocess gives the cold-start path real users hit.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import a2kit; a2kit.tool"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "v0.33" in result.stderr
    assert "AttributeError" in result.stderr
