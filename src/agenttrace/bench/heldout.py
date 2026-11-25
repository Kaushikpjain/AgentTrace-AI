"""Held-out (test-split) safeguards. Operational guard rails, NOT a security boundary.

They prevent *accidental* use of the held-out split (running the evaluation, or inspecting
held-out cases while developing). Anyone with write access to the repository can bypass them;
the protection that matters is the documented protocol in FREEZE.md and the git history.

Post-freeze hardening (ADR-026):
- the test split requires the *explicitly approved* full commit hash (``--approved-commit``);
  a tag alone is movable and is no longer sufficient;
- the freeze tag must be annotated, resolve to that commit, and HEAD must equal it;
- the evaluation configuration fingerprint must equal the one recorded for the freeze
  (``KNOWN_FREEZES``, else the fingerprint written in the annotated tag message);
- a second run for an already-evaluated commit is refused unless it is an explicit
  ``--reproducibility-check`` into a separate output directory; official artifacts are never
  overwritten;
- every guarded run appends a full entry (command, exit status, commit, fingerprints) to the log.

Python entry points (``evaluate_split``, ``run_benchmark``, ...) refuse the test split unless
they receive a ``HeldOutAuthorization`` created by ``authorize_test_split``.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FREEZE_TAG = "bench-freeze-v0"
HELD_OUT_SPLIT = "test"
LOG_SCHEMA = 2


@dataclass(frozen=True)
class FreezeRecord:
    commit: str
    test_config_fp: str


# Approved freezes. Recording the commit here means a moved tag is detected even if its
# message is rewritten. A future freeze adds its entry in a reviewed commit *after* the freeze.
KNOWN_FREEZES: Mapping[str, FreezeRecord] = {
    "bench-freeze-v0": FreezeRecord(
        commit="eb6d95c19d0ae886cef1b0ae4fca431d6fa29a50",
        test_config_fp="sha256:7a37fd81040a1bca42e11b8102a9ed91e2c429d453653c2542b7e05d8b8f5316",
    ),
}

Git = Callable[[Sequence[str]], str | None]
_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_FP = re.compile(r"sha256:[0-9a-f]{64}")


class HeldOutAccessError(RuntimeError):
    """Raised when a held-out entry point is used without authorization."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


def git_output(args: Sequence[str]) -> str | None:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, check=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


_TOKEN = object()  # only ``authorize_test_split`` can mint a valid authorization


@dataclass(frozen=True)
class HeldOutAuthorization:
    commit: str
    tag: str
    config_fp: str
    command: str
    reproducibility_check: bool = False
    _token: object = field(default=None, repr=False, compare=False)


def read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.is_file():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


def test_split_guard(
    *,
    confirmed: bool,
    approved_commit: str | None,
    config_fp: str,
    out_dir: Path,
    official_dir: Path,
    log_path: Path,
    reproducibility_check: bool = False,
    tag: str = FREEZE_TAG,
    git: Git = git_output,
    known: Mapping[str, FreezeRecord] = KNOWN_FREEZES,
) -> list[str]:
    """Reasons the held-out split must NOT run (empty list = allowed)."""
    problems: list[str] = []
    if not confirmed:
        problems.append("missing --confirm-single-test-run")
    if approved_commit is None:
        problems.append("missing --approved-commit <full 40-character commit hash>")
    elif not _FULL_SHA.fullmatch(approved_commit):
        problems.append("--approved-commit must be a full 40-character lowercase commit hash")
    record = known.get(tag)
    if record is not None and approved_commit is not None and approved_commit != record.commit:
        problems.append(
            f"approved commit {approved_commit} differs from the recorded freeze of {tag} "
            f"({record.commit})"
        )

    status = git(["status", "--porcelain"])
    if status is None:
        problems.append("git unavailable: cannot verify a clean tree")
    elif status:
        problems.append("working tree is not clean")
    kind = git(["cat-file", "-t", f"refs/tags/{tag}"])
    tagged = git(["rev-parse", f"{tag}^{{commit}}"])
    if kind is None or tagged is None:
        problems.append(f"freeze tag {tag!r} does not exist")
    else:
        if kind != "tag":
            problems.append(f"freeze tag {tag!r} is not an annotated tag")
        if approved_commit is not None and tagged != approved_commit:
            problems.append(
                f"freeze tag {tag} resolves to {tagged}, not the approved commit (tag moved?)"
            )
    head = git(["rev-parse", "HEAD"])
    if approved_commit is not None and head != approved_commit:
        problems.append(f"HEAD {head} is not the approved freeze commit {approved_commit}")

    if record is not None:
        if config_fp != record.test_config_fp:
            problems.append(
                f"evaluation config {config_fp} differs from the frozen {record.test_config_fp}"
            )
    elif kind is not None:
        message = git(["tag", "-l", "--format=%(contents)", tag]) or ""
        if config_fp not in _FP.findall(message):
            problems.append(f"evaluation config {config_fp} is not recorded in the {tag} message")

    prior = [e for e in read_log(log_path) if e.get("git_head") == approved_commit]
    official_written = (official_dir / "metrics.json").exists()
    same_dir = out_dir.resolve() == official_dir.resolve()
    if reproducibility_check:
        if same_dir or (out_dir / "metrics.json").exists():
            problems.append("a reproducibility check must write to a new, separate --out directory")
    else:
        if prior:
            ids = ", ".join(str(e.get("run_id")) for e in prior)
            problems.append(
                f"an official held-out run is already recorded for this commit ({ids}); "
                "a rerun is only allowed as --reproducibility-check with a separate --out"
            )
        if same_dir and official_written:
            problems.append(
                f"official artifacts already exist in {official_dir}; never overwritten"
            )
        elif not same_dir:
            problems.append(f"the official run must write to {official_dir}")
    return problems


def authorize_test_split(
    *,
    command: str,
    confirmed: bool,
    approved_commit: str | None,
    config_fp: str,
    out_dir: Path,
    official_dir: Path,
    log_path: Path,
    reproducibility_check: bool = False,
    tag: str = FREEZE_TAG,
    git: Git = git_output,
    known: Mapping[str, FreezeRecord] = KNOWN_FREEZES,
) -> HeldOutAuthorization:
    problems = test_split_guard(
        confirmed=confirmed,
        approved_commit=approved_commit,
        config_fp=config_fp,
        out_dir=out_dir,
        official_dir=official_dir,
        log_path=log_path,
        reproducibility_check=reproducibility_check,
        tag=tag,
        git=git,
        known=known,
    )
    if problems:
        raise HeldOutAccessError(problems)
    assert approved_commit is not None
    return HeldOutAuthorization(
        commit=approved_commit,
        tag=tag,
        config_fp=config_fp,
        command=command,
        reproducibility_check=reproducibility_check,
        _token=_TOKEN,
    )


def require_authorization(split: str, authorization: HeldOutAuthorization | None) -> None:
    """Raise unless ``split`` is not held out or a valid authorization is supplied."""
    if split != HELD_OUT_SPLIT:
        return
    if authorization is None or authorization._token is not _TOKEN:
        raise HeldOutAccessError(
            [
                "the held-out test split requires an authorization from authorize_test_split "
                "(CLI: atrace bench run --split test --approved-commit ... "
                "--confirm-single-test-run)"
            ]
        )


def append_log(log_path: Path, entry: Mapping[str, Any]) -> None:
    """Append one JSON line. Existing lines are never rewritten."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(json.dumps({"log_schema": LOG_SCHEMA, **entry}, sort_keys=True) + "\n")


def scenario_split(scenario_id: str) -> str | None:
    from agenttrace.env.support.scenario import load_scenario

    try:
        return load_scenario(scenario_id).split
    except (FileNotFoundError, ValueError, KeyError):
        return None


def held_out_refusal(what: str, split: str | None) -> str | None:
    """Message for CLI diagnostic commands touching held-out cases (None = allowed)."""
    if split != HELD_OUT_SPLIT:
        return None
    return (
        f"{what} belongs to the held-out test split. Inspecting held-out cases during "
        "development risks tuning against the held-out benchmark. Pass --allow-held-out to "
        "proceed deliberately (operational safeguard, not a security control)."
    )
