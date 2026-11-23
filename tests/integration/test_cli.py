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


# ------------------------------------------------------------------ Week 2: replay
EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "fault_plans"


def _record(tmp_path: Path, *args: str) -> str:
    result = runner.invoke(app, ["run", *args, "--runs-dir", str(tmp_path)], terminal_width=200)
    match = RUN_ID.search(result.output)
    assert match is not None, result.output
    return match.group(1)


def test_replay_verified(tmp_path: Path) -> None:
    run_id = _record(tmp_path, "T1")
    result = runner.invoke(app, ["replay", run_id, "--runs-dir", str(tmp_path)], terminal_width=200)
    assert result.exit_code == 0, result.output
    for text in ("VERIFIED", "integrity", "no live policy calls", "final state hash equal"):
        assert text in result.output


def test_run_with_fault_plan_then_replay(tmp_path: Path) -> None:
    plan = str(EXAMPLES / "lost_ack_refund.json")
    result = runner.invoke(
        app, ["run", "T1", "--fault-plan", plan, "--runs-dir", str(tmp_path)], terminal_width=200
    )
    assert result.exit_code == 1 and "NO_DUPLICATE_REFUND" in result.output
    match = RUN_ID.search(result.output)
    assert match is not None
    run_id = match.group(1)
    assert (tmp_path / run_id / "fault_plan.json").is_file()
    replay = runner.invoke(
        app, ["replay", run_id, "--runs-dir", str(tmp_path), "--save"], terminal_width=200
    )
    assert replay.exit_code == 0 and "VERIFIED" in replay.output
    assert len(JsonlTraceStore(tmp_path).list_run_ids()) == 2  # original + saved replay


def test_invalid_fault_plan_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"plan_id": "x", "faults": [{"fault_id": "f", "operator": "NOPE", '
        '"stage": "POST_EXECUTION", "trigger": {"boundary": "TOOL", '
        '"name": "get_order", "occurrence": 1}}]}'
    )
    result = runner.invoke(app, ["run", "T1", "--fault-plan", str(bad), "--no-save"])
    assert result.exit_code == 2 and "invalid fault plan" in result.output


def test_replay_config_mismatch_exit_code(tmp_path: Path) -> None:
    run_id = _record(tmp_path, "T1", "--policy", "v1")
    result = runner.invoke(
        app, ["replay", run_id, "--policy", "v2", "--runs-dir", str(tmp_path)], terminal_width=200
    )
    assert result.exit_code == 3 and "CONFIG_MISMATCH" in result.output


def test_replay_corrupted_cassette_exit_code(tmp_path: Path) -> None:
    run_id = _record(tmp_path, "T1")
    path = tmp_path / run_id / "events.jsonl"
    lines = path.read_text().splitlines()
    lines[2] = lines[2].replace('"customer_id":"C1"', '"customer_id":"C2"', 1)
    path.write_text("\n".join(lines) + "\n")
    result = runner.invoke(app, ["replay", run_id, "--runs-dir", str(tmp_path)], terminal_width=200)
    assert result.exit_code == 4 and "INTEGRITY_ERROR" in result.output


def test_replay_missing_run(tmp_path: Path) -> None:
    result = runner.invoke(app, ["replay", "run-missing", "--runs-dir", str(tmp_path)])
    assert result.exit_code == 2


def test_replay_diverged_exit_code_and_details(tmp_path: Path) -> None:
    from agenttrace.env.support.scenario import load_scenario
    from agenttrace.runner import record_scenario
    from tests.replay_helpers import map_event, revalidated, tool_seqs

    original = record_scenario(load_scenario("T1"))
    seq = tool_seqs(original, "get_order")[0]
    request = {"tool": "get_order", "args": {"order_id": "O9"}}
    tampered = map_event(original, seq, lambda e: revalidated(e, request=request))
    JsonlTraceStore(tmp_path).save(tampered)  # self-consistent: passes integrity checks
    result = runner.invoke(
        app, ["replay", tampered.header.run_id, "--runs-dir", str(tmp_path)], terminal_width=200
    )
    assert result.exit_code == 1, result.output
    assert "DIVERGED" in result.output and f"REQUEST at seq {seq}" in result.output
