# AgentTrace AI — Technical & Research Plan v0.2

> Revision of v0.1 (2026-11-22) following the joint review with ChatGPT. Status: **PLAN ONLY**. No code, dependencies or repository yet.
> Labels: **[F]** verified via web search (2026-11-22) · **[K]** prior knowledge, needs **[verify]** · **[R]** recommendation · **[A]** assumption · **[E]** unverified estimate · **[Q]** remaining decision.

---

## 1. Executive summary

AgentTrace AI keeps its long-term vision: *a reliability, security-testing and failure-diagnosis platform for tool-using AI agents*. v0.2 reorganizes it into three levels and shrinks Level 1 to fit **60–70 focused hours on an 8 GB MacBook Air M2 with no paid APIs**.

**Level 1 (four-week core MVP)** is a CLI-first Python system. Its parts:
- One synthetic **customer-support / order-management** environment with 5 sandboxed tools and a deterministic scripted agent.
- A versioned trace schema persisted as JSONL.
- A **rigorously specified replay engine** with three separate contracts: **exact replay**, **counterfactual replay** and **regression execution**.
- Five fault operators plus one harmless "decoy" operator, applied to a ~50-case synthetic benchmark with validated ground-truth fault locations.
- Deterministic oracles and validators.
- Four baseline localizers and a placebo-controlled single-step counterfactual localizer.
- An honest results table, reproducible from one command.

The engineering contribution is **replay correctness with explicit invariants and a 15-test acceptance matrix**. No research novelty is claimed. Budget-aware localization stays as Level 3 research and is kept in a **separate private repository** pending prior-art review and IPR consultation.

## 2. Changes from v0.1

| Area | v0.1 | v0.2 | Why |
|---|---|---|---|
| MVP effort | 160–225 h | **~66 h planned + ~14–18 h buffer**; 50 h + 6 h buffer fallback | User has 56–84 h |
| Domains | 2 | **1** (customer support / orders) | Strongest state-based oracle; mutating tools exercise state handling |
| Policies | scripted + local LLM + hosted | **scripted only** (plus a scripted *reference* policy) | 8 GB RAM, zero API budget, determinism needed for ground truth |
| Replay | one engine, modes loosely defined | **3 explicit contracts**, state re-application, cassette fence, identity layers, fidelity metrics, 15 acceptance tests | Replay correctness is the foundation |
| Faults | 10 operators, 600–900 instances | **5 operators + 1 decoy, ~40–60 instances** | Time; small but validated beats large and noisy |
| Localization | 5 baselines + counterfactual + adaptive | 4 baselines (+ analytical random) + **placebo-controlled counterfactual** | Adaptive allocation moves to Level 3 |
| Minimization (ddmin) | MVP | **Level 2** | Not needed for replay correctness |
| Regression | full management | **regression *execution* contract only** (needed for the demo and test #14); management moves to Level 2 | Keeps the identity; avoids the scope |
| Storage | SQLite→Postgres, blob store | **JSONL files behind a `TraceStore` protocol** | Inspectable, zero setup; SQLite/Postgres later |
| API/UI | FastAPI + React dashboard | **CLI (Typer + Rich)**; FastAPI/React in Level 2 | Not needed to demonstrate the core |
| Docker | Compose | **none in MVP** (Docker Desktop VM costs RAM [K]) | 8 GB machine |
| Security | ~20–40 injection cases | **security-aware engineering only** (sandbox, permission checks, tool-output manipulation fault); injection suite moves to Level 2 | A scripted policy cannot be meaningfully prompt-injected; that needs an LLM |
| IP | single repo, research in private branch | **public foundation repo (Apache-2.0) + separate private research repo** | Cleaner disclosure control |

## 3. Confirmed user constraints
- MacBook Air M2, **8 GB** unified memory, no NVIDIA GPU; prefer lightweight, CPU/memory-efficient tools.
- **2–3 h/day, four weeks, 56–84 h total**; target 60–70 focused hours. Other projects and placement prep run in parallel.
- Goal: a credible, resume-worthy AI engineering project (agents, evaluation, observability, testing, backend, failure diagnosis).
- Accepted: single-agent tool use; replay-based localization is not novel; budget-aware/statistical localization = longer-term research.
- Patent: keep the option open, assume nothing, keep inventive work separate from the public foundation, do not publish sensitive details before prior-art review and IPR consultation.
- **Zero paid API budget.** Hosted models are optional and disabled by default.
- No second human annotator is assumed.

## 4. Final MVP problem statement

> Given a deterministic tool-using agent operating on a sandboxed, stateful environment, AgentTrace must (1) record every execution at its nondeterministic boundaries; (2) **reproduce** any recorded execution exactly, including its environment state transitions, or report precisely where and why it cannot; (3) **re-execute** a recorded execution with one step's output replaced by a trusted reference and evaluate the new outcome with the same oracle, under a placebo control; (4) **execute** a scenario fresh against a changed agent configuration without reusing recorded responses; and (5) using (1)–(3), rank the steps of a failed run by how likely they are to be responsible, labelling each claim as *suspicion* or *interventional evidence*. Accuracy is measured against **validated injected faults** with known locations.

Definition retained from v0.1 (aligned with Who&When / AgenTracer / ReplayRCA): step *e* is an **interventional cause** if substituting its trusted reference output, then re-executing downstream, turns *fail* into *pass*, **and** the placebo (substituting its original output through the same machinery) still fails. The **decisive step** is the earliest such step.

## 5. Scope by level

| Capability (vision items 1–14) | L1: 4-week MVP | L2: Engineering expansion | L3: Research & innovation |
|---|---|---|---|
| 1 Structured tracing | Pydantic schema v1, JSONL, CLI viewer | OTel GenAI-aligned export, OTLP ingest, SQLite→Postgres, blob store | — |
| 2 Deterministic record/replay | **Exact replay contract, re-application, divergence detection** | Playback-with-recorded-deltas for non-re-executable tools; LLM cassettes | Replay fidelity study on local LLMs |
| 3 Counterfactual interventions | **Single-step, placebo-controlled, deterministic** | Multi-step / pairwise interventions; stochastic (k-replay) mode | Adaptive allocation, statistical stopping |
| 4 Fault injection + ground truth | 5 operators + decoy, ~50 instances | 10+ operators, interaction faults, partial-commit faults | Fault realism study |
| 5 Reliability evaluation | Oracle + arg/permission/output validators | Retrieval metrics, cost/latency, calibrated LLM-judge | Judge reliability study |
| 6 Classification & localization | Rule classifier, 4 baselines, CF localizer | SBFL (Ochiai), ML clustering of natural failures | Provenance-guided pruning, cost–accuracy Pareto |
| 7 Scenario minimization | — (design only) | Hierarchical ddmin with failure-signature preservation | Flakiness-bounded minimization |
| 8 Regression testing | **Regression execution contract** (fresh run, same oracle) | Versioned tests, suites, history, recurrence signatures, CI action | Flakiness-aware tests |
| 9 Security testing | Sandbox, permission checks, tool-output manipulation fault | AgentDojo adapter, injection suite, defense comparison | — |
| 10 Dashboards | CLI + Markdown investigation report | FastAPI + React (timeline, DAG, investigation) | — |
| 11 Framework integrations | Stable `Policy`/`Tool`/`Boundary` interfaces | LangGraph adapter | — |
| 12 Local/hosted LLMs | Interface only | Ollama/llama.cpp policy (small models), opt-in hosted with BudgetGuard | — |
| 13 Budget-aware localization | — | — | **Primary research** (private repo) |
| 14 Reproducible benchmarking | One-command results table, frozen splits | External benchmarks (AgentDojo, τ-bench subset, BFCL subset) | Released benchmark + paper |

**Explicitly not in L1:** React/React Flow, FastAPI, PostgreSQL, Redis/queues, Docker, LangGraph, OTel ingestion, AgentDojo, injection suites, LLM-as-judge, any LLM inference, multi-agent, RBAC, hosted deployment, adaptive allocation, ddmin, automated test generation, large datasets.

## 6. Revised architecture

Modular monolith: one Python package plus a CLI. Dependencies point downward only (enforced with `import-linter`, or a simple test that inspects imports).

```
                         ┌──────────────────────── CLI (Typer + Rich) ─────────────────────────┐
                         │ run · show · replay · intervene · regress · inject · investigate ·  │
                         │ bench                                                               │
                         └───────┬──────────────────┬──────────────────┬───────────────────────┘
                                 │                  │                  │
                  ┌──────────────▼───┐   ┌──────────▼────────┐  ┌──────▼─────────────┐
                  │ localize/        │   │ bench/            │  │ report/            │
                  │ baselines, rules,│   │ generator,        │  │ markdown/console   │
                  │ counterfactual   │   │ validator, runner,│  │ investigation      │
                  └───────┬──────────┘   │ metrics           │  └────────────────────┘
                          │              └──────┬────────────┘
                  ┌───────▼─────────────────────▼──────────────────────────────┐
                  │ replay/  ExactReplayer · CounterfactualRunner ·            │
                  │          RegressionRunner · Cassette · Divergence · Fidelity│
                  └───────┬───────────────────────────────┬────────────────────┘
                          │                               │
        ┌─────────────────▼──────────────┐     ┌──────────▼─────────┐   ┌────────────────┐
        │ runtime/  AgentLoop            │     │ faults/            │   │ evals/         │
        │  BoundaryGateway (decision,    │◀────│ FaultPlan, operators│  │ Oracle,        │
        │  tool, clock, idgen)           │     │ (transform at      │   │ validators,    │
        │  Recorder hooks                │     │  boundaries)       │   │ classifier     │
        └───────┬──────────────┬─────────┘     └────────────────────┘   └────────────────┘
                │              │
     ┌──────────▼───┐   ┌──────▼──────────────────┐        ┌──────────────────────────────┐
     │ policies/    │   │ env/ (support domain)   │        │ trace/ schema (Pydantic v2), │
     │ Scripted v1, │   │ State model, 5 tools,   │        │ canonical JSON, fingerprints,│
     │ v2, Reference│   │ snapshot/restore, hash  │        │ TraceStore protocol → JSONL  │
     └──────────────┘   └─────────────────────────┘        └──────────────────────────────┘
```

**Stable interfaces (the seams for L2/L3):**
| Interface | MVP implementation | Later implementations |
|---|---|---|
| `Policy.decide(history) -> Decision` | `ScriptedPolicy v1/v2`, `ReferencePolicy` | `OllamaPolicy`, `HostedPolicy` (+BudgetGuard), LangGraph adapter |
| `Tool.execute(state_view, args, ctx) -> ToolResult` (transactional) | 5 in-memory support tools | External-API tools in L2 playback mode |
| `BoundaryGateway` (single choke point for decision/tool/clock/idgen) | in-process | OTel span emitter, LangGraph callback bridge |
| `TraceStore` | `JsonlTraceStore` | `SqliteTraceStore`, `PostgresTraceStore`, HTTP exporter → FastAPI |
| `Oracle`, `Validator` | declarative predicates | LLM-judge (calibrated), benchmark-native oracles |
| `Localizer.rank(trace, ctx) -> Ranking` | 4 baselines + CF | SBFL; private research localizers loaded via a plugin entry point |
| `Environment` (snapshot/restore/hash) | support env | AgentDojo env adapter |

## 7. Replay mode specifications (three separate contracts)

**Boundaries in the sample agent** (everything nondeterministic or externally observable passes through `BoundaryGateway`):
| Boundary | Example | Deterministic in MVP? | Recorded value |
|---|---|---|---|
| `decision` | policy chooses next tool + args, or FINAL | yes (scripted), but treated as an "LLM boundary" | the **delivered** Decision (post fault-injection) |
| `tool` | `issue_refund(order_id, amount, idem_key)` | yes, given state | delivered ToolResult (post fault-injection), state hash before/after, state delta |
| `clock` | `now()` | injected | value returned |
| `idgen` | refund id, ticket note id | injected counter | value returned |

No randomness is used by the env or policies. Money uses `Decimal`. All serialization goes through **canonical JSON** (sorted keys, fixed Decimal formatting, no floats, UTF-8 NFC).

### 7.1 Contract A — Exact replay (`REPLAY_STRICT`)
- **Preconditions:** the run's `config_fingerprint` (schema version, scenario id+version+initial-state hash, policy id+source hash, tool-manifest hash, fault-plan hash, oracle version) equals the current code's fingerprint; otherwise **refuse with `CONFIG_MISMATCH`** before executing anything.
- **Behaviour:**
  - The environment is restored from the scenario's initial snapshot (a fresh deep copy).
  - The agent loop runs. At each boundary event *i*, the gateway checks `(seq, boundary, name, request_fp)` against cassette entry *i*. Any mismatch ends the replay with `DIVERGED` and a diff.
  - **Decision / clock / idgen:** the delivered value comes from the cassette. The policy is not consulted, so no model is called.
  - **Tool:** the tool is **re-executed** in the sandbox on the restored state (state re-application). The raw result goes through the same fault transform as in the original run. The resulting delivered value must equal cassette response *i*, and `state_hash_after` must equal the recorded value. Otherwise the replay ends with `DIVERGED(kind=RESPONSE|STATE)`.
  - Cassette entries are **consumed exactly once, in order**. Leftover entries at the end produce `DIVERGED(kind=TRUNCATED)`. A request past the end produces `DIVERGED(kind=EXTRA_EVENT)`.
- **Guarantees:** no model calls; no side effects outside the in-memory sandbox copy; a final state reconstructed by re-application and *verified* at every mutation; a fidelity report (§8.4).
- **Why re-application, not playback [R]:** returning recorded tool outputs alone does **not** reproduce the final environment state, so the oracle could not be re-evaluated. Re-execution with verification reproduces the state *and* tests tool determinism. L2 adds `PLAYBACK_WITH_DELTAS` for tools that cannot be re-executed (external APIs): recorded state deltas are applied instead, with a weaker guarantee labelled `RECONSTRUCTED`.

### 7.2 Contract B — Counterfactual replay (`REPLAY_INTERVENE`)
- **Input:** recorded run *R*, target event *e\** (identified by `seq` in *R*), replacement value *v* with provenance `{REFERENCE_TOOL, REFERENCE_POLICY, INJECTION_CLEAN_VALUE, ORIGINAL (placebo)}`.
- **Phases:**
  1. **Prefix** (`seq < e*`): identical to Contract A. A mismatch yields `INVALID_COUNTERFACTUAL(prefix_diverged)`.
  2. **Intervention** (`seq = e*`): the request must match *R*'s request at *e\**.
     - Decision boundary: deliver *v* as the decision.
     - Tool boundary: re-execute the tool (so its state mutation happens exactly as the clean tool would perform it), suppress the fault transform at this event only, and deliver *v*. For `REFERENCE_TOOL`, *v* is by definition the clean tool's output. The intervention is recorded as an explicit `intervention` field on the event and in the run header.
  3. **Cassette fence:** after *e\**, the cassette is **closed**. The handle is dropped and any lookup raises an error. Every downstream decision is recomputed by the live policy, and every downstream tool runs live in the sandbox. The fault plan stays active for *other* fault sites; triggers are predicates (e.g. "1st call to `get_order`"), not seq numbers, so they apply correctly to a changed path (documented).
  4. **Oracle:** evaluated on the *new* final state, using the same oracle version.
- **Output:** a new run *R′* with `mode=REPLAY_INTERVENE`, `parent_run_id=R`, the intervention record, its outcome, and an alignment report against *R* (§8.3, reporting only).
- **Invariant:** *R′*'s prefix is identical to *R*'s prefix (responses, sequence, state hashes). No cassette response is ever served at or after *e\**.

### 7.3 Contract C — Regression execution (`REGRESSION`)
- **Input:** a scenario + an **environment fixture plan**, plus a candidate agent configuration (policy version, prompt/source hash, tool implementations).
  - The fixture plan contains *environment-side* faults only: tool-output corruption, timeouts, wrong retrieval. Agent-side faults (wrong tool, bad args) are not fixtures; they represent agent bugs, which the candidate agent itself must not reproduce.
- **Behaviour:** a fresh execution from the initial snapshot. **No cassette object is constructed or passed in.** The runner receives a `TraceStore` that raises if asked for cassettes (enforced in the test). The same declared oracle version is applied.
- **Verdict:**
  - `DETERMINISTIC_PASS` / `DETERMINISTIC_FAIL` when the policy declares itself deterministic **and** two independent executions produce identical trace fingerprints.
  - Otherwise `PROBABILISTIC(pass_rate, Wilson CI, n)`. This path exists only from L2, once LLM policies are added.
- **Comparison report:** baseline vs. candidate outcome, the violated oracle clauses, and a first-divergence point. It **never** claims "fixed" from a replayed cassette. Attempting `REPLAY_STRICT` of a v1 run under a v2 config yields `CONFIG_MISMATCH` (test #14).

## 8. State restoration and divergence handling

### 8.1 Environment state model
- `SupportState` (Pydantic, frozen): `customers`, `orders`, `refunds`, `tickets`, `policy_docs`, `idempotency_log`, `audit` (an append-only list of tool invocations).
- **Snapshot** = canonical JSON bytes. **Restore** = parse into a new object, so there are no shared references. **Hash** = sha256 of the canonical JSON. States are a few KB, so copies are cheap.
- Each execution owns exactly one state instance. Module-level mutable state is forbidden, and a test checks for it.

### 8.2 Tool execution semantics
| Concern | Rule |
|---|---|
| Mutating calls | A tool receives a *working copy*. On success it returns `(result, new_state, delta)`, and the gateway commits atomically: it replaces the state, appends the audit entry, and records `state_hash_before/after` + `delta`. |
| Failed calls (validation error, business-rule error) | No commit. The state hash is unchanged. The result is a structured `ToolError{type, message}`, recorded as the response. |
| Partial execution | Impossible by construction in L1 (all-or-nothing commit). "Partial commit" becomes a fault operator in L2. |
| Timeouts | Simulated only by the fault layer. **`TIMEOUT_BEFORE_COMMIT`**: the tool is not executed and a timeout is delivered. **`TIMEOUT_AFTER_COMMIT`** (lost ack, operator F5): the tool commits and the agent receives a timeout anyway. Both are recorded with the true state hash, so replay verifies them. |
| Retries | Each attempt is a separate `tool` event with `attempt=n` and its own seq. The retry policy belongs to the agent (policy v1 vs. v2), never to the gateway. |
| Idempotency | Mutating tools accept `idempotency_key`. The sandbox records keys in `idempotency_log`. A duplicate key returns the original result without a second mutation. Policy v1 omits keys and v2 uses them, which is the regression demo. |
| Side-effect ordering | The order of commits is the order of `seq`. The state-hash chain makes any reordering detectable (test #7/#8). |
| Interrupted replay | A replay operates on an in-memory copy. Results are written via temp file + atomic rename. An interrupted replay leaves nothing persisted except, optionally, a `status=INTERRUPTED` header. Stored recordings are immutable (append-only, never rewritten). |

**State-transition policy [R]:** state transitions are **re-applied** (tools re-executed) in exact and counterfactual replay, and **verified** against the recorded `state_hash_after` and `delta`. Recorded deltas are stored to support the L2 reconstruction mode and diffs, never as a silent substitute.

**Exact-replay invariant:** for every boundary event *i* of original run *R* and replay *P*: `boundary, name, request_fp, delivered_response_fp, state_hash_before, state_hash_after` are equal; `len(P) = len(R)`; `final_state_hash(P) = final_state_hash(R)`; `outcome(P) = outcome(R)` (same violated clauses).

### 8.3 Step identity layers
| Layer | Field | Stable across | Used for |
|---|---|---|---|
| Execution-specific id | `span_id` (UUIDv7) | nothing (new per execution) | storage keys, parent links |
| Recorded sequence number | `seq` (0..n, per run, assigned by the gateway) | exact replays | **cassette matching in the prefix** (authoritative) |
| Stable logical identity | `logical_key = "{step_index}:{boundary}:{name}#{occurrence}"` | exact replays; **not** stable after a branch | human readability, reports, fault triggers (as a predicate), cross-run display |
| Request fingerprint | `request_fp = sha256(canonical(request))` (for decisions: canonical history + policy id; for tools: name + args + tool version) | identical requests | validating that a match is legitimate |
| Response fingerprint | `response_fp` | identical responses | fidelity metrics |

**Analysis of branching [R].** When an intervention changes the number, order or arguments of calls, or adds branches, repeated calls or a different length, `logical_key`s and `seq`s after the change no longer correspond to the original. Any strategy that keeps looking up cassette entries after the change (by logical key or by request hash) risks serving the wrong recorded response. For example, the 2nd `get_order` call in the new path might match a recorded 2nd `get_order` call made with different state. Therefore:
1. Cassette lookups are **positional (`seq`) and require all of `boundary, name, request_fp` to match**. They are permitted **only** in exact replay and in the counterfactual prefix.
2. **Fence** at the intervention point: the downstream path always executes live.
3. Any mismatch is **fatal** (`DIVERGED`) and the system never falls back to a live call. A live fallback would silently mix recorded and fresh behaviour.
4. **Post-branch alignment is reporting-only:** an LCS/Needleman-Wunsch alignment over `(boundary, name, normalized args)` shows which steps were added, removed or changed between *R* and *R′*.

### 8.4 Replay fidelity metrics (each reported separately)
| Metric | Definition | L1 requirement (scripted policy) |
|---|---|---|
| Response equality rate | matched delivered-response fingerprints / boundary events | = 1.0 on every unmodified exact replay |
| Event-sequence agreement | exact equality of the `(boundary, name, request_fp)` sequence (bool), plus LCS ratio | true / 1.0 |
| State-transition agreement | matched `state_hash_after` / mutating events | = 1.0 |
| Final-state equality | `final_state_hash` equal (bool) | true |
| Outcome agreement | same pass/fail and same violated clauses | true |
| Divergence rate | DIVERGED replays / replays attempted, reported separately for **unmodified** inputs (target 0) and **deliberately perturbed** inputs (target: 100% detected, with the correct divergence kind) | as stated |

These are **requirements checked by tests**, not results claimed in advance. Any violation on unmodified runs is a bug. For future LLM policies, *cassette playback* (exact replay, still deterministic) is reported separately from *fresh inference* (regression/counterfactual suffix, stochastic).

### 8.5 Counterfactual validity
A replacement value is **trusted** only if it comes from:
1. `REFERENCE_TOOL`: re-executing a deterministic sandbox tool with the same args on the same pre-state, without the fault transform.
2. `REFERENCE_POLICY`: the scripted **reference policy** (the gold trajectory generator for the scenario), queried with the *recorded* prefix history.
3. `INJECTION_CLEAN_VALUE`: the pre-injection value captured by the fault layer. This is used only for **label validation**, never by localizers, to avoid leakage.

For natural failures with no reference, the result is `NO_TRUSTED_REFERENCE` and no interventional claim is made. References are never fabricated (e.g. by an LLM).

**Placebo control:** for every intervention, also run `REPLAY_INTERVENE` with `v = ORIGINAL`. Under a deterministic policy, the placebo must reproduce *R*'s outcome and final state hash. Otherwise the result is `INVALID_COUNTERFACTUAL(machinery)`, which signals a bug. An intervention is tier **INTERVENTIONAL** only if the reference repairs the run (pass) **and** the placebo fails. In L2/L3 stochastic settings this becomes rates with CIs over *k* replays.

**Single-step limitations:**
- With two *jointly necessary* faults, each single intervention repairs, so both are flagged and the earliest is reported as decisive.
- With two *individually sufficient* faults, no single intervention repairs, so the result is `NOT_ISOLATED_BY_SINGLE_STEP`.
- Pairwise interventions and Shapley-style estimates (as in Causal Agent Replay [F]) are L2/L3. The L1 benchmark keeps ≤4 two-fault cases, **reported separately** to document this limitation.

## 9. Trace schema v1 (Pydantic, versioned)

```
RunHeader:   schema_version "1.0" · run_id · mode {RECORD|REPLAY_STRICT|REPLAY_INTERVENE|REGRESSION}
             · parent_run_id? · scenario {id, version, initial_state_hash}
             · agent {policy_id, policy_version, source_hash} · tool_manifest_hash · fault_plan_hash?
             · oracle {id, version} · config_fingerprint · intervention? {target_seq, logical_key,
             source, value_fp} · started_at(UTC) · status {COMPLETED|DIVERGED|INVALID_COUNTERFACTUAL|
             CONFIG_MISMATCH|INTERRUPTED|MAX_STEPS} · divergence? {seq, kind, expected_fp, actual_fp}
Span/Event:  span_id · parent_span_id? (agent_step span → its decision/tool events) · run_id · seq
             · step_index · logical_key · boundary {agent_step|decision|tool|clock|idgen}
             · name · request (inline canonical JSON) · request_fp · response · response_fp
             · status {ok|error|timeout} · error? {type, message} · attempt · idempotency_key?
             · state_hash_before? · state_hash_after? · delta? · intervened: bool · t_mono_ns (info only)
RunFooter:   final_state_hash · outcome {pass|fail, violated_clauses[{clause_id, symptom_seq}]}
             · fidelity? (replay modes) · totals {events, tool_calls, decisions, wall_ms}
             · integrity {event_count, hash_chain_root}
```

- **Ground-truth isolation:** fault metadata (operator, site, clean value) is written to a **sidecar** `labels.json`, never into the trace models given to localizers. The localizer API signature takes `Trace` only, so leakage is impossible by type.
- **Input/output references:** inline payloads in L1, because they are small. Each has a fingerprint so L2 can move payloads to a content-addressed blob store without changing semantics.
- **Redaction hook:** a `Redactor` interface exists and is applied before persistence; L1 data is synthetic, so the default is a no-op with a canary test. Real redaction rules arrive in L2.
- **Ordering:** `seq` is authoritative; timestamps are informational only.
- **Integrity:** a hash chain over `(seq, event_fp)`, verified on load. It detects truncation and corruption, but it is not a security control.
- **Versioning:** semver; minor = additive; the loader rejects unknown majors.
- **Persistence:** `runs/<run_id>/{header.json, events.jsonl, footer.json}`. `cassette` = the event list of a RECORD run (no separate format).

## 10. Minimal fault-injection design

The fault layer sits inside `BoundaryGateway` as **transforms** on delivered values (or as execution modifiers for timeouts), driven by a declarative `FaultPlan` of triggers (predicates over boundary, name, occurrence, args).

| Op | Boundary | Mechanism (example) | Failure mechanism exercised | Expected category |
|---|---|---|---|---|
| **F1 Wrong tool selection** | decision | replace the chosen tool, e.g. `issue_refund` → `close_ticket(DENIED)` | control flow | TOOL_SELECTION |
| **F2 Invalid/wrong arguments** | decision | drop a required arg, or swap `order_id` for another of the customer's orders | argument validity vs. semantic error | TOOL_ARGUMENT |
| **F3 Corrupted tool output** | tool | `get_order.amount` ×10, or status `delivered`→`shipped` | data integrity; often **delayed effect** | TOOL_OUTPUT |
| **F4 Incorrect retrieval** | tool (`search_policy`) | return a plausible but wrong policy doc (different limit or eligibility) | retrieval; **delayed effect** | RETRIEVAL |
| **F5 Lost-ack timeout** | tool (`issue_refund`) | commit, then deliver a timeout; policy v1 retries without an idempotency key → duplicate refund | state, retries, idempotency | STATE / INFRASTRUCTURE |
| **D1 Decoy (harmless deviation)** | decision | insert a redundant read (`get_customer` again) | tests false attribution | — (never causal by design; verified) |

**Delayed effect:** F3/F4 at the `get_order` / `search_policy` steps surface at `issue_refund` / `close_ticket` 1–3 steps later. Each instance stores `symptom_distance = symptom_seq − fault_seq`.

**Label validation (per instance):**
- Clean run of the template → must **pass** (otherwise the template is a bug).
- Faulty run → **fail** labels the instance `CAUSAL`; **pass** labels it `MASKED` (kept, reported, excluded from the localization table).
- For `CAUSAL`: the intervention with `INJECTION_CLEAN_VALUE` at the fault site must repair the run. This confirms the label and is a separate step from evaluating localizers.
- Decoys: the decoy-only variant must pass.

## 11. Evaluation and localization algorithms

### 11.1 Deterministic evaluation (no LLM-as-judge)
- **Oracle** per template: a declarative clause list over the final state. Example: `refund(O1)=80.00`; `ticket(T1).status=REFUNDED`; `no refund > limit(customer tier) without escalation`; `no duplicate refunds for an order`; `no tool outside the allow-list`. Each violated clause is attributed to a **symptom span**: the mutating event whose delta violated it (found via deltas), or the last event if the violation is an omission.
- **Validators** (per event): Pydantic arg schemas (missing/invalid args); permission rules (allow-list; refund > tier limit requires a prior `escalate` decision); output-contract validation (types/ranges such as non-negative amounts, enum statuses); repeat detection (same tool + same canonical args ≥ 2 without intervening state change).
- **Rule-based classifier** (ordered, first match wins): infrastructure (timeout events) → authorization (permission flag) → tool-argument (schema flag) → retrieval (wrong-doc evidence: the oracle limit clause disagrees with the retrieved doc id) → tool-output (output-contract flag or a value inconsistent with state) → tool-selection (unexpected tool for the step under the ref policy, when available) → state (duplicate side effect) → `UNKNOWN`. Accuracy is measured against the injected operator's expected category (a confusion matrix, counts only).

### 11.2 Localizers (all output a full ranking over decision + tool events ≤ symptom seq)
| ID | Method | Tier | Notes |
|---|---|---|---|
| B0 | Random | — | Computed analytically: E[Top-1] = 1/n per instance; no sampling noise |
| B1 | Earliest visible error | SUSPICION | earliest event with error/timeout status or any validator flag; else the symptom span |
| B2 | Last failed tool call | SUSPICION | last tool event with error/timeout; else the symptom span |
| B3 | Rule-based ranking | SUSPICION | score = w₁·[on the argument-origin chain of the symptom span] + w₂·[validator flag] + w₃·[error status] + w₄·[mutating]; ties broken earliest-first. **Argument-origin chain:** standard taint-style tracing; the symptom's arg values are matched verbatim to the earlier tool outputs that produced them. Weights are fixed a priori in DECISIONS.md and never tuned on the test split |
| B4 | Earliest reference deviation | SUSPICION | earliest event whose delivered value ≠ its trusted reference. A strong but honest baseline: it finds deviations, not causes. Decoys and masked deviations expose it |
| CF | Placebo-controlled single-step counterfactual | **INTERVENTIONAL** where supported | see below |

**CF algorithm**
```
candidates ← decision/tool events with seq ≤ symptom_seq, ordered by B3 rank
for e in candidates:
    ref ← trusted_reference(e)            # REFERENCE_TOOL or REFERENCE_POLICY; else mark NO_TRUSTED_REFERENCE
    if ref is None:            tier[e] ← SUSPICION (B3 score); continue
    if fp(ref) == fp(delivered[e]):  tier[e] ← CONSISTENT_WITH_REFERENCE; continue   # no-op intervention
    r_ref  ← REPLAY_INTERVENE(R, e, ref)        # Contract B
    r_plc  ← REPLAY_INTERVENE(R, e, ORIGINAL)   # placebo
    if r_plc invalid or r_plc.outcome ≠ R.outcome: flag INVALID_COUNTERFACTUAL (bug); continue
    tier[e] ← INTERVENTIONAL if r_ref.outcome == pass else DEVIATES_NOT_REPAIRING
ranking ← [INTERVENTIONAL by seq] + [DEVIATES_NOT_REPAIRING by seq] + [rest by B3]
decisive ← first INTERVENTIONAL, else NOT_ISOLATED_BY_SINGLE_STEP
report replays_used, wall_ms
```
Complexity: *m* ≤ n candidates × 2 replays × O(n) events = O(n²) boundary operations. With n ≈ 8–15 this is milliseconds. Exhaustive evaluation is fine in L1, and cost-aware selection is the L3 question. The placebo for deterministic runs doubles as a continuous replay-machinery self-test.

**Metrics** (on `CAUSAL` single-fault test-split instances): Top-1, Top-3, MRR. Results are reported as **counts k/n plus Wilson 95% CIs**, given the small n. Also reported:
- Top-1 stratified by `symptom_distance` (0 vs. ≥1) and by operator.
- On decoy-containing instances: **decoy false-attribution rate** = instances where the method's top-1 is the decoy.
- Replays per investigation; classifier confusion matrix.
- Two-fault cases: a qualitative table only.

## 12. Revised benchmark design ("AgentTrace-Synth v0")
- **8 scenario templates** (support domain):
  - T1 damaged item within limit → refund
  - T2 amount above tier limit → escalate
  - T3 final-sale item → deny + close
  - T4 not yet delivered → inform + keep open
  - T5 refund already issued → no new refund
  - T6 multi-order customer → refund the correct order
  - T7 partial refund of one line item
  - T8 gold-tier extended limit
- **Clean set:** 8 runs, which must all pass.
- **Fault instances:** templates × applicable operators × 1–2 sites, generated automatically. **Target 40–60 instances** after filtering inapplicable combinations, including **≥8 with symptom_distance ≥ 1**, **~8 decoy-augmented** (a decoy plus a causal fault in one run), and **≤4 two-fault** cases (reported separately).
  - The count is set by available hours: generation is automatic, but each operator, template and oracle needs hand-verification.
  - MASKED instances are kept and counted.
- **Splits by template** (prevents leakage via shared structure): **dev = T1–T5, test = T6–T8**. Rule weights, classifier order and any thresholds are frozen (git tag `bench-freeze-v0`) before the single test-split run. Every test-split evaluation is logged.
- **Artifacts:** `scenarios/*.json`, `fault_plans/*.json`, `labels.jsonl` (sidecar), `results/<tag>/{metrics.json, table.md, manifest.json (git SHA, config fingerprints, Python version)}`.
- **Honest limitations (stated in README):** a scripted policy; one synthetic domain; injected faults are not natural LLM failures; small n → wide CIs; references exist for all steps (unrealistic for real agents, which is why CF's applicability is limited and L3 exists).

## 13. Replay correctness test matrix

**Base scenario S-REF-01 (T1)**
- Initial state: customer C1 (regular tier, limit 100.00), order O1 (80.00, delivered, damaged), ticket T1 open, policy doc P-damaged ("refund ≤ tier limit"), refunds = [].
- Gold run R₀ (seq of boundary events, clock/idgen omitted): `decide→get_customer(C1)` · `decide→get_order(O1)` · `decide→search_policy("damaged")` · `decide→issue_refund(O1, 80.00, key K1)` · `decide→close_ticket(T1, REFUNDED)` · `decide→FINAL`.
- Expected final state F₀: refunds=[R-0001(O1, 80.00)], T1=closed/REFUNDED, idempotency_log={K1}; oracle pass.

| # | Initial state | Recorded execution | Modification / intervention | Expected behaviour | Expected final state | Assertion |
|---|---|---|---|---|---|---|
| 1 | S-REF-01 | R₀ (pass) | none; REPLAY_STRICT | completes; policy never invoked (spy) | F₀ | all §8.4 metrics = 1.0/true; outcome pass; policy-spy call count = 0 |
| 2 | S-REF-01 + F3 (O1.amount→800.00) | R₁ (fail: refund escalation clause or amount clause) | none; REPLAY_STRICT | completes, reproduces failure | identical to R₁'s final hash | metrics = 1.0; same violated clauses and symptom seq |
| 3 | S-REF-01 | R₀ with the cassette entry for `get_order` deleted | REPLAY_STRICT | stops at that seq | not persisted | status DIVERGED(kind=MISSING/EXTRA_EVENT) at exactly that seq; no live tool/policy call after it |
| 4 | S-REF-01 | R₀ with recorded `request_fp` at seq k altered | REPLAY_STRICT | stops at k | not persisted | DIVERGED(kind=REQUEST) at k; diff contains expected vs. actual fp |
| 5 | S-REF-01 | R₀ | change the tool implementation so `get_order` returns an extra field (tool-manifest hash unchanged via a test hook) | detect a response mismatch | not persisted | DIVERGED(kind=RESPONSE) at the `get_order` seq. Also: with the manifest hash changed → CONFIG_MISMATCH before execution |
| 6 | S-REF-01 + T2 variant (amount 150 > limit) | R₂: v1 policy, escalates | edit the recorded decision at the escalation step to `issue_refund` (cassette tampering) → REPLAY_STRICT | downstream tool request differs from recorded | not persisted | DIVERGED at the first downstream mismatched seq; **no cassette response served after it** |
| 7 | S-REF-01 | R₀ | REPLAY_STRICT with the tool's commit order swapped by a test hook | state-hash mismatch | not persisted | DIVERGED(kind=STATE) at the first mutating event whose `state_hash_after` differs |
| 8 | S-REF-01 + T7 variant (two `get_order` calls for different orders + one repeat read) | R₃ with repeated same-name calls | REPLAY_STRICT | each occurrence matched positionally to its own entry | R₃ final | metrics = 1.0; the test asserts the occurrence-2 response ≠ occurrence-1 response and each is served correctly; a swapped-order cassette → DIVERGED |
| 9 | S-REF-01 + F5 (lost-ack timeout on `issue_refund`), policy v1 | R₄: timeout → retry without key → duplicate refund (fail) | REPLAY_STRICT | timeout re-delivered; commit re-applied | R₄ final: 2 refunds | metrics = 1.0; refunds count = 2; the timeout event has status=timeout and state_hash_after ≠ before |
| 10 | S-REF-01 with max_steps=3 (early termination) | R₅ status MAX_STEPS | REPLAY_STRICT | stops at the same point with the same status | partial state equal to R₅ | equal event count, final hash, status MAX_STEPS; TRUNCATED/EXTRA_EVENT not raised |
| 11 | S-REF-01 + F4 (wrong policy doc: limit 50) | R₆ fail (refund denied / escalated wrongly) | REPLAY_INTERVENE at the `search_policy` seq with REFERENCE_TOOL output | prefix identical; suffix live | F₀-equivalent (refund 80.00, T1 REFUNDED) | prefix metrics = 1.0; outcome pass; `cassette_access_after_fence == 0`; the run header records the intervention |
| 12 | same as 11 | R₆ | REPLAY_INTERVENE at the `get_customer` seq with REFERENCE_TOOL (no-op difference) **and** at the decoy seq | no repair | same as R₆ | outcome fail; tier ≠ INTERVENTIONAL; no-op detected as CONSISTENT_WITH_REFERENCE without replay |
| 13 | same as 11 | R₆ | placebo: REPLAY_INTERVENE at the `search_policy` seq with ORIGINAL | reproduces R₆ exactly through the live suffix | R₆ final hash | outcome and final hash equal R₆; the event sequence equals R₆'s |
| 14 | S-REF-01 + F5 fixture | baseline: policy v1 R₄ (fail) | REGRESSION with policy v2 (uses idempotency keys / checks refunds before retry) | fresh execution; no cassette constructed | 1 refund, T1 REFUNDED | verdict DETERMINISTIC_PASS (two identical fingerprints); a cassette-store spy records 0 accesses; REPLAY_STRICT of R₄ under the v2 config → CONFIG_MISMATCH |
| 15 | all 8 clean templates | record each | run each template 5× interleaved in one process, plus exact replays in between | no cross-run leakage | each equals its own recording | identical trace fingerprints and final hashes across repeats; the original scenario snapshot object is unchanged (hash before == after) |

Hypothesis property tests (bounded `max_examples` for the 8 GB machine):
- (P1) Canonical-JSON fingerprints are invariant to key order and Decimal formatting.
- (P2) For randomly generated valid support states and requests, record → exact replay satisfies the full invariant.
- (P3) Snapshot → restore → hash round-trips.
- (P4) A random single-event cassette mutation is always detected (never a silent pass).

## 14. Recommended technology stack (L1)
| Component | Choice | Why |
|---|---|---|
| Runtime | Python 3.12, `uv` (env + lockfile) | One language; fast, reproducible installs |
| Models/schemas | Pydantic v2 | Validation, JSON schema export, frozen models |
| CLI | Typer + Rich | Small dependencies; readable tables and trace trees in a terminal demo |
| Persistence | JSONL/JSON files behind `TraceStore` | Zero setup, inspectable, diffable; SQLite adapter in L2 |
| Tests | pytest, Hypothesis, pytest-cov | Acceptance + property tests |
| Quality | ruff, mypy (strict on `trace/ replay/ runtime/ env/`), import-linter (optional) | Enforce boundaries cheaply |
| CI | One GitHub Actions workflow: lint, type-check, tests, dev-split benchmark smoke (< 5 min) | Credibility signal |
| Not used in L1 | FastAPI, React, Postgres, Redis, Docker, LangGraph, OTel SDK, Ollama, any LLM SDK | Deferred (§5) with interfaces ready |

## 15. MacBook Air M2 (8 GB) feasibility
- **L1 memory [E]:** a Python process with Pydantic/Typer/Rich and in-memory KB-sized states uses well under ~200 MB. pytest with Hypothesis is of the same order. The full benchmark (~60 instances × ≤ ~20 replays each, all deterministic) should finish in seconds to low minutes. **[E, measure in week 2]**
- **Co-running tools [E]:** VS Code + Claude Code + a browser typically use a few GB; the L1 footprint is negligible alongside them.
- **Rules [R]:**
  - No Docker Desktop in L1; its Linux VM reserves memory by default [K].
  - Run benchmarks sequentially (no multiprocessing pool).
  - Use the Hypothesis `max_examples` profile `dev=50`, `ci=200`.
  - Close browser tabs during any future LLM experiments.
- **Future local LLMs (L2, optional):**
  - Not a prerequisite. Start with **~0.5B–3B instruct models at 4-bit quantization**. Approximate weight memory ≈ params × ~0.55–0.6 bytes, plus KV cache and runtime overhead **[E]**: ~0.5–1 GB for 1–1.5B, ~2–2.5 GB for 3B. Candidates to evaluate for tool-calling support **[verify]**: Qwen2.5-1.5B/3B-Instruct, Llama-3.2-3B-Instruct, Phi-3.5/4-mini.
  - Runtimes: llama.cpp or Ollama with context ≤ 4k and one model loaded at a time.
  - **Gate:** measure clean-scenario task success over ≥5 runs per dev template before using a model in any experiment. If it is too low to produce meaningful failures, simplify the tasks instead of upgrading to 7–8B. Treat 7–8B models as infeasible on 8 GB with an IDE open **[E]**.
- **Hosted APIs:** an interface plus a `BudgetGuard` arrive in L2, disabled unless `ATRACE_ALLOW_PAID=1` with explicit per-run token caps. Cost is computed from the provider's current published prices at the time of use, never assumed.

## 16. Repository structure

**Public repo `agenttrace` (Apache-2.0)**, containing only standard / already-published methods:
```
agenttrace/
  README.md  LICENSE  pyproject.toml  uv.lock  Makefile
  docs/  ARCHITECTURE.md  REPLAY_SPEC.md  TRACE_SCHEMA.md  EVALUATION.md  SECURITY.md  DECISIONS.md
  src/agenttrace/
    trace/       schema.py canonical.py fingerprint.py store_jsonl.py
    env/         support/{state.py tools.py snapshot.py scenarios/}
    policies/    scripted_v1.py scripted_v2.py reference.py
    runtime/     loop.py gateway.py recorder.py
    replay/      exact.py counterfactual.py regression.py cassette.py divergence.py fidelity.py align.py
    faults/      plan.py operators.py labels.py
    evals/       oracle.py validators.py classifier.py
    localize/    base.py baselines.py rules.py counterfactual.py
    bench/       generate.py validate.py run.py metrics.py
    report/      console.py markdown.py
    cli.py
  tests/  unit/  acceptance/ (test_replay_matrix.py: tests #1–15)  property/  golden/
  benchmarks/synth_v0/  scenarios/ fault_plans/ labels.jsonl splits.json
  results/  (git-ignored except tagged summaries)
  .github/workflows/ci.yml
```

**Private repo `agenttrace-research` (no licence = all rights reserved; never pushed publicly)**: depends on the public package as a library and registers localizers via a plugin entry point. Contents: research notes, hypotheses, experimental localizers (adaptive allocation, stopping rules, provenance pruning), experiment configs, prior-art search log, invention-disclosure drafts.

## 17. Four-week implementation plan (~66 focused hours)

Assumption [A]: ~2.5 h/day × 7 days × 4 weeks ≈ 70 h available nominally. The plan schedules **66 h** and the gap to 84 h (~18 h) is buffer. If availability is nearer 56 h, switch to §18 at **Checkpoint 2**.

### Week 1 — Foundation (16 h)
| Task | h |
|---|---|
| Freeze L1 requirements; write DECISIONS.md ADRs (JSONL store, re-application replay, cassette fence, scripted policy, Apache-2.0 + private research repo) | 2 |
| Repo setup: uv, ruff, mypy, pytest, CI workflow | 1.5 |
| `trace/`: Pydantic schema v1, canonical JSON, fingerprints, JSONL store, hash chain | 3.5 |
| `env/`: SupportState, 5 tools (`get_customer`, `get_order`, `search_policy`, `issue_refund`, `close_ticket`; `escalate` modelled as a `close_ticket` resolution), transactional commit, snapshot/restore/hash, idempotency | 4 |
| `policies/` + `runtime/`: agent loop, BoundaryGateway (decision/tool/clock/idgen), ScriptedPolicy v1, ReferencePolicy | 3 |
| `evals/oracle.py` + 8 templates; unit tests (tools, snapshot round-trip, all clean templates pass) | 2 |
- **Dependencies:** none. **Deliverables:** `atrace run T1` executes and prints a result; clean templates pass.
- **Acceptance:** 8/8 clean templates pass the oracle; snapshot hash round-trip test passes; CI green.
- **DoD:** Checkpoint 1 met; schema v1 committed and documented in TRACE_SCHEMA.md.

### Week 2 — Record / exact replay (18 h)
| Task | h |
|---|---|
| Recorder (RECORD mode writes header/events/footer; deltas; state hashes) | 3 |
| Cassette (positional, consume-once), config fingerprint + CONFIG_MISMATCH | 2.5 |
| ExactReplayer (re-application + verification, all divergence kinds) | 4 |
| Fidelity report (§8.4) | 1.5 |
| CLI: `run`, `show` (Rich tree/timeline with state hashes), `replay` | 2.5 |
| Acceptance tests #1–#10, #15; property tests P1–P4 | 4.5 |
- **Dependencies:** week 1. **Deliverables:** `atrace replay <run_id>` with a fidelity report.
- **Acceptance:** tests #1–10 and #15 pass; P1–P4 pass at the `ci` profile.
- **DoD:** Checkpoint 2 met; REPLAY_SPEC.md drafted from §7–8.

### Week 3 — Faults, counterfactuals, regression, localization (18 h)
| Task | h |
|---|---|
| Fault layer: FaultPlan triggers, F1–F5 + D1, sidecar labels, clean-value capture | 4 |
| Benchmark generator + label validation (CAUSAL/MASKED; decoy checks) + splits | 3 |
| CounterfactualRunner (prefix, intervention, fence, placebo) + tests #11–13 | 4 |
| RegressionRunner + ScriptedPolicy v2 + test #14 | 2 |
| Validators, rule classifier, B1–B4 | 3 |
| CF localizer + investigation report (console + Markdown) | 2 |
- **Dependencies:** week 2 (replay correctness). **Deliverables:** `atrace inject`, `atrace investigate <run_id>`, `atrace regress`; a validated benchmark on disk.
- **Acceptance:** all 15 matrix tests pass; every CAUSAL label is validated; the placebo reproduces every faulty run.
- **DoD:** Checkpoints 3 and 4 met.

### Week 4 — Evaluation & release (14 h)
| Task | h |
|---|---|
| `bench run`: metrics (Top-1/3, MRR, Wilson CIs, stratification, decoy false-attribution, replays), `table.md` + manifest | 3 |
| Run on dev, fix bugs, freeze (`bench-freeze-v0`), single test-split run | 3 |
| Demo polish: investigation report readability, `make demo` script | 2 |
| README (problem, quickstart, demo, results with limitations), ARCHITECTURE, EVALUATION, SECURITY | 4 |
| Record a 3-minute demo; write NEXT.md (next milestone = L2 step 1) | 2 |
- **Dependencies:** week 3. **Deliverables:** tagged release `v0.1.0`; results table; demo video.
- **Acceptance:** `make reproduce` regenerates the exact table from a clean clone; CI green.
- **DoD:** Checkpoint 5 met.

**Total: 16 + 18 + 18 + 14 = 66 h.** Testing requirements for every week: new code ships with unit tests; replay/runtime/env/trace keep mypy strict and pass the acceptance suite in CI; nothing merges with a red CI.

## 18. 56-hour fallback scope (50 h work + 6 h buffer)
| Cut | Saves |
|---|---|
| F1–F4 only; drop F5 (lost-ack). The regression demo instead uses an F3 robustness fix (v2 validates `amount` against the order's line items) | 2 h |
| 6 templates instead of 8 (dev T1–T4, test T5–T6) | 1 h |
| Skip the rule classifier (category from the violated clause only) and B2 | 2 h |
| Property tests reduced to P1 + P4 | 1.5 h |
| Rich timeline reduced to a plain table; Markdown report only | 1.5 h |
| Docs: README + REPLAY_SPEC only (ARCHITECTURE folded into README) | 2.5 h |
| Demo video → recorded terminal session (asciinema) | 0.5 h |
| Merge the week-4 "dev fix" into buffer | 1 h |
| CI: tests only (no benchmark smoke) | 0.5 h |
| Decoys reduced to 4 instances | 0.5 h |
| Skip the import-linter/boundary test and the schema JSON export | 1 h |
| Simplify the alignment report to "first divergence point" (no LCS) | 2 h |
| **Total saved** | **16 h → 50 h** |

**Never cut:** the three replay contracts, the cassette fence, the placebo control, tests #1–15 (#9 becomes an F3-based stateful test if F5 is cut), validated labels, an honest results table.

## 19. Go/no-go checkpoints
| CP | When | Required evidence | Tests that must pass | Failure condition | If it fails |
|---|---|---|---|---|---|
| **CP1** Deterministic agent | end of week 1 | 8 clean templates pass; identical fingerprints over 3 repeated runs | env/tool unit tests, snapshot round-trip, oracle tests | any template fails, or nondeterministic fingerprints | stop feature work; defer T7/T8 and F5; fix determinism (hidden mutable state, Decimal, ordering) |
| **CP2** Exact replay | end of week 2 | fidelity = 1.0 on all clean + sample faulty recordings; every perturbation detected with the correct kind | #1–10, #15, P1–P4 | any silent pass on a perturbed cassette, or a mismatch on an unmodified one | **no counterfactual work until fixed**; switch to the §18 fallback; drop the CLI polish |
| **CP3** Validated faults | mid week 3 | every instance labelled CAUSAL/MASKED by validation; ≥8 delayed-effect CAUSAL; decoy-only runs pass | generator/label tests | labels not reproducible; too few delayed-effect cases | reduce operators to the 3 that validate cleanly; add templates rather than operators |
| **CP4** Controlled counterfactual | end of week 3 | ≥1 demonstrated repair with a failing placebo; no fence violations | #11–14 | placebo ≠ original, or cassette access after the fence | defer B3/B4 and the classifier; fix the machinery; the demo uses exact replay + baselines only |
| **CP5** Reproducible results | end of week 4 | `make reproduce` on a fresh clone yields an identical `table.md` + manifest | full suite + benchmark smoke in CI | non-identical output | defer the video; fix determinism; publish without results rather than with irreproducible ones |

Replay correctness takes priority over all CLI/report/UI work at every checkpoint.

## 20. Testing and quality assurance
- **Layers:** unit (pure functions, tools, validators) → acceptance (§13 matrix) → property (P1–P4) → golden traces (recorded runs checked in as fixtures; a schema change requires an explicit fixture update) → benchmark smoke (dev split).
- **Determinism guards:** a test forbids `random`, `time.time`, `uuid4` and `datetime.now` imports in `env/ policies/ runtime/` (everything goes through the gateway); a test asserts no module-level mutable state in `env/`.
- **Leakage guard:** a test asserts the localizer entry points receive a `Trace` type with no label fields, and that `labels.jsonl` is only read by `bench/validate.py` and `bench/metrics.py`.
- **Coverage target (engineering goal, not a result):** ≥85% line coverage on `replay/`, `runtime/`, `trace/`.
- **Security-aware engineering:** tools are pure Python over in-memory state; no `subprocess`/`socket`/`requests`/`eval` in `env/` (enforced by test); trace loading uses Pydantic validation with size and depth limits, never pickle; dependencies are pinned in `uv.lock`, with `pip-audit` in CI (cheap) and `gitleaks` pre-commit.
- **Review ritual:** end each session with an AI-assisted diff review focused on replay invariants.

## 21. Long-term engineering roadmap (Level 2, ordered by dependency and value)
1. **SQLite `TraceStore`** + run index/query; content-addressed payloads; redaction rules.
2. **Hierarchical ddmin** (Zeller & Hildebrandt 2002 [K]) over scenario components, with failure-signature preservation → minimized regression tests.
3. **Regression management:** versioned tests, suites, baseline-vs-candidate history, recurrence signatures, a GitHub Action.
4. **Local LLM policy** (small quantized model, after the reliability gate in §15); stochastic replay with k-runs and Wilson CIs; LLM-boundary cassettes; a replay-fidelity study.
5. **LangGraph adapter** (map node/tool calls to `BoundaryGateway`); demonstrates practical LLM-framework skills.
6. **FastAPI service + React viewer** (timeline, run diff, investigation evidence panel; React Flow DAG later).
7. **Security suite:** AgentDojo adapter [K: verify licence], indirect-injection cases with deterministic attack-success oracles, defense comparison; OWASP LLM Top 10 2025 / MITRE ATLAS mapping [verify IDs].
8. **OTel GenAI-aligned export/ingest** (semconv still in "Development" status [F]).
9. SBFL (Ochiai) baseline; more fault operators (partial commit, state corruption, interaction faults); PostgreSQL; an optional hosted policy with BudgetGuard.

## 22. Research and patent investigation roadmap (Level 3, private repo)

**Working title:** *Budget-Aware, Evidence-Graded Failure Localization for Tool-Using AI Agents.*

1. **Engineering prerequisites:** L1 complete; L2 items 1, 4 (stochastic local-LLM policy and k-replay counterfactuals) and an SBFL baseline.
2. **Literature verification:** read the full text of the v0.1 key papers and update the prior-art log. Retained references:
   - Who&When — [arXiv 2505.00212](https://arxiv.org/abs/2505.00212) [F]
   - AgenTracer — [arXiv 2509.03312](https://arxiv.org/abs/2509.03312) [F]; AgenTracer-v2 — [NeurIPS 2026](https://neurips.cc/virtual/2026/poster/153890) [F]
   - FAMAS — [arXiv 2509.13782](https://arxiv.org/abs/2509.13782) [F]
   - GraphTracer — [arXiv 2510.10581](https://arxiv.org/pdf/2510.10581) [F]
   - DoVer — [arXiv 2512.06749](https://arxiv.org/pdf/2512.06749) [F]
   - Causal Agent Replay — [arXiv 2606.08275](https://arxiv.org/pdf/2606.08275) [F]
   - Minimal Repair Families — [arXiv 2608.29228](https://arxiv.org/pdf/2608.29228) [F]
   - ReplayRCA — [arXiv 2610.41025](https://arxiv.org/pdf/2610.41025) [F]
   - Executed-counterfactual reporting standard — [arXiv 2611.05650](https://arxiv.org/pdf/2611.05650) [F]
   - Replay Fidelity in AppWorld — [arXiv 2611.11216](https://arxiv.org/pdf/2611.11216) [F]
   - TRAIL — [arXiv 2505.08638](https://arxiv.org/abs/2505.08638) [F]
   - FailMin — [PyPI](https://pypi.org/project/failmin/) [F, maturity unverified]; TRIM — [arXiv 2607.18161](https://arxiv.org/pdf/2607.18161) [F]
   - Classical: ddmin (TSE 2002), cause-effect chains (FSE 2002), Tarantula/Ochiai, dynamic slicing, Top-Two Thompson Sampling (Russo 2016), SPRT (Wald 1945) [K, verify citations]
3. **Candidate hypotheses** (detailed in v0.1 §26.1; kept private):
   - **H1:** provenance-guided candidate pruning reduces replays at small Top-1 loss.
   - **H2:** adaptive sequential replay allocation with an earliest-cause stopping rule reaches fixed-k accuracy with fewer replays/tokens under stochastic policies.
   - **H3:** signature-preserving minimization yields less flaky regression tests.
   - **H4:** heuristic accuracy degrades with symptom distance while counterfactual accuracy does not (an empirical study).
4. **Baselines:** B0–B4, SBFL-Ochiai, LLM-judge "read the trace" (local model), fixed-k CF, uniform allocation, per-step SPRT.
5. **Datasets:** AgentTrace-Synth v1 (scaled up with an LLM policy); an AgentDojo subset for natural failures (heuristic-only, no ground truth); Who&When/TRAIL for heuristic comparison only (no replay possible).
6. **Metrics:** Top-1/3, MRR, replays and tokens per diagnosis, a cost–accuracy Pareto front, pruning recall, posterior calibration, test flake rate; bootstrap CIs clustered by template; McNemar/Wilcoxon with Holm correction.
7. **Ablations:** pruning on/off; allocation strategy; k; τ; model size; temperature; reference availability.
8. **Novelty risks:** high. Causal Agent Replay, ReplayRCA, FailMin and AgenTracer-v2 may already cover parts of H1–H3. Result framing may need to become a replication/empirical study.
9. **Prior-art search requirements:** academic (arXiv, ACL Anthology, OpenReview, ICSE/FSE/ASE) plus patent databases (Google Patents, InPASS (Indian Patent Office), Espacenet, USPTO), with a focus on AIOps / distributed-tracing root-cause-analysis patents and LLM-agent debugging filings. Log queries, dates and hits in the private repo.
10. **Decision points:**
    - **D1 (after literature verification):** continue / reframe as an empirical study.
    - **D2 (after the first private results on dev):** consult the university IPR cell *before* any public talk, preprint or repo push of the method.
    - **D3:** if IPR advises filing → an Indian provisional application *before* disclosure; otherwise publish (workshop / SE demo track) and open-source the research code.

**Separation and licensing strategy [R]:**
- **Public foundation** under **Apache-2.0**. It contains only standard techniques (record/replay, deterministic oracles, baselines, single-step placebo-controlled CF, all of which have prior art).
  - Apache-2.0's explicit patent grant covers contributors' patents that read on *their contributions*. Keeping all candidate-inventive mechanisms **out** of the public repo means the grant does not reach them [K; confirm with the IPR cell]. It is also recruiter-friendly.
  - MIT is an acceptable alternative but gives users less clarity.
- **Private research repo**: no licence, private visibility, no public issues or demos of its methods. The public README mentions only generic "future work on cost-aware localization" in terms already present in published literature.
- **Caveats:**
  - Neither withholding publication nor choosing a licence creates patent rights; only a filing does.
  - Public commits, talks, preprints, LinkedIn posts and demo videos are disclosures.
  - Ask the IPR cell whether sharing plans with AI services (ChatGPT/Claude) counts as confidential [verify; depends on service terms].
  - Check the university's IP policy on student work. India's novelty grace provisions are narrow (Patents Act ss. 29–34 [K, verify]); s. 3(k) excludes "computer programme per se / algorithms", so any claim would need a demonstrable technical effect (CRI Guidelines; *Ferid Allani v. UoI*, Delhi HC 2019 [K, verify]).
- **Honest expectation:** patentability is doubtful; publication or a strong open-source artifact is the likelier payoff.

## 23. Placement and demonstration value
**Is the reduced MVP still impressive?** Yes, if it is presented as *a correctness-focused agent reliability engine*, not a dashboard. It demonstrates:
- **Python engineering:** typed Pydantic models, a modular monolith, protocols/interfaces, a CLI, CI.
- **AI agent execution:** an explicit agent loop with decision/tool boundaries mirroring LLM tool calling.
- **State management:** transactional commits, snapshots, idempotency, retries, lost-ack semantics.
- **Deterministic testing:** a 15-case replay acceptance matrix plus property tests.
- **Observability:** a versioned trace schema, fingerprints, hash chains, fidelity metrics.
- **Failure analysis:** a fault taxonomy, a rule classifier, evidence tiers.
- **Algorithm design:** taint-style origin tracing, placebo-controlled interventions, sequence alignment.
- **Benchmarking:** validated labels, template-level splits, freeze-then-test, CIs.
- **Security-aware engineering:** sandboxing, permission validation, tool-output manipulation, no unsafe execution.
- **Reproducibility:** one-command regeneration with a manifest.

**Gap to acknowledge in interviews:** L1 has no real LLM. Answer: "the boundaries are model-agnostic by design; the next milestone plugs in a small local model and a LangGraph adapter, and the replay contracts were designed precisely for stochastic policies." L2 items 4–5 then demonstrate hands-on LLM engineering (tool-calling prompts, small-model reliability measurement, framework integration).

**3-minute demo (CLI)**
1. *0:00–0:20* `atrace run T6` → the agent resolves a multi-order refund; the oracle passes; trace tree shown.
2. *0:20–0:40* `atrace inject T6 --op F4` (wrong policy document retrieved at step 3) → run fails at `close_ticket`/`issue_refund` 2 steps later; violated clause shown.
3. *0:40–1:00* `atrace show <run>`: the failure is recorded with state hashes; the earliest visible error points at the refund step.
4. *1:00–1:20* `atrace replay <run>` → fidelity report: all metrics equal; deterministic reproduction, with no model or tool side effects outside the sandbox.
5. *1:20–2:10* `atrace investigate <run>`:
   - Baselines B1/B2 blame the symptom step (SUSPICION).
   - CF replaces the `search_policy` output with its trusted reference → **pass**; placebo → **fail** → tier INTERVENTIONAL. The decoy step is CONSISTENT/non-repairing.
6. *2:10–2:40* Show the evidence section: prefix identical, fence respected, the downstream path changed (alignment diff), the new final state.
7. *2:40–3:00* The results table from the frozen test split (with CIs and limitations), plus `atrace regress` with the F5 fixture: v1 fails, v2 DETERMINISTIC_PASS.

**Resume bullet structures** (fill only with measured values): "Engineered a deterministic record/replay engine for tool-using agents with state re-application and fail-closed divergence detection, verified by a *[N]*-case acceptance matrix and property-based tests" · "Built a fault-injection benchmark of *[N]* validated failures across *[K]* operators; placebo-controlled counterfactual localization achieved Top-1 *[k/n]* vs. *[k/n]* for an earliest-error baseline (95% CI *[…]*)".

## 24. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Hidden nondeterminism (dict order, floats, time, ids) | Gateway-only clock/idgen; Decimal; canonical JSON; banned-import test; CP1 |
| Replay engine larger than estimated | Weeks 2–3 ordered so replay correctness is done first; §18 fallback triggered at CP2 |
| Wrong cassette reuse after branching | Positional matching + full-key verification + fence + fail-closed; tests #6, #11 |
| Benchmark too easy / circular (references exist for every step) | Decoys, masked faults, delayed effects, an explicit B4 baseline, a stated limitation |
| Label leakage | Sidecar labels; type-level separation; leakage test; template splits; a freeze tag |
| Small n → weak conclusions | Report k/n + Wilson CIs; no percentage claims without counts |
| "No LLM" weakens placement value | Model-agnostic boundaries; L2 local-LLM + LangGraph as the immediate next milestone; prepared interview answer |
| Scope creep from other projects | Hours ledger in TASKS.md; checkpoints; cut list |
| Accidental disclosure of research ideas | Separate private repo; public docs restricted to published concepts; IPR decision points |
| 8 GB memory pressure later | No Docker in L1; small models only after the gate; sequential runs |

## 25. Assumptions and remaining decisions

**Assumptions [A]:**
- ~2.5 h/day average.
- Python 3.12 and uv are acceptable.
- GitHub is used for the public repo (with a private repo for research).
- A terminal-based demo is acceptable for the target recruiters.
- Synthetic, scripted ground truth is acceptable for L1 claims if limitations are stated.
- Memory/runtime figures marked [E] will be measured in week 2.

**Decisions recommended (accept or override):**
1. Domain: **customer support / order management** (5 tools, state-based oracle, natural mutating/idempotency semantics).
2. Licence: **Apache-2.0 public foundation + private, unlicensed research repo**, pending IPR-cell confirmation.
3. CLI = Typer + Rich; persistence = JSONL.

**Still open [Q]** (none block week 1):
- Q1: Can you reach the university IPR cell before week 4, i.e. before the public release, to confirm the licensing/disclosure approach? If not, release the public foundation anyway (it contains no candidate-inventive material) and hold everything else.
- Q2: Public repo visibility during development: public from day 1 (better commit history signal) or private until v0.1.0? I recommend private until CP5, then public.

---

## Internal consistency check
| Question | Answer |
|---|---|
| Schedule fits 60–70 h? | Yes: 16+18+18+14 = **66 h**; ~18 h of buffer up to 84 h |
| Fallback fits 56 h? | Yes: **50 h** + 6 h buffer (§18 itemizes 16 h of cuts) |
| Runs without paid APIs? | Yes: no LLM at all in L1; hosted policy is L2, opt-in |
| Runs on an 8 GB M2? | Yes: no Docker/LLM/DB server; KB-sized states; sequential runs ([E] to be measured in week 2) |
| Replay engine well specified? | Contracts A/B/C (§7), state semantics (§8.2), invariant (§8.2), identity layers (§8.3), fidelity metrics (§8.4), 15 tests (§13) |
| Exact replay vs. regression separated? | Yes: regression constructs no cassette (spy-tested); config mismatch refuses strict replay (#14) |
| State mutations handled correctly? | Transactional commits, re-application + hash verification, idempotency, lost-ack, interrupted replay (§8.2; tests #7, #9, #15) |
| Step identity robust to branching? | Positional + full-key match only before the fence; live execution after; reporting-only alignment (§8.3; tests #6, #8, #11) |
| Causal claims controlled? | Trusted references only; placebo required; tiers; single-step limitations stated (§8.5) |
| Demonstrable without a frontend? | Yes: CLI demo script (§23) |
| Research preserved? | Yes: L3 roadmap (§22), private repo, decision points |
| Placement-relevant to GenAI roles? | Yes for agent reliability/eval/backend; LLM hands-on is L2 items 4–5, acknowledged |
| Assumptions identified? | §25 + [A]/[E] labels inline |
