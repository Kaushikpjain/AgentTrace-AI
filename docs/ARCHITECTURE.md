# Architecture

> Replay semantics: `REPLAY_SPEC.md` (authoritative). Data contracts: `TRACE_SCHEMA.md` (authoritative). Decisions: `DECISIONS.md`.

## 1. Style
A **modular monolith** (ADR-002): one Python package `agenttrace`, a CLI, no services, no database server, no containers. Everything runs in one process on an 8 GB laptop.

## 2. Components
| Package | Responsibility | Status |
|---|---|---|
| `agenttrace.trace` | Pydantic trace models, canonical JSON, fingerprints, semantic fingerprint, id generation, `TraceStore` protocol + `JsonlTraceStore` | Week 1 |
| `agenttrace.env.support` | Synthetic order-management state model, 5 tools, snapshot/restore/hash, JSON delta, declarative scenarios | Week 1 |
| `agenttrace.runtime` | `BoundaryGateway` (S1–S7 tool lifecycle, D1–D4 decision lifecycle, fault-hook seam), `AgentLoop`, `Policy`/`FaultHook` protocols, run assembly | Week 1 |
| `agenttrace.policies` | `ScriptedSupportPolicy` v1/v2, `ReferencePolicy` interface + gold reference | Week 1 |
| `agenttrace.evals` | Deterministic oracle (Week 1); validators (Week 3) | Week 1 / 3 |
| `agenttrace.cli` | `atrace scenarios`, `run`, `show` (Week 1); `replay`, `intervene`, `regress`, `inject`, `investigate`, `bench` (later) | Week 1+ |
| `agenttrace.replay` | Cassette, ExactReplayer, CounterfactualRunner, RegressionRunner, fidelity | Weeks 2–3 |
| `agenttrace.faults` | Stage-declared fault operators, FaultPlan, labels | Week 3 |
| `agenttrace.localize` | Baselines B1/B3/B4, CF localizer | Week 3 |
| `agenttrace.bench` / `report` | Generator, validator, metrics A/B/C, reports | Weeks 3–4 |

## 3. Dependency direction
```
cli ─▶ bench/report ─▶ localize ─▶ replay ─▶ runtime ─▶ policies ─▶ env ─▶ trace
                                   │          │                    ▲
                                   └─▶ faults ┘   evals ───────────┘
```
- `trace` imports nothing from the project.
- `env` imports only `trace` (canonical/fingerprints).
- `policies` imports `runtime.types` (Decision/Observation) and `env.support` models; `runtime` never imports `policies` (the `Policy` protocol lives in `runtime.types`).
- `runtime` imports `trace` and `env.base`/`env.delta` (environment-agnostic), never the CLI or a concrete environment.
- `runner.py` is the only module that wires the concrete support environment, oracle and policies together.
- `localize` must never import the ledger/label loaders (C3; test-enforced from Week 3).
- `env/` and `policies/` must not import nondeterministic or I/O modules (`random`, `time`, `uuid`, `datetime`, `secrets`, `subprocess`, `socket`, HTTP clients). This is test-enforced from Week 1.

## 4. Data flow (Week 1, RECORD)
```
Scenario JSON ─▶ Scenario model ─▶ snapshot bytes ─▶ restore ─▶ live state (owned by the gateway)
                                                                    │
AgentLoop: for each step ─▶ AGENT_STEP span event                   │
   gateway.decide(policy, task, history) ── D1–D4 ──▶ DECISION event + ledger
   if FINAL: stop
   gateway.call_tool(decision) ── S1 validate ─ S2 pre-faults ─ S3 execute on working copy
                                  ─ S4 commit/rollback ─ S5 post-faults ─ S6 deliver ─ S7 record
   history.append(Observation(seq, tool, args, delivered response))
Oracle(final state) ─▶ outcome ─▶ RunFooter (+ integrity chain) ─▶ JsonlTraceStore.save (atomic)
```

## 5. Execution lifecycle and state ownership
- **One live state per execution.** The gateway owns it. It is created by restoring the scenario snapshot, so the scenario object is never mutated.
- **Tools never touch the live state.** They receive a deep working copy. The gateway alone commits, by swapping the reference (atomic).
- **Read-only tools** are checked after execution; a mutation raises `ReadOnlyToolMutatedState`.
- **Policies are pure:** decisions depend only on (task, history). They hold no hidden state across runs.
- **Faults** are applied only through the `FaultHook` seam at the declared stage (`DECISION`, `PRE_EXECUTION`, `POST_EXECUTION`). Week 1 ships a no-op hook; tests use small test-only hooks to verify lifecycle semantics.
- **Delivered vs. raw:** the agent sees only delivered values. Raw outputs and fault applications go to the ledger.

## 6. Persistence
`JsonlTraceStore(root)` implements the `TraceStore` protocol: `save`, `load_trace`, `load_ledger` (privileged), `list_run_ids`, `exists`. Writes are atomic (temp dir + rename) and recordings are immutable. Loads validate schema, completeness and the integrity chain (TRACE_SCHEMA §7). Default root: `./runs`, overridable with `--runs-dir` or `ATRACE_RUNS_DIR`. The `runs/` directory is git-ignored.

## 7. Extension points
| Seam | MVP | Later |
|---|---|---|
| `Policy` protocol | scripted v1/v2 | `LocalLLMPolicy` (Phase 2A), LangGraph adapter (2B), hosted with a budget guard |
| `FaultHook` protocol | no-op + test hooks | `FaultPlan`-driven operators (Week 3) |
| `TraceStore` protocol | JSONL files | SQLite, PostgreSQL, HTTP exporter to FastAPI (2C) |
| Tool registry (`ToolSpec`) | 5 support tools | external benchmark environments (AgentDojo adapter) |
| Oracle | support oracle | benchmark-native oracles |
| Exporters | — | OpenTelemetry GenAI-aligned export |

## 8. Repository layout (as implemented; supersedes PLAN §16)
```
pyproject.toml  uv.lock  .python-version  .gitignore  README.md
docs/        PLAN_v0.2.1.md  PRD.md  ARCHITECTURE.md  REPLAY_SPEC.md  TRACE_SCHEMA.md
             TEST_PLAN.md  TASKS.md  DECISIONS.md  archive/
src/agenttrace/
  __init__.py  cli.py  runner.py (composition root: env + oracle + policy → runtime)
  trace/     canonical.py  fingerprint.py  ids.py  schema.py  integrity.py  semantic.py  store.py
  env/       base.py (ToolSpec/ToolResult contract)  delta.py (JSON diff)
  env/support/  models.py  tools.py  snapshot.py  scenario.py  scenarios/T1..T8.json
  runtime/   types.py (Decision, ToolResponse, Observation, Policy)  faults.py (FaultHook)
             gateway.py (S1–S7, D1–D4)  loop.py (run_episode)
  policies/  support_scripted.py (v1, v2)  reference.py (ReferencePolicy, gold reference)
  evals/     oracle.py
tests/       unit/  integration/  helpers.py  hooks.py (test-only fault hooks)  conftest.py
benchmarks/  (Week 3: generated fault instances, labels, splits)
.github/workflows/ci.yml
```
