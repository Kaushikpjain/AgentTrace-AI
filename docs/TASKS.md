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
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W2.1 | Cassette (positional, consume-once, full-key) + config fingerprint check | P0 | W1 | 2.0 | unit tests | TODO |
| W2.2 | ExactReplayer (lifecycle re-application, fault-plan replay, state/raw/response verification, divergence kinds) | P0 | W2.1 | 4.0 | #1–#10 pass | TODO |
| W2.3 | Fidelity report | P1 | W2.2 | 1.0 | report fields tested | TODO |
| W2.4 | CLI `replay`; `show` state transitions | P1 | W2.2 | 1.0 | CLI tests | TODO |
| W2.5 | Acceptance #1–#10, #15, #16, #21 + P1, P4 | P0 | W2.2 | 5.0 | all pass | TODO |
| W2.6 | REPLAY_SPEC review vs. implementation | P1 | W2.5 | 1.0 | spec updated, no contradictions | TODO |

## Week 3: Faults, counterfactuals, regression, localization (committed 14 h)
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W3.1 | Fault layer: F1–F5, D1, T0 fixture; FaultPlan; ledger applications; labels | P0 | W2 | 3.0 | stage declared and verified per operator | TODO |
| W3.2 | Benchmark generator + label validation + splits | P0 | W3.1 | 2.5 | CAUSAL/MASKED validated; ≥8 delayed-effect | TODO |
| W3.3 | CounterfactualRunner: both types, UNSUPPORTED, fence, same-type placebo | P0 | W2 | 4.0 | #11–#13, #17–#19 pass | TODO |
| W3.4 | RegressionRunner + fixtures | P0 | W2 | 1.5 | #14, #20 pass | TODO |
| W3.5 | Validators; baselines B1, B3, B4 | P1 | W3.2 | 2.0 | unit tests | TODO |
| W3.6 | CF localizer + Markdown investigation report | P0 | W3.3, W3.5 | 1.0 | report shows evidence labels | TODO |

## Week 4: Evaluation & release (committed 9 h)
| ID | Description | Priority | Depends on | Est. h | Acceptance criteria | Status |
|---|---|---|---|---|---|---|
| W4.1 | `bench run`: Metric A/B/C + Wilson CIs + manifest | P0 | W3 | 2.5 | tables generated | TODO |
| W4.2 | Dev run, fixes, freeze tag, test-split run | P0 | W4.1 | 2.0 | frozen results | TODO |
| W4.3 | README results + limitations; docs pass | P0 | W4.2 | 2.5 | docs consistent | TODO |
| W4.4 | `make demo` + terminal recording | P1 | W4.2 | 1.0 | demo runs end-to-end | TODO |
| W4.5 | NEXT.md (Phase 2A plan) | P2 | W4.3 | 1.0 | written | TODO |

## Stretch (+16 h, PLAN §18)
S1 templates T4/T7/T8 (1.0) **DONE in W1.5** · S2 property P2/P3 full (1.5) · S3 classifier (2.0) · S4 B2 (0.5) · S5 LCS alignment (2.0) · S6 two-fault cases (1.0) · S7 decoys (0.5) · S8 Rich timeline (1.5) · S9 CI bench smoke + pip-audit (1.0) · S10 boundary test + JSON-schema export (1.0) · S11 EVALUATION/SECURITY docs (2.0) · S12 demo video (0.5) · S13 robustness tests (1.5). All others `TODO`.

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
