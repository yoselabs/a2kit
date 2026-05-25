"""BDD scenarios for raises-registry."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from a2effect import raises_registry


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    raises_registry.reset_for_testing()
    yield
    raises_registry.reset_for_testing()


def test_lookup_for_httpx_get_returns_declared_set() -> None:
    result = raises_registry.get("httpx.AsyncClient.get")
    assert "httpx.RequestError" in result
    assert "httpx.HTTPStatusError" in result
    assert "httpx.TimeoutException" in result


def test_lookup_for_asyncpg_fetch_returns_declared_set() -> None:
    result = raises_registry.get("asyncpg.Connection.fetch")
    assert "asyncpg.PostgresError" in result


def test_unknown_function_returns_empty_frozenset() -> None:
    assert raises_registry.get("some.unknown.func") == frozenset()


def test_extend_adds_new_function_entry() -> None:
    raises_registry.extend({"mymodule.MyClient.fetch": ["mymodule.FetchError"]})
    result = raises_registry.get("mymodule.MyClient.fetch")
    assert result == frozenset({"mymodule.FetchError"})


def test_extension_takes_precedence_on_key_collision() -> None:
    raises_registry.extend({"httpx.AsyncClient.get": ["my.OverrideError"]})
    assert raises_registry.get("httpx.AsyncClient.get") == frozenset({"my.OverrideError"})


def test_load_pyproject_extension_reads_tool_a2effect_table(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        textwrap.dedent(
            """
            [tool.a2effect.raises_registry]
            "mymodule.MyClient.fetch" = ["mymodule.FetchError", "httpx.TimeoutException"]
            "mymodule.MyClient.create" = ["mymodule.ConflictError"]
            """
        ).strip()
    )
    raises_registry.load_pyproject_extension(tmp_path)
    assert raises_registry.get("mymodule.MyClient.fetch") == frozenset({"mymodule.FetchError", "httpx.TimeoutException"})
    assert raises_registry.get("mymodule.MyClient.create") == frozenset({"mymodule.ConflictError"})
    # Built-ins still resolvable
    assert "httpx.RequestError" in raises_registry.get("httpx.AsyncClient.get")


def test_load_pyproject_extension_no_op_when_file_missing(tmp_path: Path) -> None:
    raises_registry.load_pyproject_extension(tmp_path)
    assert "httpx.RequestError" in raises_registry.get("httpx.AsyncClient.get")


def test_load_pyproject_extension_no_op_when_table_missing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
    raises_registry.load_pyproject_extension(tmp_path)
    assert raises_registry.get("anything") == frozenset()


def test_importing_registry_does_not_pull_third_party_libs() -> None:
    # Run in a fresh subprocess so we measure cold import.
    code = textwrap.dedent(
        """
        import sys
        import a2effect.raises_registry
        a2effect.raises_registry.get("httpx.AsyncClient.get")  # force cache load
        forbidden = {"httpx", "asyncpg", "redis", "sqlalchemy"}
        leaked = forbidden & set(sys.modules)
        if leaked:
            print("LEAKED:", ",".join(sorted(leaked)))
            sys.exit(1)
        print("CLEAN")
        """
    ).strip()
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert "CLEAN" in result.stdout


def test_read_inline_annotation_picks_up_may_raise_comment() -> None:
    async def fetch(url: str) -> dict:
        # a2effect: may-raise FetchError, httpx.TimeoutException
        return {"url": url}

    declared = raises_registry.read_inline_annotation(fetch)
    assert declared == frozenset({"FetchError", "httpx.TimeoutException"})


def test_read_inline_annotation_returns_empty_when_no_comment() -> None:
    async def fetch(url: str) -> dict:
        return {"url": url}

    assert raises_registry.read_inline_annotation(fetch) == frozenset()


def test_read_inline_annotation_handles_multiple_comments() -> None:
    async def fetch(url: str) -> dict:
        # a2effect: may-raise First
        # a2effect: may-raise Second, Third
        return {"url": url}

    declared = raises_registry.read_inline_annotation(fetch)
    assert declared == frozenset({"First", "Second", "Third"})


def test_read_inline_annotation_ignores_non_matching_comments() -> None:
    async def fetch(url: str) -> dict:
        # ordinary comment
        # a2effect: may-raise X
        # TODO: unrelated comment
        return {"url": url}

    assert raises_registry.read_inline_annotation(fetch) == frozenset({"X"})
