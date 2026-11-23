# Release checklist: v0.1.0

Status per item. **[x]** = verified locally by an executed command (see TASKS.md verification log); **[ ]** = pending or needs approval.

## Quality gates (local)
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
- [ ] **Freeze approved**: tag `bench-freeze-v0` created locally on the approved commit (FREEZE.md)
- [ ] **Held-out test run approved and executed once**; results committed (`evaluation/synth_v0-test/`); `evaluation/TEST_RUNS.log` entry
- [ ] README results section updated with test-split numbers (counts + intervals)

## Repository and publication (owner decisions)
- [ ] Repository visibility decided (currently PUBLIC; private preferred). Steps and consequences are in the Week 4 checkpoint report
- [ ] Licence chosen (none added; Apache-2.0 recommended, pending approval)
- [ ] Push approved; **GitHub Actions run observed green** on the pushed commit (never claimed before it is observed)
- [ ] Version bumped from `0.1.0rc1` to `0.1.0`; CHANGELOG dated
- [ ] Release tag `v0.1.0` (no GitHub release published without approval)

## Content safety
- [ ] No research-sensitive planning material in the release tree. Pending owner decision: `docs/PLAN_v0.2.1.md`, `docs/archive/` (git history is not rewritten without approval)
- [x] No secrets, credentials or personal data in tracked files (scanned)
- [x] `private/` is git-ignored
