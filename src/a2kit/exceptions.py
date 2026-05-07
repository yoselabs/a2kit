"""Typed exceptions for a2kit ConnectionStore + token resolution."""

from __future__ import annotations


class A2KitError(Exception):
    """Base for all a2kit exceptions."""


class ConnectionNotFound(A2KitError, FileNotFoundError):  # noqa: N818
    """Raised when a connection key has no TOML on disk."""

    def __init__(self, key: tuple[str, ...]) -> None:
        self.key = key
        super().__init__(f"Connection not found: {'/'.join(key)}")


class InvalidConnectionKey(A2KitError, ValueError):  # noqa: N818
    """Raised when a connection key part fails the name policy."""

    def __init__(self, part: str) -> None:
        self.part = part
        super().__init__(
            f"Invalid connection key part {part!r}: must start with alphanumeric, contain only [A-Za-z0-9._-], and be non-empty."
        )


class TokenResolutionError(A2KitError):
    """Base for resolver failures."""


class EnvVarNotFound(TokenResolutionError):  # noqa: N818
    """Raised when a `${ENV_VAR}` reference points to a missing environment variable."""

    def __init__(self, var: str, ref: str) -> None:
        self.var = var
        self.ref = ref
        super().__init__(
            f"Environment variable {var!r} (referenced as {ref}) is not set. "
            f"Export it before invoking the API, or re-login with a different token reference."
        )


class OpResolutionError(TokenResolutionError):
    """Raised when a `op://...` reference cannot be resolved (binary missing, auth expired, etc.)."""

    def __init__(self, ref: str, hint: str) -> None:
        self.ref = ref
        self.hint = hint
        super().__init__(f"Failed to resolve 1Password reference {ref!r}: {hint}")


class InvalidToolReturnTypeError(A2KitError, TypeError):
    """Raised at decoration time when an a2kit-decorated tool declares `-> str`.

    Catches the a2db `4d07632` bug class: FastMCP double-serialises string returns,
    so tools must return dicts or Pydantic models. This is enforced at decoration
    time so the failure fires the moment the file is imported, not at first call.
    """

    def __init__(self, fn_name: str) -> None:
        self.fn_name = fn_name
        super().__init__(
            f"Tool {fn_name!r} declares `-> str`. FastMCP double-serialises strings; "
            "return a dict or Pydantic model instead. (See a2db commit 4d07632.) "
            "If you genuinely need a string return, use a formatter that wraps it in a dict."
        )


class SchemaSnapshotMismatch(A2KitError, AssertionError):  # noqa: N818
    """Raised by `a2kit.testing.assert_schemas_match` on snapshot drift.

    The message contains a unified diff. Re-run the test with
    `--update-schema-snapshots` to accept the change.
    """


class WriteNotAllowed(A2KitError, PermissionError):  # noqa: N818
    """Raised when a write-marked tool runs against a read-only connection.

    The fat `@a2kit.tool(write=True)` decorator enforces this once the resolved
    `ConnectionInfo.read_only` is `True`. Domain MCPs typically catch this and
    surface a re-login hint (matches a2atlassian's `decorators.check_writable`).
    """

    def __init__(self, connection_key: tuple[str, ...], tool_name: str | None = None) -> None:
        self.connection_key = connection_key
        self.tool_name = tool_name
        joined = "-".join(connection_key) if connection_key else "<unknown>"
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(f"Connection {joined!r} is read-only — cannot run write-marked tool{suffix}.")


class ToolXMLContamination(A2KitError, ValueError):  # noqa: N818
    """Raised when a string-typed tool param contains an MCP tool-XML opening tag.

    Contamination pattern observed in production: agents leak the `<parameter name="...">`
    framing into the body of a string argument. The fat decorator's `xml_guard`
    catches it before the tool body runs.
    """

    def __init__(self, param_name: str, tool_name: str | None = None) -> None:
        self.param_name = param_name
        self.tool_name = tool_name
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(
            f"Parameter {param_name!r} contains a tool-XML opening tag (`<parameter name=`)"
            f"{suffix}. The agent likely leaked its tool-call envelope into the value. "
            "Re-issue the call with the parameter value alone."
        )
