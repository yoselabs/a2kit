"""``ctx.elicit`` portability demo.

A single tool that asks the agent (or CLI user) for a username via
``ctx.elicit("Pick a username", response_type=str)`` and echoes it back.

Run as a CLI (stdin provides the value)::

    echo "alice" | python -m examples.elicitation.server users greet

Run as an MCP server::

    python -m examples.elicitation.server serve
"""

from __future__ import annotations

from fastmcp.server.elicitation import AcceptedElicitation

import a2kit


class UsersRouter(a2kit.Router):
    @a2kit.read(idempotent=True, title="Greet User")
    async def greet(self, *, ctx: a2kit.ToolContext) -> dict[str, str]:
        """Ask for a username and respond with a greeting.

        Demonstrates that the same code works on both transports:
        on MCP the server forwards the elicitation to the client;
        on CLI the :class:`a2kit.packages.cli.context.StderrToolContext`
        stub reads from stdin.
        """
        result = await ctx.elicit("Pick a username", response_type=str)
        if not isinstance(result, AcceptedElicitation):
            return {"status": "no name", "kind": result.action}
        return {"status": "ok", "greeting": f"hello {result.data}"}


app = a2kit.App("elicitation-demo")
app.add_router(UsersRouter())


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
