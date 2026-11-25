# Release checklist: v0.1.0

Status per item. **[x]** = verified locally by an executed command (see TASKS.md verification log); **[ ]** = pending or needs approval.

## Quality gates (local; last full run 2026-11-25 at version 0.1.0, see TASKS.md)
- [x] `uv sync --locked`: isolated install from `uv.lock`
- [x] `make check`: ruff lint, ruff format check, mypy strict, pytest
- [x] `make cov`: full suite with coverage (CI Hypothesis profile)
- [x] `make smoke`: CLI smoke test
- [x] `make verify-bench`: benchmark equals a deterministic regeneration
- [x] `make reproduce-dev`: byte-identical canonical dev outputs
- [x] `make audit`: pip-audit of the locked dependencies (no known vulnerabilities at the time of the check)
- [x] `DEMO_NONINTERACTIVE=1 make demo`: scripted demo completes
- [x] Clean wheel install into a fresh venv runs `atrace run T6`

## Evaluation
- [x] Dev-split evaluation committed (`evaluation/synth_v0-dev/`) with all correctness checks OK
- [x] **Freeze approved**: annotated tag `bench-freeze-v0` created locally on `eb6d95c` (FREEZE.md); not pushed
- [x] **Held-out test run approved and executed once** (2026-11-23, exit 0); integrity verified; results committed (`evaluation/synth_v0-test/`, `c684c41`); one `evaluation/TEST_RUNS.log` entry
- [x] README and EVALUATION §9 updated with test-split numbers (counts + intervals), checked against `metrics.json`

## Repository and publication (owner decisions)
- [ ] Repository visibility decided: **still PUBLIC** (GitHub API, 2026-11-25); private preferred. Manual steps are below
- [ ] Licence chosen (none added; Apache-2.0 recommended, pending approval)
- [x] GitHub Actions green on the last pushed commit `eb6d95c` (run 45203007961, conclusion success, read via the GitHub API)
- [ ] Push of the post-freeze commits approved, and CI observed green on them (currently unverified: not pushed)
- [x] Version bumped from `0.1.0rc1` to `0.1.0` (pyproject, `__version__`, `uv.lock`); CHANGELOG dated 2026-11-25 (local release commit)
- [ ] Release tag `v0.1.0`: **proposed** as an annotated tag on the local release commit. It is not created until the owner approves; no GitHub release without approval

## Content safety
- [ ] No research-sensitive planning material in the release tree. Pending owner decision: `docs/PLAN_v0.2.1.md`, `docs/archive/` (publicly readable on `main`; also included in the sdist built on 2026-11-25). Git history is not rewritten without approval
- [x] No secrets, credentials or personal data in tracked files (scanned)
- [x] `private/` is git-ignored

## Making the repository private (manual, owner only)
1. GitHub → repository **Settings** → **General** → *Danger Zone* → **Change repository visibility** → **Make private**, and confirm.
2. Check: `curl -s -o /dev/null -w "%{http_code}" https://api.github.com/repos/Kaushikpjain/AgentTrace-AI` should print `404` when unauthenticated.

This **prevents further public access**. It does **not reverse the earlier public disclosure**: anything already viewed, cloned, forked, cached or archived while the repository was public may persist, and the public period began with the first push. Deleting files or rewriting history (not done, not authorised) would not undo that either. How this affects IPR is a question for the owner's IPR advisers; notes stay in the git-ignored `private/` directory.
