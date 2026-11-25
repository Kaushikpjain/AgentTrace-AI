# Task Tracker

Status values: `TODO` / `IN_PROGRESS` / `BLOCKED` / `DONE`. A task is `DONE` only after it has been implemented **and** its acceptance criteria verified by executed commands (see the verification log at the bottom).

Rules:
- Update this file after verified progress.
- Update REPLAY_SPEC.md **before** changing replay behaviour.
- Update DECISIONS.md when an architectural decision changes.

## Week 1: Foundation (committed 13 h)
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W1.0 | Repo, uv env (Py 3.12), ruff/mypy/pytest config, CI workflow, docs | P0 | — | 1.0 | `uv sync` ok; tools run; CI YAML valid | DONE |
| W1.1 | Trace schema v1, canonical JSON, fingerprints, semantic fingerprint | P0 | W1.0 | 2.5 | unit + P1 tests pass; mypy strict | DONE |
| W1.2 | `TraceStore` + JSONL store (atomic, validation, chain, corruption/incomplete) | P0 | W1.1 | 1.5 | store tests pass | DONE |
| W1.3 | Support env: models, 5 tools, snapshot/restore/hash, delta, idempotency, audit | P0 | W1.1 | 3.0 | env tests + P3 pass | DONE |
| W1.4 | Runtime: gateway S1–S7/D1–D4 + fault-hook seam, AgentLoop, scripted v1/v2, ReferencePolicy, max steps | P0 | W1.2, W1.3 | 2.5 | gateway + policy tests pass (incl. pre-exec timeout, lost ack) | DONE |
| W1.5 | Declarative scenarios (committed T1, T2, T3, T5, T6; stretch T4, T7, T8) + oracle | P0 | W1.3 | 1.5 | all implemented scenarios pass; oracle tests pass | DONE |
| W1.6 | CLI `scenarios`, `run`, `show` | P1 | W1.4, W1.5 | 1.0 | CLI tests pass; manual `atrace run T1` | DONE |
| W1.G | Week 1 quality gates 1–12 (TEST_PLAN §8) | P0 | all W1 | (debug budget) | all gates evidenced | DONE |

## Week 2: Record / exact replay (committed 14 h)
Also pulled forward from W3.1 (needed by strict replay, approved 2026-11-23): versioned serializable `FaultPlan`, `fault_plan.json`, `PlanFaultHook`, operators T0/F3/F5/`REPLACE_DECISION`, `atrace run --fault-plan`.
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W2.1 | Cassette (positional, consume-once, full-key) + config fingerprint check | P0 | W1 | 2.0 | unit tests | DONE |
| W2.2 | ExactReplayer (lifecycle re-application, fault-plan replay, state/raw/response verification, divergence kinds) | P0 | W2.1 | 4.0 | #1–#10 pass | DONE |
| W2.3 | Fidelity report | P1 | W2.2 | 1.0 | report fields tested | DONE |
| W2.4 | CLI `replay`; `show` state transitions | P1 | W2.2 | 1.0 | CLI tests | DONE |
| W2.5 | Acceptance #1–#10, #15, #16, #21 + P1, P4 | P0 | W2.2 | 5.0 | all pass | DONE |
| W2.6 | REPLAY_SPEC review vs. implementation | P1 | W2.5 | 1.0 | spec updated, no contradictions | DONE |

## Week 3: Faults, counterfactuals, regression, localization (committed 14 h)
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W3.1 | Fault layer: remaining operators F1, F2, F4, D1 (FaultPlan, T0, F3 `CORRUPT_OUTPUT`, F5 `LOST_ACK`, `REPLACE_DECISION` already done in Week 2); labels sidecar | P0 | W2 | 2.0 | stage declared and verified per operator | DONE |
| W3.2 | Benchmark generator + label validation + splits | P0 | W3.1 | 2.5 | CAUSAL/MASKED validated; ≥8 delayed-effect | DONE |
| W3.3 | CounterfactualRunner: both types, UNSUPPORTED, fence, same-type placebo | P0 | W2 | 4.0 | #11–#13, #17–#19 pass | DONE |
| W3.4 | RegressionRunner + fixtures | P0 | W2 | 1.5 | #14, #20 pass | DONE |
| W3.5 | Validators; baselines B1, B3, B4 | P1 | W3.2 | 2.0 | unit tests | DONE |
| W3.6 | CF localizer + Markdown investigation report | P0 | W3.3, W3.5 | 1.0 | report shows evidence labels | DONE |

## Week 4: Evaluation & release (approved plan `docs/WEEK4_PLAN.md`: 14.5 h + 2 h contingency)
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W4.1 | Metrics A/B/C + statistics (`bench/metrics.py`, `bench/stats.py`) | P0 | W3 | 3.0 | fixture tests with hand-computed values pass | DONE |
| W4.2 | `atrace bench run`: canonical vs. volatile outputs, byte-identical reruns | P0 | W4.1 | 2.0 | `make reproduce-dev` identical; subset determinism test | DONE |
| W4.3 | Correctness checks + failure gallery | P0 | W4.2 | 2.0 | all checks OK on dev; violation fixtures detected | DONE |
| W4.4 | Dev-split review and fixes (DEV ONLY) | P0 | W4.3 | 1.0 | changes recorded (ADR-022, FREEZE.md) | DONE |
| W4.5 | Freeze protocol: FREEZE.md, `bench config` fingerprints, guarded test command, run log | P0 | W4.4 | 1.0 | guard refuses without clean tree, tag and flag (tests) | DONE (tag created 2026-11-23 after approval) |
| W4.6 | Makefile + scripted demo | P1 | W4.2 | 1.5 | `DEMO_NONINTERACTIVE=1 make demo` exits 0 | DONE |
| W4.7 | README, EVALUATION, WALKTHROUGH, limitations, Phase 2 roadmap | P0 | W4.4 | 3.0 | docs consistent; README commands verified | DONE |
| W4.8 | Release prep: 0.1.0rc1, CHANGELOG, pinned actions, audit, RELEASE checklist | P1 | W4.7 | 1.0 | audit clean; checklist written | DONE (owner decisions open: see RELEASE.md) |
| W4.T | Freeze tag + single held-out test run | P0 | approval | — | owner approval at CP-T; one logged run; results committed after integrity check | DONE (run 2026-11-23; committed `c684c41`) |

## Stretch (+16 h, PLAN §18)
S1 templates T4/T7/T8 (1.0) **DONE in W1.5** · S2 property P2/P3 full (1.5) · S3 classifier (2.0) · S4 B2 (0.5) · S5 LCS alignment (2.0) · S6 two-fault cases (1.0) **DONE (2 MULTI instances)** · S7 decoys (0.5) **DONE (8 decoy-only + 8 decoy+F4)** · S8 Rich timeline (1.5) · S9 CI bench smoke + pip-audit (1.0) · S10 boundary test + JSON-schema export (1.0) · S11 EVALUATION/SECURITY docs (2.0) · S12 demo video (0.5) · S13 robustness tests (1.5). All others `TODO`.

## Level 2 backlog (after CP5; not scheduled)
Phase 2A local LLM policy · Phase 2B LangGraph adapter · Phase 2C FastAPI + React · SQLite store · ddmin · regression management · security suite · OTel export.

## Verification log
| Date | Command | Result |
|---|---|---|
| 2026-11-23 | `uv sync` (Python 3.12.14, isolated `.venv`) | OK |
| 2026-11-23 | `uv run ruff check .` / `uv run ruff format --check .` | All checks passed / 55 files already formatted |
| 2026-11-23 | `uv run mypy` (strict, 30 source files) | Success: no issues found |
| 2026-11-23 | `HYPOTHESIS_PROFILE=ci uv run pytest --cov=agenttrace` | 167 passed; line+branch coverage 95% (total) |
| 2026-11-23 | `uv build --wheel` + install into a fresh venv + `atrace run T6 --no-save` | wheel contains 8 scenario files; PASS, exit 0 |
| 2026-11-23 | `uv run atrace --help`, `atrace scenarios`, `atrace run T1`, `atrace show <id>` | OK; T1 PASS; integrity verified |
| 2026-11-23 | CI YAML parsed with PyYAML (`uv run --with pyyaml`) | 1 job, 9 steps (not yet executed on GitHub) |
| 2026-11-23 | `/usr/bin/time -l atrace run T1 --no-save` | max RSS 39,583,744 bytes (~40 MB), 0.24 s |
| 2026-11-23 | `/usr/bin/time -l python -m pytest -q` | max RSS 63,455,232 bytes (~63 MB), 1.16 s |
| 2026-11-23 (W2) | baseline before Week 2: ruff, mypy, `HYPOTHESIS_PROFILE=ci pytest --cov` | clean; 167 passed; 95% |
| 2026-11-23 (W2) | `uv run ruff check .` / `ruff format --check .` / `mypy` (37 files) | all clean |
| 2026-11-23 (W2) | `HYPOTHESIS_PROFILE=ci uv run pytest --cov=agenttrace` | 236 passed (incl. import guards extended to `faults/`); total coverage 96% (replay/exact.py 95%, cassette 97%, fidelity 100%) |
| 2026-11-23 (W2) | fidelity sweep: 8 templates × {v1, v2} × {none, lost_ack, pre_exec timeout, corrupt total} recorded then strictly replayed | 64/64 VERIFIED, 64/64 fidelity exact, 660 boundary events, 0 policy calls (recorded outcomes: 52 PASS / 12 FAIL) |
| 2026-11-23 (W2) | `/usr/bin/time -l atrace replay <lost-ack run>` | VERIFIED; max RSS 39,993,344 bytes (~40 MB), 0.16 s |
| 2026-11-23 (W2) | `atrace replay <v2 run> --policy v1` | CONFIG_MISMATCH, exit 3 |
| 2026-11-23 (W3) | baseline before Week 3 (HEAD = origin/main = 5ba1709): ruff, mypy, `HYPOTHESIS_PROFILE=ci pytest --cov` | clean; 236 passed; 96%; 23 Week 2 acceptance tests pass |
| 2026-11-23 (W3) | `uv run ruff check .` / `ruff format --check .` / `mypy` (52 files) | all clean |
| 2026-11-23 (W3) | `HYPOTHESIS_PROFILE=ci uv run pytest --cov=agenttrace` | 306 passed; total coverage 94% |
| 2026-11-23 (W3) | `atrace bench generate` then `atrace bench verify` | 67 instances, 0 rejected (CAUSAL 40 = 38 single + 2 MULTI; MASKED 11; CLEAN 8; DECOY_ONLY 8); 36 causal with symptom distance ≥ 1; files equal a fresh regeneration |
| 2026-11-23 (W3) | experiment at the injection site of every CAUSAL single-site instance (default request + same-type placebo) | 38/38 repair observed, 38/38 placebo valid |
| 2026-11-23 (W3) | regression of the 4 F5 baselines with candidate v2 | 4/4 FAIL → DETERMINISTIC_PASS (FIXED), 2/2 runs each |
| 2026-11-23 (W3) | PRELIMINARY dev-split localization (16 CAUSAL single-site; test split untouched) | Top-1: B1 8, B3 8, B4 13, CF 16; Top-3: B1 8, B3 9, B4 16, CF 16; CF replays 8–16 per run (182 total); max RSS ~37 MB |
| 2026-11-23 (W4) | baseline before Week 4 (HEAD = origin/main = cee6f50): ruff, mypy, pytest | clean; all passed |
| 2026-11-23 (W4) | `atrace bench run --split dev` | 30 instances, 16 eligible; all correctness checks OK; 2.3 s, max RSS ~45 MB |
| 2026-11-23 (W4) | `make reproduce-dev` | 6/6 canonical files byte-identical across two runs; environment/timings differ (volatile) |
| 2026-11-23 (W4) | `make audit` (pip-audit, `--require-hashes`, exported lock) | No known vulnerabilities found |
| 2026-11-23 (W4) | `DEMO_NONINTERACTIVE=1 ./scripts/demo.sh` | exit 0; replay VERIFIED; CF repair site seq 11; regression FIXED |
| 2026-11-23 (W4) | GitHub Actions pins resolved via `git ls-remote --tags` | checkout v4.4.0 = 11d5960a…; setup-uv v6.8.0 = d0cc045d… (lightweight tags) |
| 2026-11-23 (W4.T) | owner approval at CP-T; `git tag -a bench-freeze-v0` on `eb6d95c`; `uv run atrace bench run --split test --confirm-single-test-run` (clean tree, `/usr/bin/time -l`) | exit 0; run `b9c61e38…`; 37 instances; all correctness checks OK; 2.91 s wall, peak RSS ≈ 44 MB; one entry in `TEST_RUNS.log` |
| 2026-11-25 | held-out artifact integrity: original `agenttrace.trace.fingerprint` recomputation, log, config fingerprint, environment, private backup + its SHA256SUMS, tag resolution | all checks pass (FREEZE.md); results committed exactly as produced (`c684c41`) |
| 2026-11-25 | GitHub API (read-only, unauthenticated): Actions run 45203007961 | `ci`, push to `main` at `eb6d95c`, status completed, conclusion **success** |
| 2026-11-25 | GitHub API: repository metadata | **public**, no licence; `docs/PLAN_v0.2.1.md` and `docs/archive/PLAN_v0.2.md` publicly readable on `main`; `private/` not tracked; no tags on the remote |
