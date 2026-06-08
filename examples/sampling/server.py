"""``ctx.sample`` portability demo — asymmetric across transports.

LLM sampling has no client-side facility on the CLI: the stub raises
:class:`a2kit.packages.cli.context.MCPOnlyError`. Over MCP, the server
forwards the sampling request to the client which holds the LLM.

Run as an MCP server::

    python -m examples.sampling.server serve

CLI invocation will fail with a clear error message::

    python -m examples.sampling.server text summarize --text "..."
"""

from __future__ import annotations

from fastmcp import Context as FastMCPContext

import a2kit


class TextRouter(a2kit.Router):
    slug = "text"

    @a2kit.read(open_world=True, title="Summarize via LLM Sampling")
    async def summarize(self, *, ctx: FastMCPContext, text: str) -> dict[str, str]:
        """Summarize ``text`` by asking the MCP client to sample its LLM.

        On MCP transport this returns the LLM's summary string. On CLI
        transport this raises ``MCPOnlyError`` — there's no LLM available
        client-side to forward the sample request to.
        """
        result = await ctx.sample(f"Summarize in one sentence:\n\n{text}")
        # ``ctx.sample`` returns a ``SamplingResult`` on MCP — extract its text.
        summary = getattr(result, "text", None) or getattr(result, "result", None) or str(result)
        return {"summary": summary}


class SamplingApp(a2kit.App):
    name = "sampling-demo"
    routers = (TextRouter,)


app = SamplingApp()


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
