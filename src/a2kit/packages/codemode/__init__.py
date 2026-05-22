"""Sandboxed code-execution surface — the single import site for FastMCP's ``CodeMode`` transform and the Monty runtime."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, Annotated, Any

from fastmcp.experimental.transforms.code_mode import CodeMode
from fastmcp.server.context import Context  # noqa: TC002 -- resolved at runtime by FastMCP's `execute` introspection
from pydantic import Field

from a2kit.packages.codemode.marshal import (
    collect_models,
    dataclass_mirror,
    marshal_result,
    unwrap_tool_result,
)
from a2kit.packages.codemode.runtime import EXECUTE_DESCRIPTION, A2kitSandboxProvider
from a2kit.packages.codemode.stubs import generate_stubs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from fastmcp.tools.base import Tool

_CODE_MODE_EXTRA = "a2kit[code-mode]"


def _require_monty() -> None:
    """Raise with a migration hint when the Monty sandbox runtime is absent.

    FastMCP's `CodeMode` module imports cleanly without `pydantic-monty`
    (the runtime is imported lazily on first sandbox execution). This
    check fails fast at transform-build time instead, so a misconfigured
    server crashes at startup rather than on the first `execute` call.
    """
    if importlib.util.find_spec("pydantic_monty") is None:
        raise ImportError(
            "Code execution requires the Monty sandbox runtime, which is "
            f"not installed. Install it with `pip install {_CODE_MODE_EXTRA}`, "
            "or disable the code-execution surface with "
            "`build_mcp_server(app, code_mode=False)` / `serve --code-mode-off`."
        )


def _is_destructive(tool: Tool) -> bool:
    """True when `tool` carries a2kit's `destructive` semantic flag.

    Reads the `A2KitMeta` projection stamped onto `tool.meta["a2kit"]` by
    `build_mcp_server`. Tools with no a2kit metadata (e.g. FastMCP's own)
    are treated as non-destructive — the gate governs a2kit tools.
    """
    meta = getattr(tool, "meta", None)
    a2kit_meta = meta.get("a2kit") if isinstance(meta, dict) else None
    if not isinstance(a2kit_meta, dict):
        return False
    annotations = a2kit_meta.get("annotations")
    if not isinstance(annotations, dict):
        return False
    return bool(annotations.get("destructiveHint", False))


class A2kitCodeMode(CodeMode):
    """FastMCP `CodeMode` plus three a2kit additions: a capability gate
    (`destructive` tools are filtered from the sandbox catalog unless the
    operator opts in), dict→dataclass marshalling of `call_tool` results, and
    pre-execution type-checking via `A2kitSandboxProvider`.
    """

    def __init__(
        self,
        *,
        allow_destructive: bool = False,
        return_types: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._allow_destructive = allow_destructive
        self._return_types: dict[str, Any] = return_types or {}
        # a2kit's provider has a wider `run` signature than the stock
        # `SandboxProvider` Protocol (it takes stubs + registry + ctx), so
        # it is held on its own attribute, not the inherited one.
        self._provider = A2kitSandboxProvider()
        # `execute`-derivation cache, keyed on the sorted catalog tool names
        # → (stubs, registry, return-type map). The catalog can vary with
        # `ctx`, so it cannot be frozen at build time — but for a given
        # tool-name set the derivation is identical.
        self._derivation_cache: dict[tuple[str, ...], tuple[str, list[type], dict[str, Any]]] = {}

    async def get_tool_catalog(self, ctx: Context, *, run_middleware: bool = True) -> Sequence[Tool]:
        tools = await super().get_tool_catalog(ctx, run_middleware=run_middleware)
        if self._allow_destructive:
            return tools
        return [t for t in tools if not _is_destructive(t)]

    def _build_execute_description(self) -> str:
        """a2kit owns the `execute` description — the eval-gated output
        contract (spike F7). Overrides CodeMode's terse default.
        """
        return EXECUTE_DESCRIPTION

    def _make_execute_tool(self) -> Tool:
        """Build the a2kit `execute` tool: catalog → stubs → dataclass
        registry (cached per catalog), marshalling `call_tool` results, run
        in the type-checking `A2kitSandboxProvider`.
        """
        from fastmcp.exceptions import NotFoundError
        from fastmcp.tools.base import Tool, ToolResult

        from a2kit.packages.formatter import render_execute

        transform = self

        async def execute(
            code: Annotated[
                str,
                Field(description="Python async code; call tools via call_tool(name, params)"),
            ],
            ctx: Context = None,  # type: ignore[assignment]  # ty:ignore[invalid-parameter-default]
        ) -> Any:
            """Execute tool calls using Python code."""
            catalog = await transform.get_tool_catalog(ctx)
            catalog_by_name = {tool.name: tool for tool in catalog}

            cache_key = tuple(sorted(catalog_by_name))
            cached = transform._derivation_cache.get(cache_key)
            if cached is None:
                reachable: list[tuple[str, Any]] = [(name, transform._return_types.get(name)) for name in cache_key]
                models: list[type] = []
                for _, return_type in reachable:
                    collect_models(return_type, models)
                cached = (
                    generate_stubs(reachable),
                    [dataclass_mirror(model) for model in models],
                    dict(reachable),
                )
                transform._derivation_cache[cache_key] = cached
            stubs, registry, return_type_by_name = cached

            async def call_tool(tool_name: str, params: dict[str, Any]) -> Any:
                tool = catalog_by_name.get(tool_name)
                if tool is None:
                    raise NotFoundError(f"Unknown tool: {tool_name}")
                result = await ctx.fastmcp.call_tool(tool.name, params)
                payload = unwrap_tool_result(result)
                return marshal_result(payload, return_type_by_name.get(tool_name))

            output = await transform._provider.run(
                code,
                external_functions={"call_tool": call_tool},
                stubs=stubs,
                dataclass_registry=registry,
                ctx=ctx,
            )
            # The execute output faces the LLM — render it for the `llm`
            # consumer by value-driven inference (it has no static type):
            # TSV in `content`, the equivalent JSON in `structuredContent`.
            rendered = render_execute(output)
            structured = rendered.structured
            if isinstance(structured, dict):
                return ToolResult(content=rendered.text, structured_content=structured)
            return ToolResult(
                content=rendered.text,
                structured_content={"result": structured},
                meta={"fastmcp": {"wrap_result": True}},
            )

        return Tool.from_function(
            fn=execute,
            name=self.execute_tool_name,
            description=self._build_execute_description(),
        )


def build_code_mode_transform(
    *,
    allow_destructive: bool = False,
    return_types: dict[str, Any] | None = None,
) -> A2kitCodeMode:
    """Build the `A2kitCodeMode` transform. `allow_destructive` (operator-only,
    default False) gates `destructive` tools out of the sandbox catalog;
    `return_types` maps tool name → return annotation for stub generation.
    """
    _require_monty()
    return A2kitCodeMode(allow_destructive=allow_destructive, return_types=return_types)


async def run_code(app: object, code: str, *, allow_destructive: bool = False) -> object:
    """Run `code` in the sandbox against `app`'s tools — the shared engine
    behind both the MCP `execute` tool and the CLI `code` subcommand.
    """
    from fastmcp import Client

    from a2kit.packages.mcp.server import build_mcp_server

    server = build_mcp_server(app, code_mode=True, code_mode_allow_destructive=allow_destructive)
    async with Client(server) as client:
        result = await client.call_tool("execute", {"code": code})
    return result.data if result.data is not None else result.content


__all__ = [
    "A2kitCodeMode",
    "A2kitSandboxProvider",
    "build_code_mode_transform",
    "run_code",
]
