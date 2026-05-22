"""Permanent eval fixture — code-mode correctness against real models.

Promoted from `scripts/eval_codemode_correctness.py` (spike F7). Unlike the
spike, this drives the **real** a2kit machinery end to end: a real `App`,
`build_mcp_server(code_mode=True)`, the real `A2kitCodeMode` `execute` tool
with the shipped `EXECUTE_DESCRIPTION`, real `generate_stubs`, the real
`A2kitSandboxProvider` type-checker, and real dataclass marshalling. So it
is a true regression gate: it fails if the `execute` description, stub
generation, or output rendering degrades, or when a new model ships.

It is NOT part of `make test` — it shells out to the `claude` CLI (one
subprocess per task per model) and costs tokens. Run it deliberately:

    make eval                 # full panel
    uv run python evals/codemode_correctness.py --smoke   # harness only, no models

`--smoke` builds the server and exercises `get_schema` / a hand-written
solution so the harness itself can be checked without spending tokens.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import textwrap
from typing import Any

from pydantic import BaseModel

import a2kit
from a2kit.packages.codemode.runtime import EXECUTE_DESCRIPTION
from a2kit.packages.formatter import Page
from a2kit.packages.mcp import build_mcp_server

# Wider model panel than the spike (haiku + sonnet). Override with
# `A2KIT_EVAL_MODELS=claude-opus-4-7,claude-sonnet-4-6`.
MODELS = os.environ.get("A2KIT_EVAL_MODELS", "claude-haiku-4-5,claude-sonnet-4-6").split(",")
REPEATS = int(os.environ.get("A2KIT_EVAL_REPEATS", "3"))


# --- the system under test: a real a2kit app -------------------------------


class Task(BaseModel):
    id: int
    title: str
    status: str
    owner_id: int


class User(BaseModel):
    id: int
    name: str


_TASKS = [Task(id=i, title=f"task-{i}", status="done" if i % 2 == 0 else "open", owner_id=i % 3) for i in range(7)]
_USERS = {0: "alice", 1: "bob", 2: "carol"}
_PAGE_SIZE = 3


class EvalRouter(a2kit.Router):
    """Tools spanning pagination, a scalar return, a join, and an error path."""

    slug = "eval"

    @a2kit.read()
    async def list_tasks(self, *, cursor: str | None = None) -> Page[Task]:
        """One page of tasks (page size 3); pass next_cursor back as cursor."""
        start = int(cursor) if cursor else 0
        end = start + _PAGE_SIZE
        nxt = str(end) if end < len(_TASKS) else None
        return Page[Task](items=_TASKS[start:end], next_cursor=nxt)

    @a2kit.read()
    async def count_tasks(self) -> int:
        """Total number of tasks."""
        return len(_TASKS)

    @a2kit.read()
    async def get_user(self, *, user_id: int) -> User:
        """The user with the given id."""
        return User(id=user_id, name=_USERS[user_id])

    @a2kit.read()
    async def boom(self) -> dict[str, str]:
        """Always raises — exercises the sandbox error path."""
        raise RuntimeError("eval: intentional failure")

    tools = (list_tasks, count_tasks, get_user, boom)


def _build_app() -> a2kit.App:
    app = a2kit.App("codemode-eval")
    app.add_router(EvalRouter())
    return app


# --- eval tasks ------------------------------------------------------------


def _sorted(v: object) -> object:
    return sorted(v) if isinstance(v, list) else v


# (description, checker). Expanded over the spike: adds a multi-tool join
# and an error path.
TASKS: list[tuple[str, Any]] = [
    ("Return the title of the task whose id is 2.", lambda r: r == "task-2"),
    (
        "Return a list of the titles of every task whose status is 'done'.",
        lambda r: _sorted(r) == ["task-0", "task-2", "task-4", "task-6"],
    ),
    (
        "Paginate through every page of list_tasks and return the total count of tasks you collected.",
        lambda r: r == 7,
    ),
    ("Return the total number of tasks using the count tool.", lambda r: r == 7),
    (
        "Paginate through all tasks and return every task title, sorted alphabetically.",
        lambda r: r == [f"task-{i}" for i in range(7)],
    ),
    (
        "Paginate through all tasks and return a dict mapping each status to the number of tasks with that status.",
        lambda r: r == {"done": 4, "open": 3},
    ),
    (
        # multi-tool join
        "Find the task with id 0, then call get_user with its owner_id and return that user's name.",
        lambda r: r == "alice",
    ),
    (
        # error path
        "Call the boom tool. It raises an error — catch the exception and return the string 'caught'.",
        lambda r: r == "caught",
    ),
]


# --- model + MCP drivers ---------------------------------------------------


def _call_claude(prompt: str, model: str) -> str:
    proc = subprocess.run(
        ["claude", "-p", prompt, "--model", model],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return proc.stdout.strip()


def _extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip()


def _build_prompt(schema: str, task: str) -> str:
    return (
        "You are writing Python for a sandboxed code-execution tool.\n\n"
        f"{EXECUTE_DESCRIPTION}\n\n"
        f"Available tools (from get_schema):\n{schema}\n\n"
        f"Task: {task}\n\n"
        "Output ONLY the Python code, no explanation."
    )


def _answer(result: object) -> object:
    """Pull the answer out of an execute ToolResult, unwrapping {'result': ...}."""
    structured = getattr(result, "structured_content", None)
    if structured is None:
        structured = getattr(result, "data", None)
    if isinstance(structured, dict) and set(structured) == {"result"}:
        return structured["result"]
    return structured


def _sampling_handler(model: str):
    """A FastMCP client sampling handler — routes the type-check retry's
    `ctx.sample` to the same model via `claude -p`.
    """

    def handler(messages: Any, params: object, context: object) -> str:
        parts: list[str] = []
        for msg in messages:  # type: ignore[attr-defined]
            content = getattr(msg, "content", None)
            text = getattr(content, "text", None)
            if text:
                parts.append(text)
        return _extract_code(_call_claude("\n".join(parts), model))

    return handler


async def _eval_model(model: str) -> tuple[int, int]:
    from fastmcp import Client

    app = _build_app()
    server = build_mcp_server(app, code_mode=True)
    correct = total = 0

    print(f"\n### {model}")
    async with Client(server, sampling_handler=_sampling_handler(model)) as client:
        schema_result = await client.call_tool(
            "get_schema",
            {"tools": ["list_tasks", "count_tasks", "get_user", "boom"], "detail": "full"},
        )
        schema = "\n".join(getattr(b, "text", "") for b in schema_result.content)

        for i, (task, check) in enumerate(TASKS, 1):
            hits = 0
            worst = ""
            for _ in range(REPEATS):
                total += 1
                code = _extract_code(_call_claude(_build_prompt(schema, task), model))
                ok = False
                try:
                    result = await client.call_tool("execute", {"code": code})
                    ok = bool(check(_answer(result)))  # type: ignore[operator]
                except Exception:  # eval: any failure is incorrect
                    ok = False
                hits += ok
                correct += ok
                if not ok:
                    worst = code
            flag = "ok" if hits == REPEATS else ("VARIES" if hits else "FAIL")
            print(f"  T{i} [{flag:6s}] {hits}/{REPEATS}")
            if hits < REPEATS and worst:
                print(textwrap.indent(worst[:300], "       | "))

    print(f"  => {model}: {correct}/{total}")
    return correct, total


async def _smoke() -> int:
    """Harness check — build the server, call get_schema, run a hand-written
    solution through the real execute tool. No models, no tokens.
    """
    from fastmcp import Client

    app = _build_app()
    server = build_mcp_server(app, code_mode=True)
    async with Client(server) as client:
        schema_result = await client.call_tool("get_schema", {"tools": ["list_tasks"], "detail": "full"})
        schema = "\n".join(getattr(b, "text", "") for b in schema_result.content)
        assert "list_tasks" in schema, "get_schema produced no schema text"

        code = 'page = await call_tool("list_tasks", {})\n[t.title for t in page.items]'
        result = await client.call_tool("execute", {"code": code})
        answer = _answer(result)
        assert answer == ["task-0", "task-1", "task-2"], f"unexpected: {answer!r}"
    print("smoke: harness OK — server builds, get_schema + execute round-trip works")
    return 0


async def _main() -> int:
    if "--smoke" in sys.argv:
        return await _smoke()
    print(f"Code-mode correctness eval — {REPEATS}x repeats, models: {', '.join(MODELS)}")
    summary: dict[str, tuple[int, int]] = {}
    for model in MODELS:
        summary[model] = await _eval_model(model)
    print("\n## Summary")
    for model, (c, t) in summary.items():
        print(f"  {model:24s} {c}/{t}")
    return 0 if all(c == t for c, t in summary.values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
