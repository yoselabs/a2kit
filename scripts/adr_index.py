#!/usr/bin/env python3
"""Generate docs/adr/INDEX.md from the YAML frontmatter of every ADR.

The INDEX is the agent-loadable entry point: a condensed table of every
recorded decision, small enough to drop into an LLM context window. Agents
follow links from the INDEX to load full ADR bodies only when needed.

Run modes
---------
    uv run python scripts/adr_index.py            # regenerate INDEX.md
    uv run python scripts/adr_index.py --check    # nonzero if invalid or stale

The --check mode is wired into pre-commit so a committer cannot land an
ADR change without (a) valid frontmatter per docs/adr/schema.json and
(b) the regenerated INDEX in the same commit.

Implementation note: this script is thin orchestration over three mature
libraries — python-frontmatter (YAML frontmatter parsing), jsonschema
(validating frontmatter against docs/adr/schema.json), and jinja2
(rendering the INDEX template). The only project-specific logic is the
Y-statement extraction regex and the INDEX template. No bespoke YAML,
JSON Schema, or markdown parsing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import frontmatter
from jinja2 import Environment
from jsonschema import Draft202012Validator

ADR_DIR = Path(__file__).resolve().parent.parent / "docs" / "adr"
INDEX_PATH = ADR_DIR / "INDEX.md"
SCHEMA_PATH = ADR_DIR / "schema.json"
ADR_FILENAME_RE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")

INDEX_TEMPLATE = """# ADR Index

Auto-generated from YAML frontmatter in `docs/adr/NNNN-*.md` by
`scripts/adr_index.py`. Do not edit by hand — regenerate with
`make adr-index` (or any commit will trigger the pre-commit hook).

This file is the agent-loadable entry point for the architecture
decision log. Load this once to see every recorded decision; follow
the links to read full bodies only when needed.

## Active decisions

| ID | Status | Title | Tags | Y-statement |
|----|--------|-------|------|-------------|
{%- for adr in active %}
| [{{ adr.id }}]({{ adr.filename }}) | {{ adr.status }} | {{ adr.title }} | {{ adr.tags | join(", ") }} | {{ adr.summary }} |
{%- endfor %}
{% if superseded %}
## Superseded

| ID | Title | Superseded by |
|----|-------|---------------|
{%- for adr in superseded %}
| [{{ adr.id }}]({{ adr.filename }}) | {{ adr.title }} | [{{ adr.superseded_by }}]({{ adr.superseded_by_filename }}) |
{%- endfor %}
{% endif %}
{% if deprecated %}
## Deprecated

| ID | Title | Last reviewed |
|----|-------|---------------|
{%- for adr in deprecated %}
| [{{ adr.id }}]({{ adr.filename }}) | {{ adr.title }} | {{ adr.last_reviewed }} |
{%- endfor %}
{% endif %}
"""


def extract_summary(body: str) -> str:
    """Extract the Y-statement / one-paragraph summary from an ADR body.

    Looks for the first paragraph under a ``## Summary`` section. Falls
    back to the first non-header paragraph if no Summary section exists.
    Newlines within the paragraph are collapsed to single spaces so the
    summary fits in a markdown table cell. Pipes are escaped.
    """

    summary_match = re.search(
        r"^##\s+Summary\s*\n+([^#].*?)(?=\n\n|\n##|\Z)",
        body,
        flags=re.MULTILINE | re.DOTALL,
    )
    if summary_match:
        paragraph = summary_match.group(1)
    else:
        para_match = re.search(r"(?:\A|\n\n)([^#\s].+?)(?=\n\n|\Z)", body, flags=re.DOTALL)
        paragraph = para_match.group(1) if para_match else ""

    collapsed = " ".join(paragraph.split())
    return collapsed.replace("|", "\\|")


def _normalize_for_validation(metadata: dict[str, Any]) -> dict[str, Any]:
    """Coerce YAML-parsed values to the types the JSON Schema expects.

    PyYAML decodes ``date: 2026-05-18`` to ``datetime.date`` and bare
    numeric ids to ``int``; the schema speaks strings (so an agent can
    grep them uniformly). Coerce here so authors don't have to remember
    to quote everything.
    """

    out = dict(metadata)
    for key in ("date", "last_reviewed"):
        if key in out and not isinstance(out[key], str):
            out[key] = str(out[key])
    if "id" in out and isinstance(out["id"], int):
        out["id"] = f"{out['id']:04d}"
    if out.get("supersedes"):
        out["supersedes"] = [f"{x:04d}" if isinstance(x, int) else x for x in out["supersedes"]]
    if isinstance(out.get("superseded_by"), int):
        out["superseded_by"] = f"{out['superseded_by']:04d}"
    return out


def validate_frontmatter(metadata: dict[str, Any], filename: str, validator: Draft202012Validator) -> list[str]:
    """Run JSON Schema validation; return a list of human-readable errors."""

    errors: list[str] = []
    for err in sorted(validator.iter_errors(metadata), key=lambda e: list(e.absolute_path)):
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"  {filename}: {path}: {err.message}")
    return errors


def load_adrs(adr_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Load all ADR files. Returns (records, validation_errors)."""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        match = ADR_FILENAME_RE.match(path.name)
        if not match:
            continue
        post = frontmatter.load(path)
        fm = _normalize_for_validation(post.metadata)

        file_errors = validate_frontmatter(fm, path.name, validator)
        if fm.get("id") != match.group(1):
            file_errors.append(f"  {path.name}: id field {fm.get('id')!r} does not match filename prefix {match.group(1)!r}")
        if file_errors:
            errors.extend(file_errors)
            continue

        title_line = post.content.split("\n", 1)[0].lstrip("# ").strip()
        title = title_line.removeprefix(f"ADR {fm['id']}: ").strip()
        records.append(
            {
                "id": fm["id"],
                "status": fm["status"],
                "title": title,
                "tags": fm.get("tags", []),
                "supersedes": fm.get("supersedes") or [],
                "superseded_by": fm.get("superseded_by"),
                "date": fm["date"],
                "last_reviewed": fm["last_reviewed"],
                "filename": path.name,
                "summary": extract_summary(post.content),
            }
        )
    return records, errors


def filename_for(adr_id: str, all_records: list[dict[str, Any]]) -> str:
    """Look up the on-disk filename for a referenced ADR id."""

    for r in all_records:
        if r["id"] == adr_id:
            return r["filename"]
    return f"{adr_id}-*.md"


def render(records: list[dict[str, Any]]) -> str:
    """Render the INDEX markdown from the loaded ADR records."""

    active = [r for r in records if r["status"] in ("proposed", "accepted")]
    superseded = [r for r in records if r["status"] == "superseded"]
    deprecated = [r for r in records if r["status"] == "deprecated"]

    for r in superseded:
        r["superseded_by_filename"] = filename_for(r["superseded_by"] or "", records)

    # Output is markdown, not HTML; HTML-escaping `<`, `>`, `&` would corrupt
    # content (e.g. Y-statements containing `<` for type hints). XSS is not a
    # threat model for a static file generator that writes to the repo tree.
    env = Environment(autoescape=False, keep_trailing_newline=True, trim_blocks=False)  # noqa: S701
    template = env.from_string(INDEX_TEMPLATE)
    return template.render(active=active, superseded=superseded, deprecated=deprecated)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit nonzero if frontmatter is invalid OR the on-disk INDEX is stale.",
    )
    args = parser.parse_args()

    records, errors = load_adrs(ADR_DIR)
    if errors:
        sys.stderr.write("ADR frontmatter validation failed:\n")
        sys.stderr.write("\n".join(errors) + "\n")
        sys.stderr.write("See docs/adr/schema.json for the contract.\n")
        return 1

    new_content = render(records)

    if args.check:
        existing = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
        if existing != new_content:
            sys.stderr.write("docs/adr/INDEX.md is stale. Run `make adr-index` and commit the result.\n")
            return 1
        return 0

    INDEX_PATH.write_text(new_content, encoding="utf-8")
    sys.stdout.write(f"Wrote {INDEX_PATH} ({len(records)} ADRs).\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
