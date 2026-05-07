"""Example: --select grammar (CLI parse + a2kit.sel typed builder).

Run: `uv run python examples/select_grammar.py`
"""

from __future__ import annotations

import a2kit
from a2kit import Cap, parse_select, sel


def main() -> None:
    # --- typed builder ------------------------------------------------------
    expr1 = sel("issues") & ~sel(Cap.DESTRUCTIVE)
    print(f"sel('issues') & ~sel(Cap.DESTRUCTIVE) = {expr1.op}")
    print(f"  evaluates against tags={{'issues','read'}}: {expr1.evaluate({'issues', 'read'})}")
    print(f"  evaluates against tags={{'issues','destructive'}}: {expr1.evaluate({'issues', 'destructive'})}")

    expr2 = sel(Cap.READ) | (sel("issues") & sel(Cap.WRITE))
    print(f"\n{expr2.op}: read OR (issues AND write)")

    # --- string parser (CLI surface) ---------------------------------------
    expr3 = parse_select("default and not write and not destructive")
    print(f"\nparsed default-select: {expr3.op}; evaluates {{default,read}} -> {expr3.evaluate({'default', 'read'})}")

    # --- namespaced atoms --------------------------------------------------
    expr4 = parse_select("tool:purge or router:issues or cap:write")
    print(f"\nnamespaced: tool:purge or router:issues or cap:write — children: {len(expr4.children)}")

    # --- back-and-forth: parse + builder produce equivalent shapes ---------
    a = parse_select("a and b")
    b = sel("a") & sel("b")
    print(f"\nparse('a and b').op = {a.op}; sel('a') & sel('b').op = {b.op}")

    # --- a2kit.sel re-exports -----------------------------------------------
    assert a2kit.sel is sel
    print("\nbuilder + parser cover the same grammar.")


if __name__ == "__main__":
    main()
