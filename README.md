# AgentTrace AI

**A reliability, security-testing and failure-diagnosis platform for tool-using AI agents.** It is built around deterministic record/replay, controlled counterfactual interventions, and fault injection with known ground truth.

> **Status: early development (Week 1 of a 4-week MVP).** Only the features listed under *Development status* as implemented exist. Everything else is planned.

## Problem
When a tool-using agent fails, a trace shows *what* happened but not *which step is responsible*, whether the failure is reproducible, or whether a fix really works. The first visible error is often not the cause. Re-running a "fixed" agent against replayed responses can falsely report success. Nondeterminism and stateful tools make honest reproduction hard.

AgentTrace's MVP addresses these questions with:
1. exact, verifiable replay of recorded runs, including environment state transitions;
2. typed, placebo-controlled interventions on single steps (observation vs. execution replacement);
3. regression execution that provably never reuses recorded responses;
4. localization benchmarks on injected faults, reporting **injection-site localization**, **interventional repair** and **diagnostic evidence** as separate metrics.

No novelty is claimed for replay-based failure attribution, which has substantial prior work (see `docs/PLAN_v0.2.1.md` §4).

## MVP boundaries (Level 1)
- One synthetic customer-support / order-management environment with 5 sandboxed tools; a deterministic scripted agent (no LLM); JSONL traces; a CLI.
- **Not in the MVP:** web UI, databases, Docker, LLM inference, LangGraph, OpenTelemetry, prompt-injection suites. See `docs/PRD.md` §7 and the roadmap below.

## Technology
Python 3.12 · uv · Pydantic v2 · Typer + Rich · pytest + Hypothesis · Ruff · mypy (strict). Runs offline on an 8 GB MacBook Air M2 with no paid APIs.

## Repository
```
src/agenttrace/   trace/ (schema, canonical JSON, store) · env/support/ (sandbox env, scenarios)
                  runtime/ (gateway, agent loop) · faults/ (fault plans) · replay/ (strict,
                  counterfactual, regression) · localize/ (B1, B3, B4, CF) · bench/ (benchmark)
                  policies/ · evals/ · runner.py · cli.py · cli_diagnose.py
examples/         fault_plans/ (example FaultPlan JSON files)
tests/            unit/ · integration/ · acceptance/ · property/
docs/             PLAN_v0.2.1 · PRD · ARCHITECTURE · REPLAY_SPEC · TRACE_SCHEMA · TEST_PLAN · TASKS · DECISIONS
benchmarks/       synth_v0/ validated benchmark (labels.jsonl is privileged)
```

## Development status
See `docs/TASKS.md` for the verified status of every task.

<!-- STATUS:BEGIN -->
**Implemented and tested (Week 1):**
- Versioned trace schema (observable trace + privileged execution ledger), canonical JSON, SHA-256 fingerprints, semantic fingerprints.
- JSONL trace store: atomic writes, schema validation, hash-chain integrity, corruption/incomplete-recording detection.
- Synthetic support environment: 5 sandboxed tools, Decimal money, state-counter ids, transactional commits, idempotency, audit log, snapshot/restore.
- Boundary gateway implementing the 7-stage tool lifecycle (validate → pre-execution faults → execute on a working copy → commit/rollback → post-execution faults → deliver → record), plus the decision lifecycle and a fault-hook seam.
- Deterministic scripted agent (v1, v2), reference-policy interface, max-step guard.
- 8 declarative scenario templates (T1–T8) with a deterministic oracle.
- CLI: `atrace scenarios`, `atrace run`, `atrace show`.

**Implemented and tested (Week 2):**
- Versioned, serializable `FaultPlan` with stage-declared operators: timeout before execution (no commit), lost acknowledgement after commit, output corruption, decision replacement.
- Strict exact replay (`REPLAY_STRICT`): restores the initial state, serves recorded decisions without calling the policy, re-executes sandbox tools with the recorded fault plan, and verifies raw results, state transitions, delivered responses, final state and outcome. It fails closed at the first divergence (request, ordering, missing/extra entries, raw result, state hash, response, outcome) and refuses changed configurations.
- Fidelity report, and `atrace replay` with integrity, configuration, state and outcome verification.

**Implemented and tested (Week 3):**
- Fault operators F1 wrong tool, F2 wrong/invalid arguments, F4 wrong retrieval, D1 decoy read. Each declares its stage and fires deterministically; it records nothing when it doesn't apply.
- Counterfactual replay (`REPLAY_INTERVENE`): strict prefix, typed **observation** vs **execution** replacement, trusted references only, cassette fence, fresh downstream execution. Every intervention is paired with a same-type placebo, and unfaithful requests return explicit `UNSUPPORTED` results.
- Regression execution: fresh runs of a candidate agent against the same scenario and environment fixture, never consuming the original cassette.
- Localizers B1 (earliest visible error), B3 (rule-based), B4 (earliest reference deviation) and CF (placebo-controlled counterfactual), with evidence labels `SUSPICION` / `REFERENCE_DEVIATION` / `INTERVENTIONAL_REPAIR` / `UNSUPPORTED`. A repair is reported as *sufficient to repair this run*, not as a unique cause.
- AgentTrace-Synth v0: 67 validated instances (40 causal, 11 masked, 8 clean, 8 decoy-only), template-based dev/test split, deterministic regeneration check, privileged labels.

**Not implemented yet (Week 4):** Metric A/B/C benchmark report with confidence intervals, the frozen test-split run, the demo script.
<!-- STATUS:END -->

## Installation
Requires [uv](https://docs.astral.sh/uv/) and a Python 3.12 interpreter (uv can install one). Verified on macOS (Apple M2, 8 GB).
```bash
uv sync                      # creates an isolated .venv with locked dependencies
uv run atrace scenarios      # list scenario templates
uv run atrace run T1         # run the scripted agent; prints the trace and PASS/FAIL
uv run atrace show <run_id>  # reload a saved run and verify its integrity
uv run atrace run T1 --fault-plan examples/fault_plans/lost_ack_refund.json   # inject a fault
uv run atrace replay <run_id>  # strict replay: verify state transitions and outcome

# Week 3: fault injection, counterfactuals, regression, investigation
uv run atrace bench list --split dev            # benchmark instance ids (labels stay private)
uv run atrace inject T1-D1+F4                   # record a benchmark instance (decoy + wrong retrieval)
uv run atrace intervene <run_id> --seq 11 --type execution   # intervention + same-type placebo
uv run atrace investigate <run_id> --markdown report.md      # B1, B3, B4, CF ranking + evidence
uv run atrace inject T1-F5                      # lost acknowledgement with agent v1
uv run atrace regress <run_id> --policy v2      # fresh candidate runs, no cassette reuse
uv run atrace bench verify                      # benchmark files == deterministic regeneration
```
`intervene` exits 0 completed, 3 CONFIG_MISMATCH, 5 UNSUPPORTED, 6 INVALID_COUNTERFACTUAL; `regress` exits 0 on a deterministic candidate PASS, 1 otherwise, 3 on CONFIG_ERROR.
Runs are saved under `./runs` (override with `--runs-dir` or `ATRACE_RUNS_DIR`). `atrace run` exits 0 on oracle PASS, 1 on FAIL and 2 on errors. `atrace replay` exits 0 VERIFIED, 1 DIVERGED, 3 CONFIG_MISMATCH, 4 INTEGRITY_ERROR (2 = usage / run not found).

## Testing
```bash
uv run pytest                          # unit + integration tests
uv run pytest --cov=agenttrace         # with coverage
HYPOTHESIS_PROFILE=ci uv run pytest    # more property-test examples
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Roadmap
- **Level 1 (MVP, 4 weeks):** tracing → exact replay → fault injection + counterfactual + regression execution → benchmark with Metrics A/B/C.
- **Level 2:** Phase 2A local small-LLM policy · 2B LangGraph adapter · 2C FastAPI + React viewer · SQLite store · scenario minimization (ddmin) · regression management · security test suite · OpenTelemetry export.
- **Level 3 (research):** budget-aware, evidence-graded failure localization (kept separate from this repository).

## Licence
Not yet selected. Until a licence is chosen, this code must not be published or redistributed. See `docs/DECISIONS.md` ADR-010.
