"""ConnectionStore behaviour: round-trip, key arity, listing, deletion, errors."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from a2kit import (
    ENV_CONFIG_HOME,
    ConnectionInfo,
    ConnectionNotFound,
    ConnectionStore,
    InvalidConnectionKey,
    default_config_dir,
)

from .conftest import AtlassianInfo, DbInfo


async def test_db_roundtrip(db_store: ConnectionStore[DbInfo]) -> None:
    info = DbInfo(key=("acme", "prod", "main"), dsn="postgresql://u@h/db")
    path = await db_store.save(info)
    assert path.name == "acme-prod-main.toml"
    loaded = await db_store.load(("acme", "prod", "main"))
    assert loaded == info


async def test_atlassian_roundtrip(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    info = AtlassianInfo(
        key=("prod",),
        url="https://example.atlassian.net",
        email="dt@example.com",
        token="${ATLASSIAN_TOKEN}",
        read_only=False,
    )
    path = await atlassian_store.save(info)
    assert path.name == "prod.toml"
    loaded = await atlassian_store.load(("prod",))
    assert loaded == info


async def test_save_overwrites(db_store: ConnectionStore[DbInfo]) -> None:
    info1 = DbInfo(key=("a", "b", "c"), dsn="sqlite:///one.db")
    info2 = DbInfo(key=("a", "b", "c"), dsn="sqlite:///two.db")
    await db_store.save(info1)
    await db_store.save(info2)
    assert (await db_store.load(("a", "b", "c"))).dsn == "sqlite:///two.db"


async def test_atomic_save_chmod_0600(db_store: ConnectionStore[DbInfo]) -> None:
    info = DbInfo(key=("a", "b", "c"), dsn="sqlite://")
    path = await db_store.save(info)
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


async def test_load_missing_raises(db_store: ConnectionStore[DbInfo]) -> None:
    with pytest.raises(ConnectionNotFound) as excinfo:
        await db_store.load(("nope", "nope", "nope"))
    assert excinfo.value.key == ("nope", "nope", "nope")


async def test_delete(db_store: ConnectionStore[DbInfo]) -> None:
    info = DbInfo(key=("x", "y", "z"), dsn="sqlite://")
    await db_store.save(info)
    await db_store.delete(("x", "y", "z"))
    with pytest.raises(ConnectionNotFound):
        await db_store.load(("x", "y", "z"))


async def test_delete_missing_raises(db_store: ConnectionStore[DbInfo]) -> None:
    with pytest.raises(ConnectionNotFound):
        await db_store.delete(("missing", "1", "2"))


async def test_list_empty_when_dir_absent(tmp_path: Path) -> None:
    store: ConnectionStore[DbInfo] = ConnectionStore(tmp_path / "does-not-exist", DbInfo)
    assert await store.list_connections() == []


async def test_list_returns_sorted(db_store: ConnectionStore[DbInfo]) -> None:
    await db_store.save(DbInfo(key=("z", "p", "m"), dsn="sqlite://"))
    await db_store.save(DbInfo(key=("a", "p", "m"), dsn="sqlite://"))
    await db_store.save(DbInfo(key=("m", "p", "m"), dsn="sqlite://"))
    listed = await db_store.list_connections()
    assert [info.key for info in listed] == [("a", "p", "m"), ("m", "p", "m"), ("z", "p", "m")]


async def test_invalid_key_part_rejected_in_model() -> None:
    with pytest.raises(ValueError, match="Invalid connection key part"):
        DbInfo(key=("ok", "bad name", "x"), dsn="sqlite://")


async def test_invalid_key_part_rejected_in_store(db_store: ConnectionStore[DbInfo]) -> None:
    with pytest.raises(InvalidConnectionKey):
        await db_store.load(("bad name", "x", "y"))


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        DbInfo(key=(), dsn="sqlite://")


def test_arity_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match=r"arity mismatch|arity 3"):
        DbInfo(key=("only-one",), dsn="sqlite://")


def test_default_key_fields_single_name() -> None:
    """Subclass without KEY_FIELDS gets the default `("name",)` shape."""

    class Flexible(ConnectionInfo):
        value: str

    assert Flexible(key=("a",), value="x").filename == "a.toml"
    with pytest.raises(ValueError, match="arity"):
        Flexible(key=("a", "b"), value="x")


def test_default_config_dir_uses_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_CONFIG_HOME, raising=False)
    expected = Path.home() / ".config" / "a2kit" / "connections"
    assert default_config_dir() == expected


async def test_default_config_dir_honours_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_CONFIG_HOME, str(tmp_path / "override"))
    assert default_config_dir() == tmp_path / "override"


async def test_save_creates_config_dir(tmp_path: Path) -> None:
    target = tmp_path / "fresh" / "subdir"
    store: ConnectionStore[DbInfo] = ConnectionStore(target, DbInfo)
    await store.save(DbInfo(key=("a", "b", "c"), dsn="sqlite://"))
    assert target.is_dir()


async def test_save_atomic_cleanup_on_failure(db_store: ConnectionStore[DbInfo], monkeypatch: pytest.MonkeyPatch) -> None:
    """If chmod fails, no tempfile should be left behind."""
    info = DbInfo(key=("a", "b", "c"), dsn="sqlite://")
    real_chmod = Path.chmod

    def boom(self: Path, mode: int) -> None:
        if self.suffix == ".tmp":
            raise OSError("simulated chmod failure")
        real_chmod(self, mode)

    monkeypatch.setattr(Path, "chmod", boom)
    with pytest.raises(OSError, match="simulated chmod failure"):
        await db_store.save(info)
    leftovers = list(db_store.config_dir.glob(".*-*.tmp"))
    assert leftovers == []


def test_filename_property() -> None:
    info = DbInfo(key=("acme", "prod", "main"), dsn="sqlite://")
    assert info.filename == "acme-prod-main.toml"


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValueError, match="Extra inputs"):
        DbInfo(key=("a", "b", "c"), dsn="sqlite://", surprise="boom")  # type: ignore[call-arg]


async def test_frozen_model_is_immutable() -> None:
    info = DbInfo(key=("a", "b", "c"), dsn="sqlite://")
    with pytest.raises(ValueError, match="frozen"):
        info.dsn = "other"  # type: ignore[misc]


async def test_listing_with_tuple_subclass_field(atlassian_store: ConnectionStore[AtlassianInfo]) -> None:
    """Cover the tuple-field coercion path on save (extra tuple field on subclass)."""

    class WithTuple(ConnectionInfo):
        admins: tuple[str, ...] = ()

    store: ConnectionStore[WithTuple] = ConnectionStore(atlassian_store.config_dir, WithTuple)
    await store.save(WithTuple(key=("x",), admins=("alice", "bob")))
    loaded = await store.load(("x",))
    assert loaded.admins == ("alice", "bob")
    listed = await store.list_connections()
    assert listed[0].admins == ("alice", "bob")


async def test_list_skips_dir_when_missing_after_init(tmp_path: Path) -> None:
    """list_connections returns [] when config_dir doesn't exist (defensive path)."""
    nonexistent = tmp_path / "never-created"
    store: ConnectionStore[DbInfo] = ConnectionStore(nonexistent, DbInfo)
    assert not nonexistent.exists()
    assert await store.list_connections() == []


def test_env_override_is_empty_string_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_CONFIG_HOME, "")
    assert default_config_dir() == Path.home() / ".config" / "a2kit" / "connections"


async def test_invalid_key_in_save_is_caught_by_model() -> None:
    """Model-level validation runs before store-level path derivation."""
    with pytest.raises(ValueError):
        DbInfo(key=("", "b", "c"), dsn="sqlite://")  # noqa: PLC1901


async def test_resolve_token_via_model_subclass(atlassian_store: ConnectionStore[AtlassianInfo], monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: subclass loads a `${ENV_VAR}` token, resolves it lazily."""
    from a2kit import resolve_token

    monkeypatch.setenv("MY_ATLASSIAN_TOKEN", "real-token-value")
    info = AtlassianInfo(
        key=("prod",),
        url="https://example.atlassian.net",
        email="dt@example.com",
        token="${MY_ATLASSIAN_TOKEN}",
    )
    await atlassian_store.save(info)
    loaded = await atlassian_store.load(("prod",))
    assert resolve_token(loaded.token) == "real-token-value"


async def test_save_path_only_visible_to_owner(db_store: ConnectionStore[DbInfo]) -> None:
    """Sanity-check on POSIX systems: file is mode 0600 after save."""
    info = DbInfo(key=("a", "b", "c"), dsn="sqlite://")
    path = await db_store.save(info)
    assert os.stat(path).st_mode & 0o077 == 0


async def test_store_exposes_key_class(db_store: ConnectionStore[DbInfo]) -> None:
    """v0.5: `store.key_class` exposes the NamedTuple key type."""
    from .conftest import DbKey

    assert db_store.key_class is DbKey
    assert db_store.key_class._fields == ("project", "env", "db")


async def test_list_keys_returns_namedtuples(db_store: ConnectionStore[DbInfo]) -> None:
    """v0.5: `await store.list_keys()` returns typed NamedTuple instances."""
    from .conftest import DbKey

    await db_store.save(DbInfo(key=("acme", "prod", "main"), dsn="sqlite://"))
    keys = await db_store.list_keys()
    assert keys == [DbKey(project="acme", env="prod", db="main")]
    # NamedTuple supports both attr-style and index-style access:
    assert keys[0].project == "acme"
    assert keys[0][0] == "acme"
