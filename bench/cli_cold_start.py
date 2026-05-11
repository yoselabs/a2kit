"""Cold-start CLI invocation benchmark.

Measures the wall-clock cost of invoking an a2kit-built CLI tool from a
fresh Python process. Three signals:

1. ``--help`` exit (no tool invocation; pure import + click setup).
2. Smallest possible tool call (one-line return, no DI).
3. Tool with DI resolution (singleton state, one provider, no connection).

Each is run N times; the script reports median + min for each signal,
plus an ``import a2kit`` baseline measured via ``-c 'import a2kit'``.

Run::

    uv run python bench/cli_cold_start.py
    uv run python bench/cli_cold_start.py --repeats 20
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_BENCH_APP = '''
import a2kit


class _State:
    def __init__(self) -> None:
        self.label = "warmed"


def _build_state() -> _State:
    return _State()


class Demo(a2kit.Router):
    name = "demo"

    @a2kit.read("ping")
    async def ping(self) -> dict:
        """No-DI tool — return a constant dict."""
        return {"ok": True}

    @a2kit.read("hello")
    async def hello(self, *, state: _State) -> dict:
        """DI-resolved tool — touches the singleton."""
        return {"label": state.label}


app = a2kit.App("bench")
app.add_router(Demo())
app.singleton(_State, _build_state)


def main() -> None:
    a2kit.run(app)


if __name__ == "__main__":
    main()
'''


def _write_bench_app(tmp: Path) -> Path:
    path = tmp / "bench_app.py"
    path.write_text(_BENCH_APP)
    return path


def _run(cmd: list[str]) -> float:
    """Time one subprocess run; return wall seconds. Raises on non-zero exit."""
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, check=False)
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        sys.stderr.write(f"FAIL ({proc.returncode}): {' '.join(cmd)}\n")
        sys.stderr.write(proc.stderr.decode("utf-8", errors="replace"))
        raise RuntimeError("subprocess failed")
    return dt


def _stats(samples: list[float]) -> dict[str, float]:
    return {
        "min_ms": min(samples) * 1000,
        "median_ms": statistics.median(samples) * 1000,
        "p90_ms": (sorted(samples)[int(len(samples) * 0.9)] if len(samples) >= 10 else max(samples)) * 1000,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    args = parser.parse_args()

    py = sys.executable
    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        bench_app = _write_bench_app(tmpdir)

        scenarios: dict[str, list[str]] = {
            "py_baseline": [py, "-c", "pass"],
            "import_a2kit": [py, "-c", "import a2kit"],
            "cli_help": [py, str(bench_app), "--help"],
            "cli_ping_json": [py, str(bench_app), "demo", "ping", "--format", "json"],
            "cli_hello_di_json": [py, str(bench_app), "demo", "hello", "--format", "json"],
            "cli_ping_schema": [py, str(bench_app), "demo", "ping", "--schema"],
        }

        print(f"# a2kit CLI cold-start benchmark (repeats={args.repeats}, warmup={args.warmup})")
        print(f"# python: {py}")
        print(f"# bench app: {bench_app}")
        print()
        header = f"{'scenario':<22} {'min_ms':>10} {'median_ms':>12} {'p90_ms':>10}"
        print(header)
        print("-" * len(header))

        for name, cmd in scenarios.items():
            for _ in range(args.warmup):
                _run(cmd)
            samples = [_run(cmd) for _ in range(args.repeats)]
            s = _stats(samples)
            print(f"{name:<22} {s['min_ms']:>10.1f} {s['median_ms']:>12.1f} {s['p90_ms']:>10.1f}")


if __name__ == "__main__":
    main()
