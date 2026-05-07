"""List-view triad — `filter`, `fields`, `pagination` x `Local` / `Passthrough`.

Three orthogonal concerns, two execution modes each. The kit keeps the schema
shape consistent across all six combinations so agents always know how to
call a list-shaped tool.

- **`Local`** — kit handles the concern post-call. Tool function doesn't see
  the param. CEL filter runs on returned rows; field projection picks dict
  keys; pagination slices the list and emits an opaque cursor.
- **`Passthrough`** — kit declares the param to FastMCP / the agent and
  threads it to the tool body. The tool compiles the param to whatever
  upstream protocol it speaks (JQL, SQL `WHERE`, REST query, cursor token).

Mix and match — Local where the kit is fine (Reddit JSON, in-memory data),
Passthrough where the upstream has its own query language (Jira JQL,
PostgreSQL, paginated REST).

Run: `uv run python examples/03_list_view.py`
"""

from __future__ import annotations

import a2kit
from a2kit import Local, Page, Passthrough

_ISSUES = [
    {"id": 1, "title": "Login broken", "status": "open", "priority": "P1"},
    {"id": 2, "title": "Slow dashboard", "status": "open", "priority": "P3"},
    {"id": 3, "title": "Spelling fix", "status": "closed", "priority": "P4"},
    {"id": 4, "title": "Race condition", "status": "open", "priority": "P1"},
]


# --- All-Local: kit handles everything --------------------------------------- #


@a2kit.tool(filter=Local, fields=Local, pagination=Local)
def list_issues_local() -> list[dict]:
    """Agent passes filter / fields / limit / cursor; kit applies all of them."""
    return _ISSUES


# --- All-Passthrough: tool handles everything (e.g. Jira) -------------------- #


@a2kit.tool(filter=Passthrough, fields=Passthrough, pagination=Passthrough)
def list_issues_jira(
    filter: str = "",  # noqa: A002 — agent-facing name
    fields: list[str] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> Page[dict]:
    """Tool body compiles `filter` to JQL, `fields` to ?fields=, `cursor` to startAt."""
    # Real impl would call jira.search(jql=_compile_to_jql(filter), ...).
    return Page(
        items=[i for i in _ISSUES if not filter or ("open" in filter and i["status"] == "open")],
        next_cursor="upstream-page-2",
    )


# --- Mixed: pagination upstream, filter local ------------------------------- #


@a2kit.tool(filter=Local, pagination=Passthrough)
def list_issues_mixed(limit: int = 50, cursor: str | None = None) -> Page[dict]:
    """Upstream paginates (e.g. Reddit `?after=`); kit filters within the page."""
    return Page(items=_ISSUES, next_cursor="next")


def main() -> None:
    print("--- all-Local: kit handles filter + fields + paginate ---")
    out = list_issues_local(filter="status == 'open'", fields=["id", "title"], limit=2)  # type: ignore[call-arg]
    print(f"format={out.format}, next_cursor={out.next_cursor!r}")
    print(out.data)
    print()

    print("--- all-Passthrough: tool returns Page[dict] ---")
    out = list_issues_jira(filter="status == 'open'")  # type: ignore[call-arg]
    print(f"format={out.format}, next_cursor={out.next_cursor!r}")
    print(out.data)
    print()

    print("--- mixed: upstream paginates, kit filters within page ---")
    out = list_issues_mixed(filter="priority == 'P1'", limit=10)  # type: ignore[call-arg]
    print(f"format={out.format}, next_cursor={out.next_cursor!r}")
    print(out.data)


if __name__ == "__main__":
    main()
