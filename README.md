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
                  runtime/ (gateway, agent loop) · policies/ · evals/ · cli.py
tests/            unit/ · integration/ · property/
docs/             PLAN_v0.2.1 · PRD · ARCHITECTURE · REPLAY_SPEC · TRACE_SCHEMA · TEST_PLAN · TASKS · DECISIONS
benchmarks/       (Week 3) generated fault instances and labels
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

**Not implemented yet:** exact replay, counterfactual replay, regression execution (Weeks 2–3); fault operators and benchmark (Week 3); localization metrics (Weeks 3–4).
<!-- STATUS:END -->

## Installation
Requires [uv](https://docs.astral.sh/uv/) and a Python 3.12 interpreter (uv can install one). Verified on macOS (Apple M2, 8 GB).
```bash
uv sync                      # creates an isolated .venv with locked dependencies
uv run atrace scenarios      # list scenario templates
uv run atrace run T1         # run the scripted agent; prints the trace and PASS/FAIL
uv run atrace show <run_id>  # reload a saved run and verify its integrity
```
Runs are saved under `./runs` (override with `--runs-dir` or `ATRACE_RUNS_DIR`). `atrace run` exits 0 on oracle PASS, 1 on FAIL and 2 on errors.

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
