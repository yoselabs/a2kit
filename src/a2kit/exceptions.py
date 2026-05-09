from __future__ import annotations


class A2KitError(Exception):
    pass


class ToolCallContamination(A2KitError, ValueError):
    def __init__(self, param_name: str, tool_name: str | None = None) -> None:
        self.param_name = param_name
        self.tool_name = tool_name
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(
            f"Parameter {param_name!r} contains a tool-call envelope tag (`<parameter name=`)"
            f"{suffix}. Re-issue the call with the parameter value alone."
        )


class InvalidToolReturnTypeError(A2KitError, TypeError):
    def __init__(self, fn_name: str) -> None:
        self.fn_name = fn_name
        super().__init__(f"Tool {fn_name!r} declares `-> str`. FastMCP double-serialises strings; return a dict or Pydantic model instead.")


class WriteNotAllowed(A2KitError, PermissionError):
    def __init__(self, connection_key: tuple[str, ...], tool_name: str | None = None) -> None:
        self.connection_key = connection_key
        self.tool_name = tool_name
        joined = "-".join(connection_key) if connection_key else "<unknown>"
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(f"Connection {joined!r} is read-only — cannot run write-marked tool{suffix}.")


class InvalidFilterExpression(A2KitError, ValueError):
    def __init__(self, expr: str, hint: str) -> None:
        self.expr = expr
        self.hint = hint
        super().__init__(f"Invalid CEL filter expression {expr!r}: {hint}")
