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
| `agenttrace.evals` | Deterministic oracle (Week 1); observable-trace validators (`validators.py`, Week 3) | Week 1 / 3 |
| `agenttrace.cli` | `atrace scenarios`, `run [--fault-plan]`, `show` (Week 1); `replay` (Week 2); `intervene`, `regress`, `investigate`, `bench` (later) | Week 1–2 |
| `agenttrace.replay` | `Cassette` (positional, consume-once, fence), `StrictReplayGateway`, `replay_strict`/`replay_run`, config check, fidelity (Week 2); `counterfactual` (typed interventions, placebos, reference probe), `regression`, `service` (InterventionService) (Week 3) | Week 2–3 |
| `agenttrace.faults` | Registered stage-declared operators (T0, F3, F5, `REPLACE_DECISION` in Week 2; F1, F2, F4, D1 in Week 3), `PlanFaultHook`, `validate_plan` | Week 2–3 |
| `agenttrace.localize` | `observe` (symptom, argument-origin chain), baselines B1/B3/B4, CF localizer, Markdown report; reads only `Trace` + `InterventionService` | Week 3 |
| `agenttrace.bench` | Candidate generator, privileged validator, benchmark files (manifest, instances, labels, rejected); metrics A/B/C in Week 4 | Week 3 |
| `agenttrace.cli_diagnose` | `inject`, `intervene`, `regress`, `investigate`, `bench generate/verify/list` | Week 3 |

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
- `runner.py` is the only module that wires the concrete support environment, oracle and policies together. It also builds the support `ReplayContext` consumed by the environment-agnostic replay engine.
- `replay` depends on `runtime` (it subclasses `BoundaryGateway` through the `_produce_decision` / `_before_tool` / `_after_tool` / `finish` seams) and never on a concrete environment.
- `localize` must never import the store's privileged loaders, `bench`, `faults` or `runner` (C3; AST-enforced). It reaches interventions only through `replay.service.InterventionService`.
- `bench` is privileged (reads ledgers and labels) and may import `localize.observe` for symptom computation; the reverse is forbidden.
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

## 4b. Data flow (Week 2, REPLAY_STRICT)
```
store.load_record (schema + fingerprints + hash chain + fault-plan hash) ─▶ RunRecord
check_config(header, fault_plan, ReplayContext)  ── mismatch ─▶ CONFIG_MISMATCH (nothing executed)
build_episode(header, plan) ─▶ fresh initial state + PlanFaultHook(plan)
run_episode(mode=REPLAY_STRICT, policy=ReplayPolicyGuard, gateway=StrictReplayGateway(cassette))
   decisions: cassette.expect(seq, DECISION, request_fp) ─▶ recorded delivered decision (policy never called)
   tools:     cassette.expect(seq, TOOL, name, request_fp) ─▶ re-run S1–S7 with the plan
              ─▶ verify raw result/fault applications, state transition, delivered response
   first mismatch ─▶ DivergenceDetected ─▶ status DIVERGED, outcome NOT_EVALUATED
   loop end: unconsumed entries ─▶ TRUNCATED; then final state hash + outcome compared
ReplayReport(verdict, divergence, fidelity, policy_calls, cassette consumed/entries)
```

## 4c. Data flow (Week 3)
```
REPLAY_INTERVENE (intervene):
  precheck(target, type, source, privilege, policies) ── fail ─▶ UNSUPPORTED(reason)
  strict prefix (seq < target) ─▶ target: consume entry, apply typed replacement
     OBSERVATION: original lifecycle (faults on) + delivered value replaced (consistency-checked)
     EXECUTION:   lifecycle with faults off (reference) / on (placebo)
  fence: cassette.close() ─▶ live suffix: real policy + sandbox tools + recorded fault plan
  oracle on new state ─▶ CounterfactualResult; experiment = intervention + same-type placebo
REGRESSION: header + env fixture (DECISION faults dropped) ─▶ fresh runs ×N (no cassette)
  ─▶ DETERMINISTIC_PASS/FAIL (equal semantic fingerprints) ─▶ FIXED / STILL_FAILING / ...
Localization: Trace + support_flags ─▶ B1/B3;  InterventionService(record) ─▶ B4 (probes), CF
  (probes + experiments) ─▶ Investigation (ranking, evidence labels, repair sites, replays)
Benchmark: generate (enumerate templates × operators) ─▶ validate (record, strict replay,
  faults fired, label, clean-value confirmation) ─▶ manifest/instances/labels/rejected
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
             gateway.py (S1–S7, D1–D4, replay seams, DivergenceDetected)  loop.py (run_episode)
  faults/    operators.py (registered operators)  plan.py (PlanFaultHook, validate_plan)
  replay/    cassette.py  exact.py (strict replay, config check, report)  fidelity.py
             counterfactual.py  regression.py  service.py
  localize/  observe.py  baselines.py (B1, B3, B4)  counterfactual.py (CF)  report.py  types.py
  bench/     generate.py  validate.py (privileged)  io.py
  cli_diagnose.py (Week 3 commands)
  policies/  support_scripted.py (v1, v2)  reference.py (ReferencePolicy, gold reference)
  evals/     oracle.py  validators.py
tests/       unit/  integration/  acceptance/  property/  helpers.py  hooks.py  plans.py  replay_helpers.py  conftest.py
examples/fault_plans/  lost_ack_refund.json  timeout_before_refund.json  corrupt_order_total.json
benchmarks/synth_v0/   manifest.json  instances.jsonl  labels.jsonl (privileged)  rejected.jsonl
benchmarks/  (Week 3: generated fault instances, labels, splits)
.github/workflows/ci.yml
```
