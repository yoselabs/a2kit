"""Spike A2: can monty's type checker pre-validate LLM-written sandbox code?

If monty can statically reject `page.titel` (typo) or a wrong access
pattern *before* execution, a2kit can type-check the model's code against
the real tool schemas and feed errors back — a far cheaper and more
reliable correction loop than execute-then-catch. Directly de-risks the
weak-model (Haiku) concern.

Run: uv run python scripts/spike_monty_typecheck.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pydantic_monty


@dataclass
class TaskDC:
    id: int
    title: str
    status: str


# Stub prepended before type-checking: declares the dataclass + the
# external function signature the sandbox code is checked against.
STUBS = """
from dataclasses import dataclass

@dataclass
class TaskDC:
    id: int
    title: str
    status: str

async def fetch() -> TaskDC: ...
"""


def typecheck(label: str, code: str) -> None:
    try:
        pydantic_monty.Monty(code, type_check=True, type_check_stubs=STUBS)
    except pydantic_monty.MontyTypingError as exc:
        msg = str(exc).replace("\n", " ")[:120]
        print(f"  {label:46s} REJECTED -> {msg}")
    except Exception as exc:
        print(f"  {label:46s} OTHER({type(exc).__name__}) -> {str(exc)[:90]}")
    else:
        print(f"  {label:46s} ACCEPTED")


async def runtime_typecheck(label: str, code: str) -> None:
    """Build with type_check, then actually run — confirms accepted code executes."""

    async def fetch():
        return TaskDC(id=1, title="alpha", status="done")

    try:
        monty = pydantic_monty.Monty(code, type_check=True, type_check_stubs=STUBS)
        value = await monty.run_async(external_functions={"fetch": fetch})
    except Exception as exc:
        print(f"  {label:46s} {type(exc).__name__} -> {str(exc)[:80]}")
    else:
        print(f"  {label:46s} RAN -> {value!r}")


async def main() -> None:
    print("monty type-check spike —", pydantic_monty.__version__)

    print("\n=== Static type-check: does monty reject bad field access? ===")
    typecheck("correct  r.title", "r = await fetch()\nr.title")
    typecheck("typo     r.titel", "r = await fetch()\nr.titel")
    typecheck("wrong-pattern  r['title'] on dataclass", "r = await fetch()\nr['title']")
    typecheck("nonexistent  r.description", "r = await fetch()\nr.description")
    typecheck("type misuse  r.id + r.title", "r = await fetch()\nr.id + r.title")

    print("\n=== Accepted code still runs ===")
    await runtime_typecheck("correct  r.title", "r = await fetch()\nr.title")

    print("\ndone.")


if __name__ == "__main__":
    asyncio.run(main())
