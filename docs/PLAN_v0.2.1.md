# AgentTrace AI — Technical & Research Plan v0.2.1

> Final plan (2026-11-23). It applies four corrections from the ChatGPT review of v0.2; v0.2 is kept unchanged at `docs/archive/PLAN_v0.2.md`.
> Status: **conditionally approved; Week 1 implementation authorized.**
> Labels: **[F]** verified via web search (2026-11-22) · **[K]** prior knowledge, needs **[verify]** · **[R]** recommendation · **[A]** assumption · **[E]** unverified estimate · **[Q]** remaining decision.
>
> **Authority:** `docs/REPLAY_SPEC.md` is authoritative for replay semantics and `docs/TRACE_SCHEMA.md` for serialized data contracts. If this plan disagrees with either, the spec wins and this plan must be corrected.
>
> **Disclosure warning:** §22 (research roadmap) and the archived v0.1/v0.2 material describe candidate research mechanisms. Before any public release of this repository, remove them (and their git history) and move them to the private research repository. See DECISIONS.md ADR-010.

## 0. Change log v0.2 → v0.2.1
| # | Correction | Sections changed | Summary |
|---|---|---|---|
| C1 | Realistic schedule | §1, §17, §18, §19, consistency check | **Committed MVP = 50 h planned + ≥6 h debugging = 56 h.** The former 66 h plan becomes **committed + stretch** (stretch = +16 h, only if time allows; maximum available 84 h). §18 is now the stretch list instead of a fallback. The three replay contracts and their core tests stay in the committed scope. F5 (lost ack) stays committed because the corrected replay tests require it. |
| C2 | Replay semantics | §7, §8.2, §8.5, §9, §10, §13 | Separates the **state transition**, **raw result**, **fault transform** and **delivered response**. Adds a 7-stage tool execution lifecycle; fault operators declare their stage (`DECISION`, `PRE_EXECUTION`, `POST_EXECUTION`). Interventions are typed **OBSERVATION_REPLACEMENT** vs **EXECUTION_REPLACEMENT**, each with a matching placebo and explicit `UNSUPPORTED` results. Traces split into an **observable trace** and a **privileged execution ledger**. Test matrix extended with #16–#21. |
| C3 | Defensible localization | §11, §12 | Three separate metric families: **A injection-site localization**, **B interventional repair**, **C diagnostic evidence**. Evidence labels: `SUSPICION`, `REFERENCE_DEVIATION`, `INTERVENTIONAL_REPAIR`, `NOT_ISOLATED`, `UNSUPPORTED`. A repair is explicitly not a unique causal explanation. Leakage rules are tightened: localizers can read neither the ledger nor the labels. |
| C4 | GenAI relevance | §21, §23 | Level 2 is reordered: **2A local LLM policy → 2B LangGraph adapter → 2C FastAPI + React**. None of it starts before the committed MVP is done. |
| — | Implementation detail (ADR-008) | §7, §9 | `clock`/`idgen` boundaries are reserved in the schema but unused by the MVP: identifiers come from counters in the environment state (restored with snapshots) and the environment uses no clock. This removes two boundary kinds without loss of determinism. |

---

## 1. Executive summary

AgentTrace AI keeps its long-term vision: *a reliability, security-testing and failure-diagnosis platform for tool-using AI agents*. v0.2 reorganizes it into three levels. v0.2.1 fixes Level 1 at a **committed 50 h of planned work + ≥6 h debugging (56 h total)**, with an optional **+16 h stretch**, on an **8 GB MacBook Air M2 with no paid APIs**.

**Level 1 (four-week core MVP)** is a CLI-first Python system. Its parts:
- One synthetic **customer-support / order-management** environment with 5 sandboxed tools and a deterministic scripted agent.
- A versioned trace schema persisted as JSONL.
- A **rigorously specified replay engine** with three separate contracts: **exact replay**, **counterfactual replay** and **regression execution**.
- Five fault operators plus one harmless "decoy" operator, applied to a ~50-case synthetic benchmark with validated ground-truth fault locations.
- Deterministic oracles and validators.
- Baseline localizers (B1 earliest error, B3 rule-based, B4 earliest reference deviation; B2 is stretch) and a placebo-controlled single-step counterfactual localizer supporting **observation** and **execution** replacement.
- An honest results table, reproducible from one command.

The engineering contribution is **replay correctness with explicit invariants and a 21-test acceptance matrix**. No research novelty is claimed. Budget-aware localization stays as Level 3 research and is kept in a **separate private repository** pending prior-art review and IPR consultation.

## 2. Changes from v0.1 (historical; made in v0.2, scheduling superseded by §0 C1)

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
| `decision` | policy chooses next tool + args, or FINAL | yes (scripted), but treated as an "LLM boundary" | observable: the **delivered** Decision · ledger: the raw policy Decision and any `DECISION`-stage fault applications |
| `tool` | `issue_refund(order_id, amount, idempotency_key)` | yes, given state | observable: request, **delivered** response, **state transition** (before/after hash, committed flag, delta) · ledger: executed flag, **raw result**, fault applications per stage |
| `clock`, `idgen` | — | reserved, **unused in MVP** (ADR-008: ids come from counters in env state; env uses no clock) | — |

No randomness is used by the env or policies. Money uses `Decimal`. All serialization goes through **canonical JSON** (sorted keys, Decimals as normalized strings, floats rejected, UTF-8 NFC).

### 7.0 Tool execution lifecycle (C2; authoritative definition in REPLAY_SPEC §3)
Four separate facts are recorded for every tool call: **(a) state transition**, **(b) raw result**, **(c) fault transform(s)**, **(d) delivered response**. A delivered timeout does **not** imply that no mutation happened.

| Stage | What happens | Recorded |
|---|---|---|
| S1 Validate request | Check the tool exists and the args parse against its schema. Invalid → raw = `INVALID_ARGUMENTS` error, no execution. | `executed=false` |
| S2 Pre-execution faults | Faults with stage `PRE_EXECUTION` may **prevent** execution and supply a response (e.g. timeout before commit). | fault application (ledger) |
| S3 Execute | Run the tool on an **isolated working copy** of state. | raw result (ledger) |
| S4 Commit / roll back | Mutating tool with an ok raw result → commit the working copy atomically; otherwise discard it. A read-only tool must leave state unchanged (checked). | state transition (observable) |
| S5 Post-execution faults | Faults with stage `POST_EXECUTION` transform raw result → delivered response (output corruption, lost ack). The state transition is never changed. | fault application (ledger) |
| S6 Deliver | The agent receives the delivered response only. | delivered response (observable) |
| S7 Record | Append the observable event and the ledger entry. | — |

Fault operators must declare exactly one stage: `DECISION`, `PRE_EXECUTION` or `POST_EXECUTION`.

### 7.1 Contract A — Exact replay (`REPLAY_STRICT`)
- **Preconditions:** the run's `config_fingerprint` (schema version, scenario id+version+initial-state hash, policy id+source hash, tool-manifest hash, fault-plan hash, oracle version) equals the current code's fingerprint; otherwise **refuse with `CONFIG_MISMATCH`** before executing anything.
- **Behaviour:**
  - The environment is restored from the scenario's initial snapshot (a fresh deep copy).
  - The agent loop runs. At each boundary event *i*, the gateway checks `(seq, boundary, name, request_fp)` against cassette entry *i*. Any mismatch ends the replay with `DIVERGED` and a diff.
  - **Decision / clock / idgen:** the delivered value comes from the cassette. The policy is not consulted, so no model is called.
  - **Tool:** the full lifecycle S1–S7 is re-run on the restored state with the run's recorded fault plan (state re-application). Pre-execution faults again prevent execution, and post-execution faults again transform the raw result. Three things are then verified: the `executed`/`committed` flags and `state_hash_after` against the recording (`DIVERGED(kind=STATE)`), the raw-result fingerprint against the ledger (`DIVERGED(kind=RAW_RESULT)`), and the delivered-response fingerprint against the cassette (`DIVERGED(kind=RESPONSE)`).
  - Cassette entries are **consumed exactly once, in order**. Leftover entries at the end produce `DIVERGED(kind=TRUNCATED)`. A request past the end produces `DIVERGED(kind=EXTRA_EVENT)`.
- **Guarantees:** no model calls; no side effects outside the in-memory sandbox copy; a final state reconstructed by re-application and *verified* at every mutation; a fidelity report (§8.4).
- **Why re-application, not playback [R]:** returning recorded tool outputs alone does **not** reproduce the final environment state, so the oracle could not be re-evaluated. Re-execution with verification reproduces the state *and* tests tool determinism. L2 adds `PLAYBACK_WITH_DELTAS` for tools that cannot be re-executed (external APIs): recorded state deltas are applied instead, with a weaker guarantee labelled `RECONSTRUCTED`.

### 7.2 Contract B — Counterfactual replay (`REPLAY_INTERVENE`)
- **Input:** recorded run *R* and an **intervention spec** declaring:
  - `target_seq`;
  - `intervention_type` ∈ {`OBSERVATION_REPLACEMENT`, `EXECUTION_REPLACEMENT`};
  - `reference_source` ∈ {`REFERENCE_TOOL`, `REFERENCE_POLICY`, `ORIGINAL` (placebo)};
  - `is_placebo`;
  - `expected_semantics` (free text, recorded).
  - `INJECTION_CLEAN_VALUE` is **not** an allowed source for localizers. Only the benchmark validator may use it (§8.5).
- **Intervention types (C2; not equivalent):**
  | Type | Boundary | Semantics | Placebo |
  |---|---|---|---|
  | `OBSERVATION_REPLACEMENT` | decision or tool | The original execution is re-applied unchanged (same faults, same state transition). Only the **delivered** value is replaced. | Replace the delivered value with the *original* delivered value |
  | `EXECUTION_REPLACEMENT` | tool only | The original execution (including its pre-/post-execution faults) is replaced by a **trusted clean execution**: lifecycle with the fault layer disabled *for this event only*. The clean state transition commits, and the delivered value is the clean raw result. | Re-run the *original* execution (faults enabled) through the same intervention path |
- **Unsupported cases (explicit result, never invented):**
  - `EXECUTION_REPLACEMENT` at a decision boundary → `UNSUPPORTED(no_state_transition_at_decision)`.
  - `OBSERVATION_REPLACEMENT` of a **mutating** tool when the original state transition differs from the reference execution's transition (e.g. a pre-execution timeout prevented a refund but the reference says "refunded") → `UNSUPPORTED(observation_inconsistent_with_state)`.
  - No trusted reference → `UNSUPPORTED(no_trusted_reference)`.
- **Phases:**
  1. **Prefix** (`seq < e*`): identical to Contract A. A mismatch yields `INVALID_COUNTERFACTUAL(prefix_diverged)`.
  2. **Intervention** (`seq = e*`): the request must match *R*'s request at *e\**. The replacement is applied according to its declared type, and the intervention record is written to the run header and to the event.
  3. **Cassette fence:** after *e\**, the cassette is **closed**. The handle is dropped and any lookup raises an error. Every downstream decision is recomputed by the live policy, and every downstream tool runs live in the sandbox. The fault plan stays active for *other* fault sites; triggers are predicates (e.g. "1st call to `get_order`"), not seq numbers, so they apply correctly to a changed path (documented).
  4. **Oracle:** evaluated on the *new* final state, using the same oracle version.
- **Output:** a new run *R′* with `mode=REPLAY_INTERVENE`, `parent_run_id=R`, the intervention record, its outcome, and an alignment report against *R* (§8.3, reporting only).
- **Invariant:** *R′*'s prefix is identical to *R*'s prefix (responses, sequence, state hashes). No cassette response is ever served at or after *e\**.

### 7.3 Contract C — Regression execution (`REGRESSION`)
- **Input:** a scenario + an **environment fixture plan**, plus a candidate agent configuration (policy version, prompt/source hash, tool implementations).
  - The fixture plan contains *environment-side* faults only: tool-output corruption, timeouts, wrong retrieval. Agent-side faults (wrong tool, bad args) are not fixtures; they represent agent bugs, which the candidate agent itself must not reproduce.
- **Behaviour:** a fresh execution from the initial snapshot. The declared environment fixture is applied through the normal fault stages. **No previous agent decisions are reused and no cassette object is constructed or passed in.** The runner has no cassette parameter at all. A test passes a store whose cassette accessors raise, and a second test puts a "poisoned" recording for the same scenario on disk and asserts the regression result is unaffected. The same declared oracle version is applied.
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
| Timeouts | Simulated only by the fault layer. **`TIMEOUT_BEFORE_COMMIT`** (stage `PRE_EXECUTION`): S3/S4 are skipped (`executed=false`, `committed=false`) and a timeout is delivered. **`LOST_ACK`** (stage `POST_EXECUTION`, operator F5): S3/S4 run and commit, then S5 replaces the ok raw result with a timeout. The observable event shows `status=timeout` **and** `committed=true` with the real delta. Both are verified by replay. |
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
1. `REFERENCE_TOOL`: re-executing a deterministic sandbox tool with the same args on a scratch copy of the same pre-state, with the fault layer disabled. This is the only source for `EXECUTION_REPLACEMENT` and for tool `OBSERVATION_REPLACEMENT`.
2. `REFERENCE_POLICY`: the scripted **reference policy** (the gold trajectory generator for the scenario), queried with the *recorded* prefix history. This is the only source for decision `OBSERVATION_REPLACEMENT`.
3. `INJECTION_CLEAN_VALUE`: the pre-injection value captured by the fault layer, stored only in the ledger/labels. It is used for **label validation by the benchmark validator** and is never available to localizers (leakage rule, §11.3).

For natural failures with no reference, the result is `NO_TRUSTED_REFERENCE` and no interventional claim is made. References are never fabricated (e.g. by an LLM).

**Placebo control:** every intervention has a placebo of the **same type** (§7.2) with `reference_source=ORIGINAL`. Under a deterministic policy, the placebo must reproduce *R*'s outcome and final state hash. Otherwise the result is `INVALID_COUNTERFACTUAL(machinery)`, which signals a bug. A step earns **`INTERVENTIONAL_REPAIR`** only if the reference intervention repairs the run (pass) **and** its placebo still fails. This is evidence that changing this step is *sufficient to repair this run*; it is **not** a unique causal explanation, since other steps may also repair it (they are all reported). In L2/L3 stochastic settings this becomes rates with CIs over *k* replays.

**Single-step limitations:**
- With two *jointly necessary* faults, each single intervention repairs, so both are flagged and the earliest is reported as decisive.
- With two *individually sufficient* faults, no single intervention repairs, so the result is `NOT_ISOLATED_BY_SINGLE_STEP`.
- Pairwise interventions and Shapley-style estimates (as in Causal Agent Replay [F]) are L2/L3. The L1 benchmark keeps ≤4 two-fault cases, **reported separately** to document this limitation.

## 9. Trace schema v1 (Pydantic, versioned)

> Authoritative definition: `docs/TRACE_SCHEMA.md`. The summary below predates C2. The authoritative schema adds:
> - the **observable trace** (`header.json`, `events.jsonl`, `footer.json`), readable by localizers;
> - a **privileged execution ledger** (`ledger.jsonl`: raw results, executed flags, fault applications with their stage), readable only by the replay engine and the benchmark validator;
> - a `StateTransition` record on tool events (`before_hash`, `after_hash`, `committed`, `delta`);
> - typed `Intervention` records (`intervention_type`, `reference_source`, `is_placebo`, `expected_semantics`).

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

- **Ground-truth isolation:** fault metadata is never placed in the trace models given to localizers.
  - Fault applications and raw results live in the **ledger**.
  - Benchmark labels (operator, site, clean value) live in `labels.jsonl`.
  - The localizer API takes the observable `Trace` type only, and the store exposes the ledger through a separately named method that localizer code must not import (enforced by a test).
- **Input/output references:** inline payloads in L1, because they are small. Each has a fingerprint so L2 can move payloads to a content-addressed blob store without changing semantics.
- **Redaction hook:** a `Redactor` interface exists and is applied before persistence; L1 data is synthetic, so the default is a no-op with a canary test. Real redaction rules arrive in L2.
- **Ordering:** `seq` is authoritative; timestamps are informational only.
- **Integrity:** a hash chain over `(seq, event_fp)`, verified on load. It detects truncation and corruption, but it is not a security control.
- **Versioning:** semver; minor = additive; the loader rejects unknown majors.
- **Persistence:** `runs/<run_id>/{header.json, events.jsonl, ledger.jsonl, footer.json}`, written to a temp directory and atomically renamed. `cassette` = the observable event list + ledger of a RECORD run (no separate format).

## 10. Minimal fault-injection design

The fault layer sits inside `BoundaryGateway` as **transforms** on delivered values (or as execution modifiers for timeouts), driven by a declarative `FaultPlan` of triggers (predicates over boundary, name, occurrence, args).

| Op | Boundary | **Stage (C2)** | Mechanism (example) | Failure mechanism exercised | Expected category |
|---|---|---|---|---|---|
| **F1 Wrong tool selection** | decision | `DECISION` | replace the chosen tool, e.g. `issue_refund` → `close_ticket(DENIED)` | control flow | TOOL_SELECTION |
| **F2 Invalid/wrong arguments** | decision | `DECISION` | drop a required arg, or swap `order_id` for another of the customer's orders | argument validity vs. semantic error | TOOL_ARGUMENT |
| **F3 Corrupted tool output** | tool | `POST_EXECUTION` | `get_order.total` ×10, or status `delivered`→`shipped` | data integrity; often **delayed effect** | TOOL_OUTPUT |
| **F4 Incorrect retrieval** | tool (`search_policy`) | `POST_EXECUTION` | return a plausible but wrong (archived) policy doc with a different limit | retrieval; **delayed effect** | RETRIEVAL |
| **F5 Lost-ack timeout** | tool (`issue_refund`) | `POST_EXECUTION` | commit, then deliver a timeout; policy v1 retries without an idempotency key → duplicate refund | state, retries, idempotency | STATE / INFRASTRUCTURE |
| **D1 Decoy (harmless deviation)** | decision | `DECISION` | insert a redundant read (`get_customer` again) | tests false attribution | — (never causal by design; verified) |
| *T0 Timeout before commit* (test fixture, not a benchmark operator in the committed scope) | tool | `PRE_EXECUTION` | skip execution, deliver a timeout | pre-execution semantics | INFRASTRUCTURE |

**Delayed effect:** F3/F4 at the `get_order` / `search_policy` steps surface at `issue_refund` / `close_ticket` 1–3 steps later. Each instance stores `symptom_distance = symptom_seq − fault_seq`.

**Label validation (per instance):**
- Clean run of the template → must **pass** (otherwise the template is a bug).
- Faulty run → **fail** labels the instance `CAUSAL`; **pass** labels it `MASKED` (kept, reported, excluded from the localization table).
- For `CAUSAL`: the validator's intervention with `INJECTION_CLEAN_VALUE` at the fault site must repair the run. This confirms the label. The validator is a **separate program** from the localizers and runs before them; localizers never receive its outputs.
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
| B4 | Earliest reference deviation | REFERENCE_DEVIATION | earliest event whose delivered value ≠ its trusted reference. A strong but honest baseline: it finds deviations, not causes. Decoys and masked deviations expose it |
| CF | Placebo-controlled single-step counterfactual | **INTERVENTIONAL_REPAIR** where supported | see below |

**CF algorithm**
```
candidates ← decision/tool events with seq ≤ symptom_seq, ordered by B3 rank
for e in candidates:
    ref ← trusted_reference(e)            # REFERENCE_TOOL (tool) or REFERENCE_POLICY (decision)
    if ref is None:            label[e] ← UNSUPPORTED(no_trusted_reference); continue
    if fp(ref) == fp(delivered[e]) and state_transition_matches(e, ref):
                               label[e] ← SUSPICION (B3 score only); continue   # consistent with reference
    label[e] ← REFERENCE_DEVIATION
    itype ← EXECUTION_REPLACEMENT if e is a tool event else OBSERVATION_REPLACEMENT
    r_ref ← REPLAY_INTERVENE(R, e, itype, ref)              # Contract B
    r_plc ← REPLAY_INTERVENE(R, e, itype, ORIGINAL, placebo) # same-type placebo
    if r_ref or r_plc is UNSUPPORTED:  label[e] ← UNSUPPORTED(reason); continue
    if r_plc invalid or r_plc.outcome ≠ R.outcome: flag INVALID_COUNTERFACTUAL (bug); continue
    if r_ref.outcome == pass:  label[e] ← INTERVENTIONAL_REPAIR
ranking  ← [INTERVENTIONAL_REPAIR by seq] + [REFERENCE_DEVIATION by seq] + [rest by B3]
run_conclusion ← "repair sites: {all INTERVENTIONAL_REPAIR}" or NOT_ISOLATED
report replays_used, unsupported_count, wall_ms
```
For tool events, CF uses `EXECUTION_REPLACEMENT` by default, because it is the only type that is faithful for mutating tools. `OBSERVATION_REPLACEMENT` on tools is used where it is supported (read-only tools, or a mutating tool whose original transition matches the reference) and is reported separately in Metric B.
Complexity: *m* ≤ n candidates × 2 replays × O(n) events = O(n²) boundary operations. With n ≈ 8–15 this is milliseconds. Exhaustive evaluation is fine in L1, and cost-aware selection is the L3 question. The placebo for deterministic runs doubles as a continuous replay-machinery self-test.

### 11.3 Metrics (C3): three families, always reported separately
Results are reported as **counts k/n plus Wilson 95% CIs**, given the small n. Nothing is reported before it has been run (no invented results).

**Metric A: injection-site localization.** Does the ranking put the *known injected site* on top? Computed on `CAUSAL` single-fault test-split instances.
- Top-1, Top-3, MRR (rank of the injected `seq`).
- Broken down by fault operator and by `symptom_distance` (0 vs. ≥1).
- Decoy false-attribution rate (top-1 = decoy step).
- Note: the injection site is a *label of where we perturbed the run*. It is the ground truth for A only.

**Metric B: interventional repair.** Measures what the interventions actually showed, independently of the label.
- Repair success rate: instances with ≥1 `INTERVENTIONAL_REPAIR` / instances investigated.
- Injected-site repair rate: the injected site itself repairs (the validator computes this from labels after the localizer finishes).
- **Multiple-repair-site cases**: instances with ≥2 repairing steps, listed with their steps.
- Placebo validity rate: placebos reproducing the original outcome and final state / placebos run. Required = 1.0 for the deterministic policy; any lower value is a bug.
- Unsupported intervention rate, by reason.
- Replay executions per investigation (reference + placebo).
- Intervention type used (observation vs. execution) per repair.

**Metric C: diagnostic evidence.** The distribution of per-step labels `SUSPICION` / `REFERENCE_DEVIATION` / `INTERVENTIONAL_REPAIR` / `UNSUPPORTED`, and of run conclusions (repair sites found vs. `NOT_ISOLATED`), for each method. The report must state that `INTERVENTIONAL_REPAIR` means "sufficient to repair this run under this intervention", not "the unique cause".

Also reported:
- Classifier confusion matrix (stretch scope).
- Two-fault cases: a qualitative table only, documenting single-step limitations (jointly necessary faults → several repair sites; individually sufficient faults → `NOT_ISOLATED`).

**Leakage rules.**
1. Localizers receive only the observable `Trace` plus the trusted-reference API.
2. They never receive the ledger, `labels.jsonl`, fault plans or `INJECTION_CLEAN_VALUE`.
3. The benchmark validator and metrics code may read labels; localizer modules may not import them (test-enforced).
4. The dev/test split is by template, and the configuration is frozen before the test run.

## 12. Revised benchmark design ("AgentTrace-Synth v0")
- **8 scenario templates** (support domain):
  - T1 damaged item within limit → refund
  - T2 amount above tier limit → escalate
  - T3 final-sale item → deny + close
  - T4 not yet delivered → close the ticket as `PENDING_DELIVERY`, with no refund
  - T5 refund already issued → no new refund
  - T6 multi-order customer → refund the correct order
  - T7 partial refund of one line item
  - T8 gold-tier extended limit
- **Clean set:** 8 runs, which must all pass.
- **Fault instances:** templates × applicable operators × 1–2 sites, generated automatically. **Target 40–60 instances** after filtering inapplicable combinations, including **≥8 with symptom_distance ≥ 1**, **~8 decoy-augmented** (a decoy plus a causal fault in one run), and **≤4 two-fault** cases (reported separately).
  - The count is set by available hours: generation is automatic, but each operator, template and oracle needs hand-verification.
  - MASKED instances are kept and counted.
- **Committed vs. stretch templates (C1):** the committed minimum is T1, T2, T3, T5, T6; T4, T7, T8 are stretch. To keep the split stable whichever set exists, it is fixed as **dev = T1–T4, test = T5–T8**. (v0.2 had T1–T5 / T6–T8; this changed because the committed set must contain test templates.)
- **Splits by template** (prevents leakage via shared structure): dev and test as above. Rule weights, classifier order and any thresholds are frozen (git tag `bench-freeze-v0`) before the single test-split run. Every test-split evaluation is logged.
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
| 9 | S-REF-01 + F5 (lost-ack, `POST_EXECUTION`, on the 1st `issue_refund`), policy v1 | R₄: timeout → retry without key → **duplicate refund** (fail) | REPLAY_STRICT | timeout re-delivered; commit re-applied for **both** attempts | R₄ final: 2 refunds | metrics = 1.0; refunds = 2; the 1st refund event has delivered `status=timeout` **and** `committed=true`, `after_hash ≠ before_hash`; its ledger raw result is ok |
| 10 | S-REF-01 with max_steps=3 (early termination) | R₅ status MAX_STEPS | REPLAY_STRICT | stops at the same point with the same status | partial state equal to R₅ | equal event count, final hash, status MAX_STEPS; TRUNCATED/EXTRA_EVENT not raised |
| 11 | S-REF-01 + F4 (wrong policy doc: limit 50) | R₆ fail (escalated wrongly) | REPLAY_INTERVENE, `EXECUTION_REPLACEMENT` at the `search_policy` seq with REFERENCE_TOOL | prefix identical; suffix live; **downstream branch changes** (escalate → refund + close) | F₀-equivalent (refund 80.00, T1 REFUNDED) | prefix metrics = 1.0; outcome pass; `cassette_access_after_fence == 0`; the run header records type, source, target and semantics |
| 12 | same as 11 | R₆ | REPLAY_INTERVENE at the `get_customer` seq with REFERENCE_TOOL (no-op difference) **and** at the decoy seq | no repair | same as R₆ | outcome fail; tier ≠ INTERVENTIONAL; no-op detected as CONSISTENT_WITH_REFERENCE without replay |
| 13 | same as 11 | R₆ | placebo: REPLAY_INTERVENE, `EXECUTION_REPLACEMENT` with ORIGINAL (faults enabled) at the `search_policy` seq; and an `OBSERVATION_REPLACEMENT` placebo | each reproduces R₆ exactly through the live suffix | R₆ final hash | outcome and final hash equal R₆; the event sequence equals R₆'s; `is_placebo=true` recorded |
| 14 | S-REF-01 + F5 fixture | baseline: policy v1 R₄ (fail) | REGRESSION with policy v2 (uses idempotency keys / checks refunds before retry) | fresh execution; no cassette constructed | 1 refund, T1 REFUNDED | verdict DETERMINISTIC_PASS (two identical fingerprints); a cassette-store spy records 0 accesses; REPLAY_STRICT of R₄ under the v2 config → CONFIG_MISMATCH |
| 15 | all available clean templates | record each | run each template 5× interleaved in one process, plus exact replays in between | no cross-run leakage | each equals its own recording | identical **semantic** fingerprints (excluding run/span ids and wall-clock fields) and final hashes across repeats; the original scenario snapshot object is unchanged (hash before == after) |

**Added focused tests (C2): they extend the matrix and weaken nothing above.**
| # | Initial state | Recorded execution | Modification / intervention | Expected behaviour | Expected final state | Assertion |
|---|---|---|---|---|---|---|
| 16 Pre-execution timeout | S-REF-01 + T0 (`PRE_EXECUTION` timeout on the 1st `issue_refund`), policy v1 | R₇: timeout (not executed) → retry → 1 refund (pass) | REPLAY_STRICT | the 1st attempt is again not executed | 1 refund | 1st refund event: `executed=false`, `committed=false`, `after_hash == before_hash`, delivered timeout; ledger has the `PRE_EXECUTION` application and no raw result |
| 17 Observation vs. execution replacement differ | S-REF-01 + F5, policy v1 | R₄ (duplicate refund) | (a) `OBSERVATION_REPLACEMENT` at the 1st `issue_refund` with REFERENCE_TOOL output (ok ack); (b) `EXECUTION_REPLACEMENT` at the same seq | (a) the original commit is kept and only the ack changes → no retry; (b) a clean execution commits → no retry | (a) and (b) both 1 refund; the intervention records differ in type | both pass; (a) the event's state transition equals R₄'s at that seq; (b) the transition comes from the clean execution; the types are recorded and **not** conflated |
| 18 Unsupported observation replacement | S-REF-01 + T0 (pre-exec timeout), policy v1 | R₇ | `OBSERVATION_REPLACEMENT` at the 1st `issue_refund` with REFERENCE_TOOL output (says "refunded", but nothing was committed) | refused | not persisted as a counterfactual | result `UNSUPPORTED(observation_inconsistent_with_state)`; no outcome is reported. Also: `EXECUTION_REPLACEMENT` at a decision seq → `UNSUPPORTED(no_state_transition_at_decision)` |
| 19 Execution-replacement placebo | S-REF-01 + F5, policy v1 | R₄ | `EXECUTION_REPLACEMENT` placebo (ORIGINAL execution, faults enabled) at the 1st `issue_refund` | reproduces the lost ack and the duplicate | R₄ final (2 refunds) | outcome fail; final hash = R₄'s |
| 20 Regression ignores a poisoned cassette | S-REF-01 + F5 fixture | R₄ (v1) stored in the same run store; additionally a hand-edited recording whose decisions would pass | REGRESSION with policy v1 and then v2 | fresh execution in both | v1: 2 refunds (fail); v2: 1 refund (pass) | v1 still fails (proving recorded decisions were not reused); v2 passes; the cassette-access spy = 0 |
| 21 Idempotent retry replays exactly | S-REF-01 + F5, policy v2 | R₈: timeout → retry with the same key → idempotent hit (pass) | REPLAY_STRICT | the 2nd attempt executes but commits **no** new refund | 1 refund; `idempotency_log` has 1 key | 2nd attempt: `executed=true`, `committed=false` (no state change), delivered ok with the original refund id; metrics = 1.0 |

**Coverage of the C2 list:** pre-execution timeout (#16, #18), post-commit lost ack (#9, #17, #19), duplicate retry (#9, #20), idempotency (#14, #21), observation replacement (#13, #17, #18), execution replacement (#11, #17, #19), placebo (#13, #19), state-hash divergence (#7), changed downstream branches (#6, #11), regression without cassette access (#14, #20).

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

## 17. Four-week implementation plan (C1: committed 50 h + ≥6 h debugging = 56 h)

**Time model [A]:**
- 2–3 h/day for 28 days = 56–84 h available.
- The **committed MVP** is planned at **50 h**, with **≥6 h reserved for debugging**, so it fits in **56 h**, the minimum available.
- **Stretch** work (+16 h, up to 66 h) starts only when the committed tasks of the current week are DONE and verified.
- Anything above 66 h (up to 84 h) is unallocated slack.
- Hours are focused development hours, not calendar time. The task-level tracker is `docs/TASKS.md`.

### Week 1: Foundation (committed 13 h)
| ID | Task | h |
|---|---|---|
| W1.0 | Repo + tooling (uv, ruff, mypy, pytest, CI); ADRs | 1.0 |
| W1.1 | Trace schema v1 (observable models + ledger models, intervention/state-transition metadata), canonical JSON, fingerprints, semantic fingerprint | 2.5 |
| W1.2 | `TraceStore` protocol + JSONL store (atomic dir write, validation, hash chain, corruption/incomplete detection) | 1.5 |
| W1.3 | Support env: state model, 5 tools, transactional commit, snapshot/restore/hash, idempotency, audit, deltas | 3.0 |
| W1.4 | Runtime: BoundaryGateway with the 7-stage lifecycle and fault-hook seam (no operators yet), AgentLoop, ScriptedPolicy v1/v2, ReferencePolicy interface, max-step guard | 2.5 |
| W1.5 | Declarative scenarios (≥ committed 5 templates) + deterministic oracle | 1.5 |
| W1.6 | CLI: `atrace run`, `atrace scenarios`, minimal `atrace show` | 1.0 |
- **Deliverable:** `atrace run T1` executes, prints PASS/FAIL and the run id, and persists the trace.
- **Acceptance (CP1):** quality gates 1–12 of the kickoff brief: install, CLI, clean scenarios pass, snapshot hash round-trip, identical semantic fingerprints over repeated runs, mutation isolation, no external side effects, serialization round-trip, ruff, mypy, pytest, valid CI config.

### Week 2: Record / exact replay (committed 14 h)
| ID | Task | h |
|---|---|---|
| W2.1 | Cassette (positional, consume-once, full-key match) + config fingerprint check | 2.0 |
| W2.2 | ExactReplayer: lifecycle re-application, fault-plan replay, verification of state/raw/delivered, all divergence kinds | 4.0 |
| W2.3 | Fidelity report (§8.4) | 1.0 |
| W2.4 | CLI `atrace replay`; `show` displays state transitions | 1.0 |
| W2.5 | Acceptance tests #1–#10, #15, #16, #21 (with test-only fault hooks for #9/#16/#21) + property tests P1, P4 | 5.0 |
| W2.6 | REPLAY_SPEC review against the implementation | 1.0 |
- **Acceptance (CP2):** the listed tests pass; zero divergence on unmodified recordings; every perturbation detected with the correct kind.

### Week 3: Faults, counterfactuals, regression, localization (committed 14 h)
| ID | Task | h |
|---|---|---|
| W3.1 | Fault layer: stage-declared operators F1–F5 + D1 (+ T0 fixture), FaultPlan triggers, ledger fault applications, labels sidecar | 3.0 |
| W3.2 | Benchmark generator + label validation (CAUSAL/MASKED, decoys) + split file | 2.5 |
| W3.3 | CounterfactualRunner: both intervention types, unsupported detection, fence, same-type placebo; tests #11–#13, #17–#19 | 4.0 |
| W3.4 | RegressionRunner + fixtures; tests #14, #20 | 1.5 |
| W3.5 | Validators; baselines B1, B3, B4 | 2.0 |
| W3.6 | CF localizer + Markdown investigation report (evidence labels) | 1.0 |
- **Acceptance (CP3, CP4):** all of tests #1–#21 pass; labels validated; placebo validity = 1.0 on the dev split.

### Week 4: Evaluation & release (committed 9 h)
| ID | Task | h |
|---|---|---|
| W4.1 | `bench run`: Metric A/B/C tables with Wilson CIs + manifest | 2.5 |
| W4.2 | Dev run, fixes, freeze tag, single test-split run | 2.0 |
| W4.3 | README results + limitations; docs consistency pass | 2.5 |
| W4.4 | `make demo` script + recorded terminal session (asciinema or screen recording) | 1.0 |
| W4.5 | NEXT.md (Phase 2A plan) | 1.0 |
- **Acceptance (CP5):** `make reproduce` regenerates identical tables from a clean clone.

**Committed total: 13 + 14 + 14 + 9 = 50 h, plus ≥6 h debugging = 56 h.**

**Never cut from the committed scope:** the three replay contracts; both intervention types with same-type placebos and explicit UNSUPPORTED results; the cassette fence; acceptance tests #1–#21; validated labels; leakage rules; an honest results table.

## 18. Stretch scope (+16 h, only if time permits; ordered by value)
| ID | Stretch item | h |
|---|---|---|
| S1 | Templates T4, T7, T8 (if not already done in W1.5) | 1.0 |
| S2 | Property tests P2 (random-state record → replay invariant) and P3 | 1.5 |
| S3 | Rule-based failure classifier + confusion matrix | 2.0 |
| S4 | Baseline B2 (last failed tool) | 0.5 |
| S5 | LCS/Needleman-Wunsch alignment report after branching (committed scope reports the first divergence only) | 2.0 |
| S6 | Two-fault cases (≤4) and their qualitative table | 1.0 |
| S7 | Decoy-augmented instances expanded to ~8 | 0.5 |
| S8 | Rich timeline view in `atrace show` | 1.5 |
| S9 | Benchmark smoke job in CI; `pip-audit` step | 1.0 |
| S10 | import-linter / module-boundary test; schema JSON-schema export | 1.0 |
| S11 | EVALUATION.md and SECURITY.md as standalone docs (committed scope keeps them as README sections) | 2.0 |
| S12 | Short narrated demo video | 0.5 |
| S13 | Extra robustness tests (fuzzed corrupted traces, store edge cases) | 1.5 |
| **Total** | | **16.0** |

If even the committed scope is at risk (CP2 failing by the end of week 2), the order of deferral is: W4.4 demo recording → W3.5 B3 (keep B1, B4) → W4.1 Metric C breakdown (keep the raw label counts). Replay correctness work is never deferred in favour of features.

## 19. Go/no-go checkpoints
| CP | When | Required evidence | Tests that must pass | Failure condition | If it fails |
|---|---|---|---|---|---|
| **CP1** Deterministic agent | end of week 1 | all implemented clean templates (≥ committed 5) pass; identical **semantic** fingerprints over repeated runs; Week 1 quality gates 1–12 met | env/tool unit tests, gateway lifecycle tests, snapshot round-trip, oracle tests, store tests | any template fails, or nondeterministic semantic fingerprints | stop feature work; defer stretch templates; fix determinism (hidden mutable state, Decimal, ordering) |
| **CP2** Exact replay | end of week 2 | fidelity = 1.0 on all clean + sample faulty recordings; every perturbation detected with the correct kind | #1–10, #15, #16, #21, P1, P4 | any silent pass on a perturbed cassette, or a mismatch on an unmodified one | **no counterfactual work until fixed**; freeze all stretch items; apply the §18 deferral order; drop the CLI polish |
| **CP3** Validated faults | mid week 3 | every instance labelled CAUSAL/MASKED by validation; ≥8 delayed-effect CAUSAL; decoy-only runs pass | generator/label tests | labels not reproducible; too few delayed-effect cases | reduce operators to the 3 that validate cleanly; add templates rather than operators |
| **CP4** Controlled counterfactual | end of week 3 | ≥1 demonstrated repair with a failing same-type placebo for **each** intervention type; correct UNSUPPORTED results; no fence violations | #11–14, #17–20 | placebo ≠ original, or cassette access after the fence | defer B3 and all stretch items; fix the machinery; the demo uses exact replay + baselines only |
| **CP5** Reproducible results | end of week 4 | `make reproduce` on a fresh clone yields identical Metric A/B/C tables + manifest | full suite in CI (benchmark smoke job is stretch S9; run locally otherwise) | non-identical output | defer the video; fix determinism; publish without results rather than with irreproducible ones |

Replay correctness takes priority over all CLI/report/UI work at every checkpoint.

## 20. Testing and quality assurance
- **Layers:** unit (pure functions, tools, validators) → acceptance (§13 matrix) → property (P1–P4) → golden traces (recorded runs checked in as fixtures; a schema change requires an explicit fixture update) → benchmark smoke (dev split).
- **Determinism guards:** a test forbids `random`, `time`, `uuid`, `datetime`, `secrets`, `subprocess`, `socket`, `requests`/`httpx`/`urllib` imports in `env/` and `policies/`. `runtime/` may obtain run/span ids only via `trace/ids.py`; these ids are excluded from semantic fingerprints.
- **Leakage guard:** a test asserts that the localizer entry points receive the observable `Trace` type (no ledger, no labels), that `localize/` never imports the ledger/label loaders, and that `labels.jsonl` is only read by `bench/validate.py` and `bench/metrics.py`.
- **Coverage target (engineering goal, not a result):** ≥85% line coverage on `replay/`, `runtime/`, `trace/`.
- **Security-aware engineering:** tools are pure Python over in-memory state; no `subprocess`/`socket`/`requests`/`eval` in `env/` (enforced by test); trace loading uses Pydantic validation with size and depth limits, never pickle; dependencies are pinned in `uv.lock`, with `pip-audit` in CI (cheap) and `gitleaks` pre-commit.
- **Review ritual:** end each session with an AI-assisted diff review focused on replay invariants.

## 21. Long-term engineering roadmap (Level 2, ordered by dependency and value)

**C4: GenAI-relevance phases come first, after the committed MVP (CP5) is done. None of them starts during Weeks 1–4.**

- **Phase 2A: Real LLM agent integration.**
  - An optional `LocalLLMPolicy` (llama.cpp or Ollama), evaluating small 4-bit models that fit 8 GB alongside an IDE (~0.5B–3B; §15 gate).
  - Structured action generation: JSON-schema-constrained decisions, or native tool calling where the model supports it.
  - Actual model decisions are recorded at the `decision` boundary (raw text + parsed decision in the ledger; the delivered decision in the trace).
  - Measure clean-task success, decision latency and peak RSS (all measured, none assumed).
  - Exact replay stays deterministic via cassettes; fresh inference is labelled stochastic.
  - Tests: parsing failures, stochastic regression verdicts (`PROBABILISTIC` with Wilson CI), replay of LLM runs without model access.
- **Phase 2B: Framework integration.** A minimal LangGraph adapter mapping node and tool invocations to `BoundaryGateway` events; record vs. live comparison; one documented investigation of a real (non-injected) agent failure, reported with `ground_truth=UNKNOWN`.
- **Phase 2C: Developer interface.** A FastAPI backend over `TraceStore`; a React trace viewer (timeline, state transitions); a run-comparison view; an investigation view with evidence labels.

Then, in dependency order:
1. **SQLite `TraceStore`** + run index/query; content-addressed payloads; redaction rules.
2. **Hierarchical ddmin** (Zeller & Hildebrandt 2002 [K]) over scenario components, with failure-signature preservation → minimized regression tests.
3. **Regression management:** versioned tests, suites, baseline-vs-candidate history, recurrence signatures, a GitHub Action.
4. *(moved to Phase 2A)* Local LLM policy.
5. *(moved to Phase 2B)* LangGraph adapter.
6. *(moved to Phase 2C)* FastAPI + React; React Flow DAG later.
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
- **Deterministic testing:** a 21-case replay acceptance matrix plus property tests.
- **Observability:** a versioned trace schema, fingerprints, hash chains, fidelity metrics.
- **Failure analysis:** a fault taxonomy, stage-declared fault operators, evidence labels kept separate from localization accuracy (Metrics A/B/C).
- **Algorithm design:** taint-style origin tracing, placebo-controlled interventions, sequence alignment.
- **Benchmarking:** validated labels, template-level splits, freeze-then-test, CIs.
- **Security-aware engineering:** sandboxing, permission validation, tool-output manipulation, no unsafe execution.
- **Reproducibility:** one-command regeneration with a manifest.

**Gap to acknowledge in interviews:** L1 has no real LLM. Answer: "the boundaries are model-agnostic by design; the next milestone plugs in a small local model and a LangGraph adapter, and the replay contracts were designed precisely for stochastic policies." Phases 2A–2B then demonstrate hands-on LLM engineering (tool-calling prompts, small-model reliability measurement, framework integration).

**3-minute demo (CLI)**
1. *0:00–0:20* `atrace run T6` → the agent resolves a multi-order refund; the oracle passes; trace tree shown.
2. *0:20–0:40* `atrace inject T6 --op F4` (wrong policy document retrieved at step 3) → run fails at `close_ticket`/`issue_refund` 2 steps later; violated clause shown.
3. *0:40–1:00* `atrace show <run>`: the failure is recorded with state hashes; the earliest visible error points at the refund step.
4. *1:00–1:20* `atrace replay <run>` → fidelity report: all metrics equal; deterministic reproduction, with no model or tool side effects outside the sandbox.
5. *1:20–2:10* `atrace investigate <run>`:
   - Baselines B1/B3 blame the symptom step (SUSPICION).
   - B4 flags `search_policy` as REFERENCE_DEVIATION.
   - CF applies an EXECUTION_REPLACEMENT with the trusted reference → **pass**; same-type placebo → **fail** → `INTERVENTIONAL_REPAIR` ("sufficient to repair this run", not a unique cause). The decoy step is consistent with its reference.
6. *2:10–2:40* Show the evidence section: prefix identical, fence respected, the downstream path changed (alignment diff), the new final state.
7. *2:40–3:00* The results table from the frozen test split (with CIs and limitations), plus `atrace regress` with the F5 fixture: v1 fails, v2 DETERMINISTIC_PASS.

**Resume bullet structures** (fill only with measured values): "Engineered a deterministic record/replay engine for tool-using agents with state re-application and fail-closed divergence detection, verified by a *[N]*-case acceptance matrix and property-based tests" · "Built a fault-injection benchmark of *[N]* validated failures across *[K]* operators; placebo-controlled counterfactual localization achieved Top-1 *[k/n]* vs. *[k/n]* for an earliest-error baseline (95% CI *[…]*)".

## 24. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Hidden nondeterminism (dict order, floats, time, ids) | State-counter ids (ADR-008); Decimal; canonical JSON; banned-import test; CP1 |
| Replay engine larger than estimated | Weeks 2–3 ordered so replay correctness is done first; stretch frozen and the §18 deferral order applied at CP2 |
| Wrong cassette reuse after branching | Positional matching + full-key verification + fence + fail-closed; tests #6, #11, #20 |
| Observation vs. execution intervention confusion | Typed interventions, explicit UNSUPPORTED cases, same-type placebos; tests #17–#19 |
| Benchmark too easy / circular (references exist for every step) | Decoys, masked faults, delayed effects, an explicit B4 baseline, a stated limitation |
| Label leakage | Sidecar labels; type-level separation; leakage test; template splits; a freeze tag |
| Small n → weak conclusions | Report k/n + Wilson CIs; no percentage claims without counts |
| "No LLM" weakens placement value | Model-agnostic boundaries; L2 local-LLM + LangGraph as the immediate next milestone; prepared interview answer |
| Scope creep from other projects | Hours ledger in TASKS.md; checkpoints; cut list |
| Accidental disclosure of research ideas | Separate private repo; public docs restricted to published concepts; IPR decision points |
| 8 GB memory pressure later | No Docker in L1; small models only after the gate; sequential runs |

## 25. Assumptions and remaining decisions

**Assumptions [A]:**
- 2–3 h/day: the committed scope assumes 2 h/day (56 h); stretch assumes more.
- Python 3.12 and uv are acceptable.
- GitHub is used for the public repo (with a private repo for research).
- A terminal-based demo is acceptable for the target recruiters.
- Synthetic, scripted ground truth is acceptable for L1 claims if limitations are stated.
- Memory/runtime figures marked [E] will be measured in week 2.

**Decisions recommended (accept or override):**
1. Domain: **customer support / order management** (5 tools, state-based oracle, natural mutating/idempotency semantics).
2. Licence: **Apache-2.0 public foundation + private, unlicensed research repo**, pending IPR-cell confirmation. **Not applied yet:** no LICENSE file is added until you approve it (ADR-010).
3. CLI = Typer + Rich; persistence = JSONL.

**Still open [Q]** (none block week 1):
- Q1: Can you reach the university IPR cell before week 4, i.e. before the public release, to confirm the licensing/disclosure approach? If not, release the public foundation anyway (it contains no candidate-inventive material) and hold everything else.
- Q2: Public repo visibility during development: public from day 1 (better commit history signal) or private until v0.1.0? I recommend private until CP5, then public.

---

## Internal consistency check
| Question | Answer |
|---|---|
| Committed scope fits 56 h? | Yes: 13+14+14+9 = **50 h** + ≥6 h debugging = 56 h (§17) |
| Stretch bounded? | Yes: +16 h (§18) → 66 h; 84 h maximum leaves 18 h unallocated |
| Replay contracts and core tests in the committed scope? | Yes: W2.1–W2.5, W3.3–W3.4; tests #1–#21 are committed |
| Runs without paid APIs? | Yes: no LLM at all in L1; hosted policy is L2, opt-in |
| Runs on an 8 GB M2? | Yes: no Docker/LLM/DB server; KB-sized states; sequential runs ([E] to be measured in week 2) |
| Replay engine well specified? | Lifecycle (§7.0), contracts A/B/C with typed interventions (§7), state semantics (§8.2), invariant (§8.2), identity layers (§8.3), fidelity metrics (§8.4), 21 tests (§13); authoritative detail in REPLAY_SPEC.md |
| Exact replay vs. regression separated? | Yes: regression constructs no cassette (spy-tested); config mismatch refuses strict replay (#14) |
| State mutations handled correctly? | Transactional commits, re-application + hash verification, idempotency, lost-ack, interrupted replay (§8.2; tests #7, #9, #15) |
| Step identity robust to branching? | Positional + full-key match only before the fence; live execution after; reporting-only alignment (§8.3; tests #6, #8, #11) |
| Causal claims controlled? | Trusted references only; same-type placebo required; Metrics A/B/C separated; a repair is not a unique cause; single-step limitations stated (§8.5, §11.3) |
| Demonstrable without a frontend? | Yes: CLI demo script (§23) |
| Research preserved? | Yes: L3 roadmap (§22), private repo, decision points |
| Placement-relevant to GenAI roles? | Yes for agent reliability/eval/backend; LLM hands-on is Phases 2A–2C (C4), directly after the MVP |
| Assumptions identified? | §25 + [A]/[E] labels inline |
