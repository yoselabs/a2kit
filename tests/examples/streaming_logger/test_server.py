"""End-to-end CLI invocation: ctx.info lines hit stderr, return value hits stdout."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from a2kit.packages.cli.builder import build_full_cli
from examples.streaming_logger.server import app


def _write_csv(tmp_path: Path) -> Path:
    p = tmp_path / "rows.csv"
    p.write_text("id,name\n1,a\n2,b\n3,c\n4,d\n5,e\n", encoding="utf-8")
    return p


def test_import_csv_streams_logs_to_stderr_and_returns_dict(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path)
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        [
            "tasks",
            "import_csv",
            "--file",
            str(csv),
            "--batch-size",
            "2",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output

    # stdout = final formatted return value
    payload = json.loads(result.stdout.strip())
    assert payload == {"imported": 5, "batches": 3}

    # stderr = streamed ctx.info / report_progress lines.
    # New format: [ +s.mmm LEVEL   ] msg key=val (relative elapsed timestamps).
    err = result.stderr
    assert "INFO    ] starting import" in err
    assert "INFO    ] loaded rows" in err
    assert "INFO    ] processing batch" in err
    assert "progress] " in err
    assert "INFO    ] done" in err


def test_long_running_emits_warning_then_error(tmp_path: Path) -> None:
    """``attempts > fail_after`` path: ctx.warning per retry, ctx.error before raise."""
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        ["tasks", "long_running", "--attempts", "8", "--fail-after", "3"],
    )
    # The tool raises after exhausting retries — CLI exits non-zero.
    assert result.exit_code != 0
    err = result.stderr
    assert "WARN    ] transient failure" in err
    assert "ERROR   ] giving up" in err


def test_import_csv_with_reports_emits_event_and_report_lines(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path)
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        [
            "tasks",
            "import_csv_with_reports",
            "--file",
            str(csv),
            "--batch-size",
            "2",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    err = result.stderr
    # Narrative events fire at start + end.
    assert "event   ]" in err
    assert "ImportStarted" in err
    assert "ImportComplete" in err
    # Reports fire per-batch with the BatchReport class name.
    assert "report  ]" in err
    assert "BatchReport" in err
    assert "batch=0" in err


def test_no_reports_flag_silences_reports_but_not_events(tmp_path: Path) -> None:
    csv = _write_csv(tmp_path)
    cli = build_full_cli(app)
    result = CliRunner().invoke(
        cli,
        [
            "--no-reports",
            "tasks",
            "import_csv_with_reports",
            "--file",
            str(csv),
            "--batch-size",
            "2",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    err = result.stderr
    # Events still fire.
    assert "ImportStarted" in err
    # Reports do not.
    assert "BatchReport" not in err


def test_quick_status_has_no_log_lines(tmp_path: Path) -> None:
    cli = build_full_cli(app)
    result = CliRunner().invoke(cli, ["tasks", "quick_status", "--format", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout.strip()) == {"status": "ok"}
    # No log levels emitted for a tool that opts out.
    assert "INFO    ]" not in result.stderr
    assert "WARN    ]" not in result.stderr
