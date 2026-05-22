"""Spike A: pydantic-monty marshalling boundary for a2kit code mode.

De-risks the dict-vs-dataclass fork and the 40k-element cost worry.

Questions:
  Q1. Access pattern per return type crossing the external-function
      boundary (dict / dataclass / pydantic BaseModel).
  Q2. Does a dataclass give attribute access (`page.items`) in-sandbox?
  Q3. What does the sandbox RETURN value marshal back to in host Python?
  Q4. Cost curve: marshalling N elements (100 .. 40_000) across the boundary.
  Q5. register_dataclass — does it round-trip a real typed instance?
  Q6. Failure-mode legibility — what error on the wrong access pattern?

Run: uv run python scripts/spike_monty_marshalling.py
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pydantic_monty
from pydantic import BaseModel


@dataclass
class Point:
    x: int
    y: int


@dataclass
class TaskDC:
    id: int
    title: str
    status: str


@dataclass
class PageDC:
    items: list
    next_cursor: str | None


class TaskBM(BaseModel):
    id: int
    title: str
    status: str


async def run_code(code: str, ext: dict | None = None, *, registry: list[type] | None = None):
    """Run sandbox code; return (ok, value_or_exc)."""
    monty = pydantic_monty.Monty(code, inputs=None, dataclass_registry=registry)
    try:
        value = await monty.run_async(external_functions=ext or None)
    except Exception as exc:
        return False, exc
    return True, value


def show(label: str, ok: bool, value) -> None:
    kind = type(value).__name__
    if ok:
        rendered = repr(value)
        if len(rendered) > 90:
            rendered = rendered[:90] + "..."
        print(f"  {label:42s} OK    -> ({kind}) {rendered}")
    else:
        print(f"  {label:42s} ERROR -> ({kind}) {value}")


async def q1_q2_access_patterns() -> None:
    print("\n=== Q1/Q2: access patterns per return type ===")

    async def fetch_dict():
        return {"id": 1, "title": "alpha", "status": "done"}

    async def fetch_point():
        return Point(x=3, y=4)

    async def fetch_bm():
        return TaskBM(id=2, title="beta", status="open")

    ok, v = await run_code("r = await fetch()\nr['title']", {"fetch": fetch_dict})
    show("dict   subscript  r['title']", ok, v)
    ok, v = await run_code("r = await fetch()\nr.title", {"fetch": fetch_dict})
    show("dict   attribute  r.title", ok, v)

    ok, v = await run_code("r = await fetch()\nr.x", {"fetch": fetch_point})
    show("dataclass attribute  r.x", ok, v)
    ok, v = await run_code("r = await fetch()\nr['x']", {"fetch": fetch_point})
    show("dataclass subscript  r['x']", ok, v)

    ok, v = await run_code("r = await fetch()\nr.title", {"fetch": fetch_bm})
    show("pydantic  attribute  r.title", ok, v)
    ok, v = await run_code("r = await fetch()\nr['title']", {"fetch": fetch_bm})
    show("pydantic  subscript  r['title']", ok, v)


async def q2_nested_page() -> None:
    print("\n=== Q2: nested  page.items[0].title  (the Page proof case) ===")

    async def fetch_page_dc():
        return PageDC(
            items=[TaskDC(id=i, title=f"t{i}", status="done") for i in range(3)],
            next_cursor="c2",
        )

    async def fetch_page_dict():
        return {
            "items": [{"id": i, "title": f"t{i}", "status": "done"} for i in range(3)],
            "next_cursor": "c2",
        }

    code_dc = "p = await fetch()\nresult = [t.title for t in p.items]\n(result, p.next_cursor)"
    ok, v = await run_code(code_dc, {"fetch": fetch_page_dc})
    show("dataclass  p.items[i].title + p.next_cursor", ok, v)

    code_dict = "p = await fetch()\nresult = [t['title'] for t in p['items']]\n(result, p['next_cursor'])"
    ok, v = await run_code(code_dict, {"fetch": fetch_page_dict})
    show("dict       p['items'][i]['title']", ok, v)


async def q3_return_marshalling() -> None:
    print("\n=== Q3: what the sandbox RETURN value marshals back to ===")

    ok, v = await run_code("{'a': 1, 'b': [1, 2, 3]}")
    show("sandbox returns dict literal", ok, v)
    ok, v = await run_code("[{'id': 1}, {'id': 2}]")
    show("sandbox returns list[dict]", ok, v)

    async def fetch_point():
        return Point(x=9, y=9)

    ok, v = await run_code("r = await fetch()\nr", {"fetch": fetch_point})
    show("sandbox returns dataclass (unregistered)", ok, v)
    print(f"     -> isinstance(result, Point) = {isinstance(v, Point) if ok else 'n/a'}")

    ok, v = await run_code("r = await fetch()\nr", {"fetch": fetch_point}, registry=[Point])
    show("sandbox returns dataclass (REGISTERED)", ok, v)
    print(f"     -> isinstance(result, Point) = {isinstance(v, Point) if ok else 'n/a'}")


async def q4_cost_curve() -> None:
    print("\n=== Q4: cost curve — marshalling N elements across the boundary ===")
    for n in (100, 1_000, 10_000, 40_000):
        rows_dict = [{"id": i, "title": f"t{i}", "status": "done", "score": i * 1.5} for i in range(n)]
        rows_dc = [TaskDC(id=i, title=f"t{i}", status="done") for i in range(n)]

        async def fd(_rows=rows_dict):
            return _rows

        async def fc(_rows=rows_dc):
            return _rows

        t0 = time.perf_counter()
        ok_d, _ = await run_code("r = await fetch()\nlen(r)", {"fetch": fd})
        dt_d = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        ok_c, _ = await run_code("r = await fetch()\nlen(r)", {"fetch": fc})
        dt_c = (time.perf_counter() - t0) * 1000

        # roundtrip: sandbox filters then returns a subset (realistic code-mode use)
        t0 = time.perf_counter()
        ok_f, vf = await run_code("r = await fetch()\n[x for x in r if x['id'] < 5]", {"fetch": fd})
        dt_f = (time.perf_counter() - t0) * 1000

        print(
            f"  N={n:>6}  dict in={dt_d:8.1f}ms ({'ok' if ok_d else 'ERR'})   "
            f"dataclass in={dt_c:8.1f}ms ({'ok' if ok_c else 'ERR'})   "
            f"in+filter+out={dt_f:8.1f}ms ({'ok' if ok_f else 'ERR'})"
        )


async def main() -> None:
    print("pydantic-monty marshalling spike —", pydantic_monty.__version__)
    await q1_q2_access_patterns()
    await q2_nested_page()
    await q3_return_marshalling()
    await q4_cost_curve()
    print("\ndone.")


if __name__ == "__main__":
    asyncio.run(main())
