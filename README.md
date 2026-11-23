# AgentTrace AI

**Deterministic record/replay, controlled counterfactual interventions and failure diagnosis for tool-using AI agents.**

> **Status: v0.1.0rc1 release candidate (deterministic MVP).** Everything listed under *What works* is implemented and tested. Held-out (test-split) results are **not yet available**: the benchmark freeze is pending approval (see `FREEZE.md`).

## Why
When a tool-using agent fails, a trace shows *what* happened, not *which step is responsible*. The first visible error is often not the cause. Re-running a "fixed" agent against replayed responses can falsely report success. Stateful tools and nondeterminism make honest reproduction hard.

AgentTrace answers four questions with explicit guarantees:
1. **Can I reproduce this run exactly?** Strict replay re-executes every tool against a restored state and fails closed at the first divergence.
2. **Which single step, if replaced, repairs the run?** Typed counterfactual interventions, each paired with a placebo control.
3. **Does my fix really work?** Regression execution runs the candidate freshly; it never reuses recorded responses.
4. **How good is a localizer?** A validated fault-injection benchmark with separate localization, repair and evidence metrics.

No novelty is claimed for replay-based failure attribution, which has substantial prior work.

## What works (v0.1.0rc1)
- **Tracing:**
  - versioned trace schema with an observable trace and a privileged ledger;
  - canonical JSON and SHA-256 fingerprints;
  - hash-chain integrity, plus an atomic JSONL store.
- **Sandbox environment:** synthetic customer support / order management with 5 tools, transactional commits, idempotency, snapshot/restore and 8 scenario templates.
- **Fault injection:** a serializable `FaultPlan` with stage-declared operators:
  - timeout before execution, lost acknowledgement after commit;
  - corrupted output, wrong retrieval;
  - wrong tool, wrong argument, decoy read, decision replacement.
- **Replay modes:**

  | Mode | What it does |
  |---|---|
  | `REPLAY_STRICT` | exact, verified replay |
  | `REPLAY_INTERVENE` | observation vs. execution replacement, trusted references only, a cassette fence, a fresh downstream run, same-type placebo, explicit `UNSUPPORTED` |
  | `REGRESSION` | fresh candidate runs from the scenario and environment fixture only |

- **Localizers:**
  - B1 earliest visible error, B3 rule-based, B4 earliest reference deviation, CF placebo-controlled counterfactual;
  - evidence labels `SUSPICION` / `REFERENCE_DEVIATION` / `INTERVENTIONAL_REPAIR` / `UNSUPPORTED`, run conclusion `NOT_ISOLATED`.
- **Benchmark and evaluation:**
  - AgentTrace-Synth v0: 67 validated instances, dev/test split by template;
  - `atrace bench run` with Metrics A/B/C, Wilson intervals, byte-identical canonical outputs and built-in correctness checks.

## Quickstart
Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv can install it). Verified on an 8 GB MacBook Air M2: offline, no GPU, no paid API.
```bash
uv sync --locked
make demo                          # scripted 3-minute tour (press Enter between steps)
DEMO_NONINTERACTIVE=1 make demo    # same, non-interactive
```
Individual commands:
```bash
uv run atrace scenarios                      # list scenario templates
uv run atrace run T1                         # clean run: trace + oracle verdict
uv run atrace inject T1-D1+F4                # record a fault-injected benchmark instance
uv run atrace show <run_id>                  # reload + integrity check
uv run atrace replay <run_id>                # strict replay verification
uv run atrace investigate <run_id> --markdown report.md
uv run atrace intervene <run_id> --seq 11 --type execution   # intervention + placebo
uv run atrace regress <run_id> --policy v2   # fresh candidate runs, no cassette reuse
uv run atrace bench run --split dev          # Metric A/B/C on the development split
```
A guided example is in [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md).

Exit codes:

| Command | Exit codes |
|---|---|
| `run` | 0 PASS, 1 FAIL, 2 error |
| `replay` | 0 VERIFIED, 1 DIVERGED, 3 CONFIG_MISMATCH, 4 INTEGRITY_ERROR |
| `intervene` | 0 completed, 5 UNSUPPORTED, 6 INVALID_COUNTERFACTUAL |
| `regress` | 0 deterministic candidate PASS, 1 otherwise |
| `bench run` | 1 on any correctness violation; 2 when the guarded test split refuses |

## Architecture
```mermaid
flowchart LR
  CLI[atrace CLI] --> BENCH[bench: generate / validate / evaluate / metrics]
  CLI --> LOC[localize: B1 B3 B4 CF]
  BENCH --> LOC
  LOC --> SVC[InterventionService]
  SVC --> REPLAY[replay: strict / counterfactual / regression]
  REPLAY --> RT[runtime: BoundaryGateway + AgentLoop]
  RT --> FAULTS[faults: FaultPlan operators]
  RT --> ENV[env: support sandbox]
  RT --> POL[policies: scripted v1 / v2]
  RT --> TRACE[trace: schema, canonical JSON, JSONL store]
```
Localizers see only the observable trace and the `InterventionService`, never labels, ledgers or fault plans. This is enforced by tests. Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Replay contracts: [`docs/REPLAY_SPEC.md`](docs/REPLAY_SPEC.md). Data contracts: [`docs/TRACE_SCHEMA.md`](docs/TRACE_SCHEMA.md).

## Results: development split only
From `evaluation/synth_v0-dev/table.md` (`atrace bench run --split dev`): 30 dev instances, **16 eligible** CAUSAL single-site instances. Each cell is k/n [Wilson 95% CI].

| Method | Top-1 (primary) | Top-3 | Top-1 same-step action (secondary) | Decoy ranked first |
|---|---|---|---|---|
| B1 | 8/16 [0.28, 0.72] | 8/16 [0.28, 0.72] | 14/16 [0.64, 0.97] | 0/3 |
| B3 | 8/16 [0.28, 0.72] | 9/16 [0.33, 0.77] | 14/16 [0.64, 0.97] | 0/3 |
| B4 | 13/16 [0.57, 0.93] | 16/16 [0.81, 1.00] | 13/16 [0.57, 0.93] | 3/3 |
| CF | 16/16 [0.81, 1.00] | 16/16 [0.81, 1.00] | 16/16 [0.81, 1.00] | 0/3 |
| B0 (random) | expected 0.12 | expected 0.35 | | |

- **Interventional repair (CF):** 16/16 failed runs repaired at the injected step. Placebo validity is 30/30, with 0 unsupported steps.
- **Replay cost:** CF averages 11.4 replays per investigation (max 16); B4 averages 9.0.
- **Correctness checks:**
  - strict replay 30/30 VERIFIED;
  - 0 false repairs on passing runs;
  - 0 cassette accesses after the intervention fence;
  - 13 regression runs constructed 0 cassettes.

**How to read this.** These are *development* results: the metric definitions were reviewed on this split. Top-1 measures agreement with the **injected step**, which is not unique causal attribution. n is small (16) and there are only 4 templates, so intervals are wide and paired tests are descriptive. CF's perfect dev score reflects that **trusted references exist for every step**, because the agent is scripted. Held-out results will be added only after the approved freeze.

## Limitations
- One synthetic domain and a deterministic scripted agent. Injected faults are not natural LLM failures.
- Trusted references exist only because the agent is scripted. For real LLM agents most interventions would be `UNSUPPORTED`. Treat CF results as an upper bound for settings where references exist.
- Some faults are visible in tool responses (inconsistent totals, the archived-policy flag), which helps B1/B3.
- Single-step interventions cannot isolate jointly sufficient faults (`NOT_ISOLATED`).
- Probabilistic regression is implemented but untested with a stochastic agent.
- The integrity chain detects accidental corruption, not a determined adversary.
- CI has been configured with pinned actions, but a green run on GitHub has not been observed for this release candidate.

## Development
```bash
make check          # ruff, format check, mypy --strict, pytest
make cov            # coverage with the CI Hypothesis profile
make reproduce-dev  # dev evaluation twice; canonical outputs must be byte-identical
make audit          # pip-audit of the locked dependencies
make verify-bench   # benchmark files == deterministic regeneration
```
Docs: [PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Replay spec](docs/REPLAY_SPEC.md) · [Trace schema](docs/TRACE_SCHEMA.md) · [Evaluation](docs/EVALUATION.md) · [Test plan](docs/TEST_PLAN.md) · [Decisions](docs/DECISIONS.md) · [Tasks](docs/TASKS.md) · [Release checklist](docs/RELEASE.md) · [Changelog](CHANGELOG.md)

## Phase 2 roadmap (not started)
- **2A, real LLM agent (local, free):**
  - a small quantized local model (≤3B, llama.cpp or Ollama) behind the existing `Policy` interface, with structured decisions;
  - recorded model decisions, strict replay without a model;
  - stochastic regression with Wilson intervals, and k-replay counterfactuals.
- **2B, framework integration:** a minimal LangGraph adapter onto the boundary gateway, and an investigation of a real (non-injected) failure.
- **2C, developer interface:** a FastAPI read-only API and a React + TypeScript viewer covering the run list, trace timeline with state transitions, counterfactual diff and evidence view.

## Licence
Not yet selected. Until a licence is chosen, this code must not be redistributed.
