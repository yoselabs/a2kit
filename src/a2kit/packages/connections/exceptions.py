"""Connection / token typed exceptions."""

from __future__ import annotations


class ConnectionNotFound(FileNotFoundError):
    available_connections: list[str]

    def __init__(self, key: tuple[str, ...]) -> None:
        self.key = key
        self.available_connections = []
        super().__init__(f"Connection not found: {'/'.join(key)}")


class InvalidConnectionKey(ValueError):
    def __init__(self, part: str) -> None:
        self.part = part
        super().__init__(
            f"Invalid connection key part {part!r}: must start with alphanumeric, contain only [A-Za-z0-9._-], and be non-empty."
        )


class KeyFieldMissing(KeyError):
    def __init__(self, field: str, *, have: list[str], key_class: str | None = None) -> None:
        self.field = field
        self.have = list(have)
        self.key_class = key_class
        suffix = f" on {key_class}" if key_class else ""
        super().__init__(
            f"Missing key field {field!r}{suffix}; have: {sorted(self.have)}. "
            f"Pass it as a keyword argument to load()/delete(), or construct the typed key directly."
        )


class KeyArityMismatch(ValueError):
    def __init__(self, *, expected: tuple[str, ...], got: tuple[str, ...], key_class: str | None = None) -> None:
        self.expected = expected
        self.got = got
        self.key_class = key_class
        suffix = f" {key_class}({', '.join(expected)})" if key_class else f"={list(expected)}"
        super().__init__(f"Key arity mismatch:{suffix} (arity {len(expected)}) but got {list(got)} (arity {len(got)}).")


class TokenResolutionError(Exception):
    """Base for token-resolution failures."""


class EnvVarNotFound(TokenResolutionError):
    def __init__(self, var: str, ref: str) -> None:
        self.var = var
        self.ref = ref
        super().__init__(f"Environment variable {var!r} (referenced as {ref}) is not set.")


class OpResolutionError(TokenResolutionError):
    def __init__(self, ref: str, hint: str) -> None:
        self.ref = ref
        self.hint = hint
        super().__init__(f"Failed to resolve 1Password reference {ref!r}: {hint}")


# --- Class-based DI exceptions (moved from core in pluggable-core-architecture) --- #


class ConnectionKwargMissing(TypeError):
    def __init__(self, conn_type: type, tool_name: str | None = None) -> None:
        self.conn_type = conn_type
        self.tool_name = tool_name
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(f"`Depends({conn_type.__name__})` requires a `connection: str` kwarg on the tool signature{suffix}.")


class ConnectionNotRegistered(RuntimeError):
    def __init__(self, conn_type: type) -> None:
        self.conn_type = conn_type
        super().__init__(
            f"`Depends({conn_type.__name__})` references an unregistered connection class. "
            f"Call `app.use(Connections())` then `app.use({conn_type.__name__})` before use."
        )


class StoreConnectionTypeUnknown(TypeError):
    def __init__(self, store_type: type) -> None:
        self.store_type = store_type
        super().__init__(
            f"`Depends({store_type.__name__})` cannot determine its connection type. "
            f"Either set `{store_type.__name__}.conn_type = YourConnT` or inherit from "
            f"`a2kit.packages.connections.Store[YourConnT]`."
        )
