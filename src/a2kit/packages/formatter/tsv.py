"""TSV encoder using stdlib ``csv`` with tab delimiter, ``\\n`` line
terminator, and ``QUOTE_MINIMAL``.

Header is the caller-supplied ``columns`` list (declared model-field order, not
alphabetical). Each row is dumped via ``model_dump(mode="json")`` when the
input is a pydantic ``BaseModel`` so datetimes / UUIDs / enums become wire
scalars. ``list`` / ``dict`` cell values (only reachable when ``format_hint=
"tsv"`` is explicitly forced on a non-uniform shape) are JSON-blob'd into the
cell.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from pydantic import BaseModel


def _row_to_cells(row: Any, columns: list[str]) -> dict[str, Any]:
    if isinstance(row, BaseModel):
        dumped = row.model_dump(mode="json")
    elif isinstance(row, dict):
        dumped = row
    else:
        msg = f"encode_tsv expected BaseModel or dict rows, got {type(row).__name__}"
        raise TypeError(msg)

    return {
        col: (
            json.dumps(dumped[col], separators=(",", ":"), ensure_ascii=False)
            if isinstance(dumped.get(col), (list, dict))
            else (dumped[col] if dumped.get(col) is not None else "")
        )
        for col in columns
        if col in dumped
    }


def encode_tsv(rows: list[Any], *, columns: list[str]) -> str:
    """Encode ``rows`` as TSV with ``columns`` as the header.

    ``rows`` items may be pydantic ``BaseModel`` instances or plain dicts.
    ``columns`` SHOULD come from ``Model.model_fields.keys()`` (declared order)
    when the caller is type-driven; alphabetical sorting would defeat the
    point.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=columns,
        delimiter="\t",
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(_row_to_cells(row, columns))
    return buf.getvalue()
