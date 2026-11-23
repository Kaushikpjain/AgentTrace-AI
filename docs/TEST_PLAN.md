# Test Plan

All claims in README, TASKS and reports must be backed by tests that were actually executed. Test commands:
```
uv run pytest                      # all tests
uv run pytest --cov=agenttrace     # with coverage
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

## 1. Unit tests (`tests/unit/`)
| Area | Covered behaviour |
|---|---|
| canonical | Decimal normalization; float/NaN rejection; key-order invariance; NFC; enum/datetime/model encoding; `to_json_value` round-trip |
| fingerprint | fp stability; config-fingerprint sensitivity to every field |
| schema | model validation; StateTransition constraint; `extra=forbid`; version check |
| store | write/read round-trip; invalid schema; missing fields; corrupted event line; tampered event (chain mismatch); incomplete recording (no footer); seq gap; existing run not overwritten; temp dirs ignored |
| env | each tool's success/error paths; idempotency; amount guard; ticket already closed; snapshot/restore hash equality; scenario initial state unchanged; JSON delta |
| gateway | S1 validation (unknown tool, bad args → no execution); read-only tools never mutate; mutating commit + delta; failed mutating call rolls back; tool exception → `TOOL_EXCEPTION` without commit; attempt numbering; **pre-execution timeout** (`executed=false`, `committed=false`); **lost ack** (`committed=true` with a delivered timeout, raw ok in the ledger); decision-stage transform recorded raw vs. delivered |
| policy | v1/v2 decision sequences; retry behaviour under timeouts; v1 duplicate vs. v2 idempotent under lost ack |
| oracle | each clause passes/fails correctly |
| guards | banned imports in `env/` and `policies/` (AST scan) |

## 2. Integration tests (`tests/integration/`)
- Every clean scenario passes its oracle with v1 and v2.
- Determinism: two executions → equal semantic fingerprints, different run ids.
- Interleaved repeated executions of all scenarios → no state leakage (test #15 precursor).
- No network: scenarios run with `socket.socket` patched to raise.
- CLI via Typer's `CliRunner`: `scenarios`, `run` (exit codes, run id, persisted trace), `show`.

## 3. Property-based tests (Hypothesis)
Week 1 property tests live next to their unit tests (`tests/unit/test_canonical.py` → P1, `tests/unit/test_env.py` → P3). `tests/property/` will hold the cross-module properties P2/P4 from Week 2.
| ID | Property | Week |
|---|---|---|
| P1 | canonical bytes are invariant under dict key permutation and Decimal scale (`80` vs. `80.00`) | 1 |
| P3 | snapshot → restore → hash round-trips for generated valid states | 1 (stretch S2 for full generators; Week 1 has a basic version) |
| P2 | record → exact replay satisfies invariant I1 on generated states | 2 / stretch |
| P4 | any single-field cassette mutation is detected (never a silent pass) | 2 |

Hypothesis profiles (`tests/conftest.py`): `dev` (max_examples=50, default) and `ci` (200, selected with `HYPOTHESIS_PROFILE=ci`), to stay light on 8 GB.

## 4. Replay acceptance tests (Weeks 2–3)
Tests #1–#21 as defined in PLAN_v0.2.1 §13 (initial state, recording, modification, expected behaviour, final state, assertion). Mapping to REPLAY_SPEC: see REPLAY_SPEC §12. They live in `tests/acceptance/test_replay_matrix.py`, one test function per row, named `test_rNN_<slug>`.

## 5. Fault-injection validation (Week 3)
- Every fault instance: the clean run passes. Then faulty fail → `CAUSAL`, faulty pass → `MASKED`.
- `CAUSAL` instances are confirmed by the validator's `INJECTION_CLEAN_VALUE` intervention.
- Decoy-only variants must pass.
- Each operator declares exactly one stage, and the declared stage matches the ledger's fault application.

## 6. Benchmark leakage prevention (Week 3)
- Localizer functions accept only the observable `Trace` type (type-checked and asserted).
- AST test: `agenttrace.localize` does not import `load_ledger`, label loaders, fault plans or `INJECTION_CLEAN_VALUE`.
- Splits are by template (dev T1–T4, test T5–T8). A freeze tag is required before the test-split run, and test-split runs are logged.

## 7. Regression testing (Week 3)
- #14 and #20. The regression runner has no cassette parameter; a spy store raises on cassette access; a poisoned recording on disk does not change the result.

## 8. Week 1 quality gates (CP1)
| # | Gate | Evidence |
|---|---|---|
| 1 | Package installs in an isolated env | `uv sync` succeeds into `.venv` (Python 3.12) |
| 2 | CLI launches | `uv run atrace --help`, `atrace scenarios` |
| 3 | Clean scenarios pass oracles | integration test + `atrace run T1` |
| 4 | Snapshot/restore preserves hashes | unit + property P3 |
| 5 | Repeated runs → identical semantic traces | integration determinism test |
| 6 | Tool mutations isolated | gateway unit tests + scenario immutability test |
| 7 | No real external side effects | banned-import guard + socket-blocked run test |
| 8 | Serialization round-trips | canonical + store tests |
| 9 | Ruff passes | `ruff check`, `ruff format --check` |
| 10 | mypy passes | `mypy` (strict, `src/agenttrace`) |
| 11 | pytest passes | `pytest` |
| 12 | CI config valid | YAML parses; its steps are the same commands executed locally |

## 9. Checkpoint criteria
CP1–CP5 as in PLAN_v0.2.1 §19. A checkpoint is passed only when its listed tests pass in a run recorded in TASKS.md.
