"""The a2kit code-mode sandbox runtime — type-checked Monty execution via ``A2kitSandboxProvider``."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

# The `execute` tool description — a load-bearing, eval-gated artifact
# (spike F7). Cheap-model correctness is gated by the precision of this
# contract, not by model capability. Covered by the permanent eval fixture.
EXECUTE_DESCRIPTION = """\
Execute Python in a sandbox to call tools and compute an answer.

`await call_tool(name: str, params: dict)` is in scope. Its result is an
OBJECT with attribute access — `page.items`, `task.title`. Never subscript
a call_tool result (`page["items"]` is wrong); the type checker rejects it.

Output contract — read carefully, this is what makes the call succeed:
  - The answer is the value of the LAST line of your code: a bare
    expression that evaluates to it.
  - If you define an async function, the final line must be
    `await your_function()`. Never use a top-level `return`.
  - Prefer a flat list of records, or a flat dict, as the answer — flat
    results travel back compressed and cheap.

Discover tools with `search` and `get_schema` before calling them. Your
code is type-checked against the real tool schemas before it runs; a type
error comes back with a precise message to fix.
"""


def _extract_code(text: str) -> str:
    """Pull a Python code block out of a model response, fences stripped."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _type_error(message: str) -> Exception:
    """A wire-visible error carrying a monty type diagnostic.

    Raised as a ``ToolError`` so the message reaches the agent verbatim
    (FastMCP re-raises ``FastMCPError`` subclasses unmasked) — the agent
    sees exactly what to fix.
    """
    from fastmcp.exceptions import ToolError

    return ToolError(f"Sandbox code rejected by the type checker:\n{message}")


class A2kitSandboxProvider:
    """Monty sandbox provider with pre-execution type-checking — handed the
    generated stubs and dataclass registry by ``A2kitCodeMode``, it type-checks
    submitted code (retrying once via sampling) before executing.
    """

    def __init__(self, *, limits: Any | None = None) -> None:
        self._limits = limits

    async def run(
        self,
        code: str,
        *,
        external_functions: dict[str, Callable[..., Any]],
        stubs: str,
        dataclass_registry: list[type],
        ctx: Any | None = None,
    ) -> Any:
        """Type-check ``code`` against ``stubs``, then execute it.

        On a first-pass type error the diagnostic is fed back to the model
        for one retry; a second failure raises without executing.
        """
        import pydantic_monty as pm

        validated = await self._validate(code, stubs, ctx)
        monty = pm.Monty(validated, dataclass_registry=dataclass_registry or None)
        return await monty.run_async(
            external_functions=external_functions,
            limits=self._limits,
        )

    async def _validate(self, code: str, stubs: str, ctx: Any | None) -> str:
        """Return type-checking code, retrying once via sampling on error."""
        error = self._type_check(code, stubs)
        if error is None:
            return code

        fixed = await self._sample_fix(code, error, ctx) if ctx is not None else None
        if fixed is None:
            # No sampling available, or it failed — the call fails here,
            # before any execution, with the original diagnostic.
            raise _type_error(error)

        retry_error = self._type_check(fixed, stubs)
        if retry_error is None:
            return fixed
        raise _type_error(retry_error)

    @staticmethod
    def _type_check(code: str, stubs: str) -> str | None:
        """Type-check ``code`` against ``stubs``; return the error text or None."""
        import pydantic_monty as pm

        try:
            pm.Monty(code, type_check=True, type_check_stubs=stubs)
        except (pm.MontyTypingError, pm.MontySyntaxError) as exc:
            return str(exc)
        except Exception as exc:  # noqa: BLE001 -- any check failure blocks execution
            return f"{type(exc).__name__}: {exc}"
        return None

    @staticmethod
    async def _sample_fix(code: str, error: str, ctx: Any) -> str | None:
        """Ask the client's model, via MCP sampling, to fix a type error.

        Returns the corrected code, or ``None`` when the client does not
        support sampling (the call then fails with the type error).
        """
        prompt = (
            "Your sandboxed Python failed a static type check. Fix it.\n\n"
            f"Type error:\n{error}\n\n"
            f"Code:\n{code}\n\n"
            "Output ONLY the corrected Python code."
        )
        try:
            response = await ctx.sample(prompt)
        except Exception:  # noqa: BLE001 -- sampling unsupported / failed → no retry
            return None
        text = getattr(response, "text", None)
        if text is None:
            text = str(response)
        fixed = _extract_code(text)
        return fixed or None


__all__ = ["EXECUTE_DESCRIPTION", "A2kitSandboxProvider"]
