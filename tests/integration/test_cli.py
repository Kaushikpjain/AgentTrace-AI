from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from agenttrace.cli import app
from agenttrace.trace.store import JsonlTraceStore

runner = CliRunner()
RUN_ID = re.compile(r"Run id: (run-\S+)")


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0 and "run" in result.output and "show" in result.output


def test_scenarios_lists_templates() -> None:
    result = runner.invoke(app, ["scenarios"])
    assert result.exit_code == 0
    for sid in ("T1", "T2", "T3", "T5", "T6"):
        assert sid in result.output


def test_run_pass_persists_and_show_validates(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "T1", "--runs-dir", str(tmp_path)], terminal_width=200)
    assert result.exit_code == 0, result.output
    assert "PASS" in result.output
    match = RUN_ID.search(result.output)
    assert match is not None
    run_id = match.group(1)
    assert JsonlTraceStore(tmp_path).exists(run_id)

    shown = runner.invoke(app, ["show", run_id, "--runs-dir", str(tmp_path)], terminal_width=200)
    assert shown.exit_code == 0 and "integrity verified" in shown.output


def test_runs_dir_from_environment(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "T2"], env={"ATRACE_RUNS_DIR": str(tmp_path)})
    assert result.exit_code == 0
    assert len(JsonlTraceStore(tmp_path).list_run_ids()) == 1


def test_no_save(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "T3", "--no-save", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 0 and not any(tmp_path.iterdir())


def test_unknown_scenario_and_policy() -> None:
    assert runner.invoke(app, ["run", "T99", "--no-save"]).exit_code == 2
    assert runner.invoke(app, ["run", "T1", "--policy", "v9", "--no-save"]).exit_code == 2


def test_show_reports_corruption(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "T1", "--runs-dir", str(tmp_path)], terminal_width=200)
    match = RUN_ID.search(result.output)
    assert match is not None
    run_id = match.group(1)
    (tmp_path / run_id / "footer.json").unlink()
    shown = runner.invoke(app, ["show", run_id, "--runs-dir", str(tmp_path)])
    assert shown.exit_code == 2 and "IncompleteRecordingError" in shown.output


def test_show_missing_run(tmp_path: Path) -> None:
    assert runner.invoke(app, ["show", "run-missing", "--runs-dir", str(tmp_path)]).exit_code == 2
