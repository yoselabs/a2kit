from __future__ import annotations

from a2effect import AppError


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
    def __init__(self, fn_name: str, *, message: str | None = None) -> None:
        self.fn_name = fn_name
        default = f"Tool {fn_name!r} declares `-> str`. FastMCP double-serialises strings; return a dict or Pydantic model instead."
        super().__init__(message if message is not None else default)


class A2KitContextBindingBroken(A2KitError, RuntimeError):
    """Raised at App-construction time when the MCP wrapper chain's
    rewritten signature does not contain a tool's ``ctx`` parameter.

    This is a framework-internal invariant check — user code cannot
    cause this. It fires when a future change to the wrapper chain
    (e.g. a refactor of ``_wrap_with_dispatch_hook``) drops ``ctx``
    from the rewritten signature, preventing FastMCP from binding
    the live ``Context`` at call time.
    """

    def __init__(self, fn_name: str, *, ctx_param_name: str) -> None:
        self.fn_name = fn_name
        self.ctx_param_name = ctx_param_name
        super().__init__(
            f"a2kit-internal: rewritten MCP signature for {fn_name!r} "
            f"does not contain ctx parameter {ctx_param_name!r}. This "
            "indicates a wrapper-chain regression; user code cannot "
            "cause this. Please file an issue."
        )


class A2KitSingletonTeardownError(A2KitError, RuntimeError):
    """Aggregates teardown failures from ``App._run_teardowns``.

    The framework does NOT raise this — it stashes failures on
    ``App.teardown_failures`` for programmatic introspection. The
    primary surface is an ``error``-level Python log line emitted per
    failing teardown. This class exists so callers who want to
    detect-and-react have a typed handle (e.g. test fixtures asserting
    that shutdown ran clean).
    """

    def __init__(self, failures: list[tuple[type, Exception]]) -> None:
        self.failures = list(failures)
        rendered = "; ".join(f"{t.__name__}: {type(exc).__name__}: {exc}" for t, exc in failures)
        super().__init__(f"a2kit singleton-teardown failures ({len(failures)}): {rendered}")


class AuthorizationDenied(AppError):
    """Raised by `AuthorizeGateStage` when a tool's `authorize=` callable
    returns a falsy value.

    Typed as an `a2effect.AppError` (kind=auth, http_status=403, exit=77)
    so it flows through the same envelope-rendering pipeline as every
    other typed error. The tool body is never invoked.
    """

    kind = "auth"
    http_status = 403
    cli_exit_code = 77
    kind_label = "Authorization denied"

    def __init__(self, *, reason: str, callable_name: str) -> None:
        self.reason = reason
        self.callable_name = callable_name
        super().__init__(
            f"authorization denied by {callable_name!r}: {reason}",
            details={"reason": reason, "callable": callable_name},
        )


class A2KitInvalidContextAnnotation(A2KitError, TypeError):
    """Raised at decoration time when a tool declares ``ctx`` with an
    Optional/Union annotation form.

    The dispatcher always binds ``ctx`` when declared (live
    ``fastmcp.Context`` on MCP, ``StderrToolContext`` on CLI). There
    is no runtime path that produces ``None`` for a declared ``ctx``.
    The Optional form is misleading typing with no corresponding
    runtime semantics.
    """

    def __init__(self, fn_name: str, *, param_name: str, hint: str) -> None:
        self.fn_name = fn_name
        self.param_name = param_name
        self.hint = hint
        super().__init__(f"Tool {fn_name!r}: parameter {param_name!r} has an Optional/Union annotation form for `ctx`. {hint}")
