"""Post-freeze held-out safeguards (ADR-026). Never executes a held-out benchmark case.

Git state is mocked; the "test split" runs below use *development* instances relabelled as a
temporary synthetic test split, so no held-out instance is recorded or evaluated.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
import typer

from agenttrace.bench import heldout
from agenttrace.bench.evaluate import evaluate_instance, evaluate_split, record_instance
from agenttrace.bench.heldout import (
    FreezeRecord,
    HeldOutAccessError,
    HeldOutAuthorization,
    authorize_test_split,
    read_log,
    require_authorization,
)
from agenttrace.bench.heldout import test_split_guard as split_guard
from agenttrace.bench.io import DEFAULT_DIR, load_instances, load_labels
from agenttrace.bench.run import run_benchmark
from agenttrace.runner import support_replay_context
from agenttrace.trace.fingerprint import fingerprint

REPO = Path(__file__).resolve().parents[2]
SHA = "a" * 40
OTHER = "b" * 40
FP = "sha256:" + "1" * 64
KNOWN = {"freeze-x": FreezeRecord(commit=SHA, test_config_fp=FP)}


def fake_git(
    *,
    status: str | None = "",
    head: str | None = SHA,
    tagged: str | None = SHA,
    kind: str | None = "tag",
    message: str = "",
) -> Any:
    def git(args: Sequence[str]) -> str | None:
        args = list(args)
        if args[0] == "status":
            return status
        if args == ["rev-parse", "HEAD"]:
            return head
        if args[0] == "cat-file":
            return kind
        if args[0] == "rev-parse":
            return tagged
        if args[0] == "tag":
            return message
        raise AssertionError(args)

    return git


def problems(tmp_path: Path, **overrides: Any) -> list[str]:
    official = tmp_path / "official"
    kwargs: dict[str, Any] = {
        "confirmed": True,
        "approved_commit": SHA,
        "config_fp": FP,
        "out_dir": official,
        "official_dir": official,
        "log_path": tmp_path / "TEST_RUNS.log",
        "tag": "freeze-x",
        "git": fake_git(),
        "known": KNOWN,
    }
    kwargs.update(overrides)
    return split_guard(**kwargs)


def has(found: list[str], text: str) -> bool:
    return any(text in p for p in found)


# ------------------------------------------------------------------ guard conditions
def test_guard_allows_only_the_fully_verified_state(tmp_path: Path) -> None:
    assert problems(tmp_path) == []


def test_guard_requires_confirmation_and_explicit_full_commit(tmp_path: Path) -> None:
    assert has(problems(tmp_path, confirmed=False), "missing --confirm-single-test-run")
    assert has(problems(tmp_path, approved_commit=None), "missing --approved-commit")
    assert has(problems(tmp_path, approved_commit="eb6d95c"), "full 40-character")
    assert has(problems(tmp_path, approved_commit=SHA.upper()), "full 40-character")


def test_guard_checks_working_tree_and_git_availability(tmp_path: Path) -> None:
    assert has(problems(tmp_path, git=fake_git(status=" M x")), "not clean")
    assert has(problems(tmp_path, git=lambda _a: None), "git unavailable")


def test_guard_detects_missing_lightweight_and_moved_tags(tmp_path: Path) -> None:
    assert has(problems(tmp_path, git=fake_git(tagged=None, kind=None)), "does not exist")
    assert has(problems(tmp_path, git=fake_git(kind="commit")), "not an annotated tag")
    moved = problems(tmp_path, git=fake_git(tagged=OTHER))
    assert has(moved, "tag moved")


def test_guard_requires_head_at_the_approved_commit(tmp_path: Path) -> None:
    # HEAD == tag is no longer sufficient: both must equal the approved commit.
    found = problems(tmp_path, approved_commit=OTHER, git=fake_git(head=OTHER, tagged=OTHER))
    assert has(found, "differs from the recorded freeze")
    assert has(problems(tmp_path, git=fake_git(head=OTHER)), "is not the approved freeze commit")


def test_guard_checks_config_fingerprint(tmp_path: Path) -> None:
    assert has(problems(tmp_path, config_fp="sha256:" + "2" * 64), "differs from the frozen")
    # Unknown (future) tag: the fingerprint must be written in the annotated tag message.
    ok = problems(tmp_path, tag="freeze-new", git=fake_git(message=f"config\n{FP}\n"))
    assert ok == []
    missing = problems(tmp_path, tag="freeze-new", git=fake_git(message="no fingerprint"))
    assert has(missing, "is not recorded in the freeze-new message")


def test_guard_refuses_second_official_run_and_overwrites(tmp_path: Path) -> None:
    log = tmp_path / "TEST_RUNS.log"
    log.write_text(json.dumps({"git_head": SHA, "run_id": "r1"}) + "\n")
    assert has(problems(tmp_path), "already recorded for this commit (r1)")
    official = tmp_path / "official"
    official.mkdir()
    (official / "metrics.json").write_text("{}")
    log.unlink()
    assert has(problems(tmp_path), "never overwritten")
    assert has(problems(tmp_path, out_dir=tmp_path / "elsewhere"), "must write to")


def test_reproducibility_check_needs_a_separate_new_directory(tmp_path: Path) -> None:
    log = tmp_path / "TEST_RUNS.log"
    log.write_text(json.dumps({"git_head": SHA, "run_id": "r1"}) + "\n")
    assert problems(tmp_path, reproducibility_check=True, out_dir=tmp_path / "repro") == []
    assert has(problems(tmp_path, reproducibility_check=True), "separate --out")
    used = tmp_path / "used"
    used.mkdir()
    (used / "metrics.json").write_text("{}")
    assert has(problems(tmp_path, reproducibility_check=True, out_dir=used), "separate --out")


def test_bench_freeze_v0_is_recorded_with_the_approved_commit() -> None:
    record = heldout.KNOWN_FREEZES["bench-freeze-v0"]
    assert record.commit == "eb6d95c19d0ae886cef1b0ae4fca431d6fa29a50"
    assert record.test_config_fp.endswith(
        "7a37fd81040a1bca42e11b8102a9ed91e2c429d453653c2542b7e05d8b8f5316"
    )


# ------------------------------------------------------------------ authorization tokens
def _authorize(tmp_path: Path, **overrides: Any) -> HeldOutAuthorization:
    official = tmp_path / "official"
    kwargs: dict[str, Any] = {
        "command": "atrace bench run --split test",
        "confirmed": True,
        "approved_commit": SHA,
        "config_fp": FP,
        "out_dir": official,
        "official_dir": official,
        "log_path": tmp_path / "TEST_RUNS.log",
        "tag": "freeze-x",
        "git": fake_git(),
        "known": KNOWN,
    }
    kwargs.update(overrides)
    return authorize_test_split(**kwargs)


def test_authorize_raises_with_all_problems(tmp_path: Path) -> None:
    with pytest.raises(HeldOutAccessError, match="missing --confirm-single-test-run"):
        _authorize(tmp_path, confirmed=False)


def test_require_authorization_rejects_missing_and_forged_tokens(tmp_path: Path) -> None:
    require_authorization("dev", None)
    with pytest.raises(HeldOutAccessError):
        require_authorization("test", None)
    forged = HeldOutAuthorization(commit=SHA, tag="t", config_fp=FP, command="x")
    with pytest.raises(HeldOutAccessError):
        require_authorization("test", forged)
    require_authorization("test", _authorize(tmp_path))


# ------------------------------------------------------------------ Python entry points
@pytest.fixture(scope="module")
def dev_instances() -> list[dict[str, Any]]:
    return load_instances(REPO / DEFAULT_DIR)


def _synthetic_test(dev: list[dict[str, Any]], ids: Sequence[str]) -> list[dict[str, Any]]:
    """Development instances relabelled as a temporary synthetic test split."""
    return [{**i, "split": "test"} for i in dev if i["instance_id"] in ids]


def test_evaluation_entry_points_refuse_test_split(dev_instances: list[dict[str, Any]]) -> None:
    ctx = support_replay_context()
    fake = _synthetic_test(dev_instances, ("T1-F4",))
    with pytest.raises(HeldOutAccessError):
        evaluate_split(fake, "test", ctx)
    with pytest.raises(HeldOutAccessError):
        evaluate_instance(fake[0], ctx, ("B1",))
    with pytest.raises(HeldOutAccessError):
        record_instance(fake[0])


def test_run_benchmark_refuses_test_split_and_writes_nothing(tmp_path: Path) -> None:
    log = tmp_path / "log"
    with pytest.raises(HeldOutAccessError):
        run_benchmark(
            split="test",
            ctx=support_replay_context(),
            out_dir=tmp_path / "out",
            bench_dir=REPO / DEFAULT_DIR,
            log_path=log,
        )
    assert not (tmp_path / "out").exists() and not log.exists()


def test_authorized_run_appends_a_complete_log_entry(
    tmp_path: Path, dev_instances: list[dict[str, Any]]
) -> None:
    fake = _synthetic_test(dev_instances, ("T1-F4", "T1-clean"))
    auth = _authorize(tmp_path)
    out = tmp_path / "official"
    metrics = run_benchmark(
        split="test",
        ctx=support_replay_context(),
        out_dir=out,
        methods=("B1", "CF"),
        bench_dir=REPO / DEFAULT_DIR,
        check_regeneration=False,
        instances=fake,
        labels=load_labels(REPO / DEFAULT_DIR),
        authorization=auth,
        log_path=tmp_path / "TEST_RUNS.log",
    )
    (entry,) = read_log(tmp_path / "TEST_RUNS.log")
    stored = json.loads((out / "canonical_fingerprints.json").read_text())
    assert entry["log_schema"] == 2 and entry["kind"] == "official"
    assert entry["command"] == "atrace bench run --split test"
    assert entry["exit_status"] == (0 if metrics["checks"]["ok"] else 1)
    assert entry["approved_commit"] == SHA and entry["config_fp"] == FP
    assert entry["freeze_tag"] == "freeze-x"
    assert entry["artifact_fps"] == stored and entry["metrics_fp"] == stored["metrics.json"]
    assert entry["run_id"] == json.loads((out / "environment.json").read_text())["run_id"]
    assert entry["started_at"] <= entry["finished_at"]


def test_failed_authorized_run_is_still_logged(tmp_path: Path) -> None:
    broken = [{"instance_id": "X", "scenario_id": "NOPE", "split": "test", "kind": "clean",
               "policy_version": "v1", "fault_plan": None}]  # fmt: skip
    with pytest.raises(KeyError):
        run_benchmark(
            split="test",
            ctx=support_replay_context(),
            out_dir=tmp_path / "official",
            bench_dir=REPO / DEFAULT_DIR,
            check_regeneration=False,
            instances=broken,
            labels=[],
            authorization=_authorize(tmp_path),
            log_path=tmp_path / "TEST_RUNS.log",
        )
    (entry,) = read_log(tmp_path / "TEST_RUNS.log")
    assert entry["exit_status"] == "error: KeyError" and entry["artifact_fps"] is None


# ------------------------------------------------------------------ the real repository
def test_real_repository_refuses_another_official_run() -> None:
    """At any post-freeze HEAD the real guard refuses; the official log is never touched."""
    log = REPO / "evaluation" / "TEST_RUNS.log"
    before = log.read_bytes()
    found = split_guard(
        confirmed=True,
        approved_commit=heldout.KNOWN_FREEZES["bench-freeze-v0"].commit,
        config_fp=heldout.KNOWN_FREEZES["bench-freeze-v0"].test_config_fp,
        out_dir=REPO / "evaluation" / "synth_v0-test",
        official_dir=REPO / "evaluation" / "synth_v0-test",
        log_path=log,
    )
    assert has(found, "already recorded for this commit")
    assert log.read_bytes() == before


def test_official_heldout_artifacts_are_intact() -> None:
    """Read-only integrity check of the committed held-out results (original fingerprinting)."""
    d = REPO / "evaluation" / "synth_v0-test"
    stored = json.loads((d / "canonical_fingerprints.json").read_text())
    for name, fp in stored.items():
        assert fingerprint((d / name).read_bytes().decode("utf-8")) == fp, name
    (official,) = read_log(REPO / "evaluation" / "TEST_RUNS.log")
    assert official["metrics_fp"] == stored["metrics.json"]
    assert official["git_head"] == heldout.KNOWN_FREEZES["bench-freeze-v0"].commit
    config = json.loads((d / "config.json").read_text())
    assert fingerprint(config) == heldout.KNOWN_FREEZES["bench-freeze-v0"].test_config_fp


# ------------------------------------------------------------------ CLI helper
def test_held_out_refusal_and_explicit_allowance() -> None:
    from agenttrace.cli_diagnose import _guard_held_out

    assert heldout.held_out_refusal("x", "dev") is None
    assert heldout.scenario_split("T5") == "test" and heldout.scenario_split("T1") == "dev"
    assert heldout.scenario_split("NOPE") is None
    with pytest.raises(typer.Exit):
        _guard_held_out("instance T5-F4", "test", allow=False)
    _guard_held_out("instance T5-F4", "test", allow=True)  # warns, does not raise
    _guard_held_out("instance T1-F4", "dev", allow=False)
