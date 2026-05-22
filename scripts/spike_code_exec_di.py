"""Spike: does FastMCP's CodeMode work with a2kit connection-scoped DI tools?

Question under test
-------------------
FastMCP 3.2 ships ``experimental.transforms.CodeMode`` — it collapses the
tool catalog into ``search`` / ``get_schemas`` / ``execute`` and runs
agent-authored Python in a Monty sandbox. Inside the sandbox, the only
callable is ``call_tool(name, params)``, which bridges out via
``ctx.fastmcp.call_tool(...)``.

a2kit tools are not plain functions: each is wrapped by
``_wrap_with_dispatch_hook`` so that, per call, the connections dispatch
hook resolves the wire ``connection: str`` into a typed config and the DI
container resolves request-scoped dependencies (``store: TrackerStore``).

So the unknown is narrow and concrete: when sandboxed code calls
``call_tool("<a2kit tool>", {"connection": "default", ...})``, does the
nested ``ctx.fastmcp.call_tool`` path re-run a2kit's per-call dispatch
hook + DI, or is connection/DI scope lost?

Run: ``uv run python scripts/spike_code_exec_di.py``
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import anyio

_REPO = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="spike-codeexec-"))
_CFG = _TMP / "connections"
_CFG.mkdir(parents=True)
_DB = _TMP / "tracker.jsonl"

# A2KIT_CONFIG_HOME must be set BEFORE importing the tracker example: its
# `install_connections(...)` builds the ConnectionStore at import time and
# captures default_config_dir() then.
os.environ["A2KIT_CONFIG_HOME"] = str(_CFG)
sys.path.insert(0, str(_REPO / "examples"))

from tracker.connection import TrackerConn  # noqa: E402
from tracker.models import Project, Task  # noqa: E402
from tracker.server import app  # noqa: E402
from tracker.store import TrackerStore  # noqa: E402

from a2kit.packages.connections.store import ConnectionStore  # noqa: E402
from a2kit.packages.mcp import build_mcp_server  # noqa: E402

PASS = "[PASS]"  # noqa: S105 -- display marker, not a credential
FAIL = "[FAIL]"
INFO = "[INFO]"


def _seed() -> None:
    """Write a connection record + a tracker DB with two tasks."""
    conn = TrackerConn(key=["default"], db_path=str(_DB))
    TrackerStore(conn).replace(
        [Project(id="p1", name="Spike Project")],
        [
            Task(id="t1", project_id="p1", title="First task"),
            Task(id="t2", project_id="p1", title="Second task"),
        ],
    )
    # save() is async; run it on the loop below instead. Done in main().
    return conn


async def main() -> int:
    from fastmcp import Client
    from fastmcp.experimental.transforms.code_mode import CodeMode

    conn = _seed()
    await ConnectionStore(TrackerConn, config_dir=_CFG).save(conn)
    print(f"{INFO} temp workspace: {_TMP}")

    failures = 0

    # ---- 1. discover real a2kit tool names (pre-transform) ----------------
    server = build_mcp_server(app)
    async with Client(server) as client:
        raw = await client.list_tools()
    raw_names = [t.name for t in raw]
    print(f"{INFO} a2kit tool names: {raw_names}")
    list_tool = next((n for n in raw_names if "list" in n and "task" in n), None)
    get_tool = next((n for n in raw_names if "get" in n and "task" in n), None)
    print(f"{INFO} picked list tool = {list_tool!r}, get tool = {get_tool!r}")
    if list_tool is None:
        print(f"{FAIL} could not find a list-tasks tool — aborting")
        return 1

    # ---- 2. add CodeMode and check the catalog collapses -----------------
    server.add_transform(CodeMode())
    async with Client(server) as client:
        cm_tools = await client.list_tools()
        cm_names = sorted(t.name for t in cm_tools)
        print(f"{INFO} post-CodeMode tools: {cm_names}")
        if "execute" in cm_names and any("search" in n for n in cm_names):
            print(f"{PASS} CodeMode collapsed the catalog to discovery + execute")
        else:
            failures += 1
            print(f"{FAIL} CodeMode did not collapse the catalog as expected")

        # ---- 3. does the search/schema surface expose `connection`? ------
        try:
            sr = await client.call_tool("search", {"query": "tasks", "detail": "full"})
            schema_text = str(sr.data if sr.data is not None else sr.content)
            has_conn = "connection" in schema_text
            verdict = PASS if has_conn else FAIL
            failures += 0 if has_conn else 1
            print(f"{verdict} discovery schema {'exposes' if has_conn else 'does NOT expose'} the `connection` wire param")
        except Exception as exc:  # spike: report, keep going
            failures += 1
            print(f"{FAIL} search call raised: {type(exc).__name__}: {exc}")

        # ---- 4. THE CORE TEST: sandboxed code -> connection-scoped tool --
        code_ok = f'result = await call_tool("{list_tool}", {{"connection": "default"}})\nreturn result\n'
        try:
            res = await client.call_tool("execute", {"code": code_ok})
            payload = res.data if res.data is not None else res.content
            text = str(payload)
            hit = "First task" in text or "Second task" in text
            verdict = PASS if hit else FAIL
            failures += 0 if hit else 1
            print(f"{verdict} sandboxed call_tool() with connection ran the connection-scoped DI tool")
            print(f"{INFO} sandbox received (repr, truncated): {text[:300]!r}")
        except Exception as exc:  # spike: report, keep going
            failures += 1
            print(f"{FAIL} execute(with connection) raised: {type(exc).__name__}: {exc}")

        # ---- 5. failure mode: sandboxed call WITHOUT connection ----------
        code_no_conn = f'result = await call_tool("{list_tool}", {{}})\nreturn result\n'
        try:
            res = await client.call_tool("execute", {"code": code_no_conn})
            print(f"{INFO} execute(no connection) returned (no raise): {str(res.data if res.data is not None else res.content)[:200]!r}")
        except Exception as exc:  # spike: this raise is expected
            print(f"{INFO} execute(no connection) raised {type(exc).__name__}: {str(exc)[:200]}")

    print()
    if failures:
        print(f"{FAIL} spike finished with {failures} failed check(s)")
    else:
        print(f"{PASS} all spike checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(anyio.run(main))
