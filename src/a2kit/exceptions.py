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


class InvalidFilterExpression(A2KitError, ValueError):
    def __init__(self, expr: str, hint: str) -> None:
        self.expr = expr
        self.hint = hint
        super().__init__(f"Invalid CEL filter expression {expr!r}: {hint}")


class ReportTypeNotDeclared(A2KitError, RuntimeError):
    def __init__(self, tool_name: str | None = None) -> None:
        self.tool_name = tool_name
        suffix = f" {tool_name!r}" if tool_name else ""
        super().__init__(
            f"Tool{suffix} called `ctx.report(...)` but no `report=ReportT` "
            f"kwarg was declared on the verb decorator. Add "
            f"`@a2kit.read(report=YourReportModel)` or use `ctx.event(...)` "
            f"for free-form narration."
        )


class ReportTypeMismatch(A2KitError, TypeError):
    def __init__(self, expected: type, got: type, tool_name: str | None = None) -> None:
        self.expected = expected
        self.got = got
        self.tool_name = tool_name
        suffix = f" (tool {tool_name!r})" if tool_name else ""
        super().__init__(f"`ctx.report(...)` payload is a {got.__name__!r}; declared `report=` is {expected.__name__!r}{suffix}.")
