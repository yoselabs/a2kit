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
    def __init__(self, fn_name: str, *, message: str | None = None) -> None:
        self.fn_name = fn_name
        default = f"Tool {fn_name!r} declares `-> str`. FastMCP double-serialises strings; return a dict or Pydantic model instead."
        super().__init__(message if message is not None else default)


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


class AmbientContextMissing(A2KitError, RuntimeError):
    """Raised when an LDD primitive cannot find a usable ambient ``ctx``.

    Two failure modes share this class (v0.33 splits the message):

    - **Mode A — no active dispatch.** The ``_LDD_STATE`` ContextVar is unset.
      Happens when LDD primitives are called from module-import-time code,
      lifecycle hooks, or any pre-dispatch context.
    - **Mode B — dispatch active, tool missing ``ctx`` parameter.** The
      ContextVar IS set (the dispatcher entered a scope), but the running
      tool's signature does not declare ``ctx: a2kit.ToolContext``, so
      ``state.ctx is None``.

    The message identifies which mode fired and points at the actionable
    fix at the call site.
    """

    MODE_NO_DISPATCH = "no_dispatch"
    MODE_MISSING_CTX_PARAM = "missing_ctx_param"

    def __init__(self, fn_name: str, *, mode: str = MODE_NO_DISPATCH) -> None:
        self.fn_name = fn_name
        self.mode = mode
        if mode == self.MODE_MISSING_CTX_PARAM:
            super().__init__(
                f"{fn_name} called from a tool body that did not declare "
                "`ctx: a2kit.ToolContext` as a parameter. Add the parameter "
                "to the tool signature (the dispatcher will bind it ambient), "
                "or remove the LDD call."
            )
        else:
            super().__init__(
                f"{fn_name} called outside an active tool dispatch. LDD "
                "primitives only work inside a tool body (or any code "
                "reached from one). Move the call into a tool, use the "
                "test harness's ldd_state_for_call(ctx=...) context manager, "
                "or remove the call."
            )


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


class A2KitDecoratedMethodNotInTools(A2KitError, TypeError):
    """Raised at ``App.add_router`` time when a Router subclass has
    ``@a2kit.read/write/list_/tool``-decorated methods that are not
    listed in its ``tools`` tuple.

    Without this check, the methods register no tools — they're
    invisible on every transport. The footgun is tier-1: adding a
    tool, forgetting to update the tuple, deploying, debugging why
    "the tool isn't there."
    """

    def __init__(self, router_cls_name: str, missing: list[str]) -> None:
        self.router_cls_name = router_cls_name
        self.missing = list(missing)
        missing_quoted = ", ".join(repr(m) for m in missing)
        super().__init__(
            f"Router {router_cls_name!r} has decorated methods that "
            f"are not in its `tools` tuple: {missing_quoted}. "
            "Either add them to `tools = (...)`, or remove the "
            "`@a2kit.read/write/list_/tool` decorator from methods "
            "you don't want registered."
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


class AuthorizationDenied(A2KitError, PermissionError):
    """Raised by `AuthorizeGateStage` when a tool's `authorize=` callable
    returns a falsy value.

    Maps to HTTP 403 on FastAPI and to the documented MCP error envelope.
    The tool body is never invoked.
    """

    def __init__(self, *, reason: str, callable_name: str) -> None:
        self.reason = reason
        self.callable_name = callable_name
        super().__init__(f"authorization denied by {callable_name!r}: {reason}")


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
