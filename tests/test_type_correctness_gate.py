"""Hard gate budget: `# ty: ignore` count.

The `ty check src/` invocation itself is gated by `make lint`, not pytest —
running ty inside the test suite duplicates the lint step and slows feedback.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ty_ignore_count() -> int:
    out = subprocess.run(  # noqa: S603
        ["/usr/bin/grep", "-rE", "# ty: ignore", str(ROOT / "src" / "a2kit")],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode not in (0, 1):
        raise RuntimeError(out.stderr)
    return len([line for line in out.stdout.splitlines() if line.strip()])


def test_ty_ignore_count_under_budget() -> None:
    assert _ty_ignore_count() <= 10, "Spec budget for `# ty: ignore` is ≤ 10"
