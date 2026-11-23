# Replay Specification (authoritative)

> This document is **authoritative for replay semantics**. Serialized field definitions are in `TRACE_SCHEMA.md`. Any behaviour change to recording or replay must be made here **before** it is made in code (TASKS.md rule).
>
> **Implementation status:** §3–§4 (lifecycles) and §5.1 (RECORD): Week 1. §5.2 (REPLAY_STRICT), §6–§8, §11–§12: Week 2. §5.3 (REPLAY_INTERVENE), §5.4 (REGRESSION), §10 (interventions) and §14 (experiments and localization service): Week 3.

## 1. Scope
The contracts cover a single-agent, tool-using runtime whose external interactions all pass through one choke point, the **BoundaryGateway**. The MVP environment is an in-memory, deterministic, synthetic support/order system. Nothing in this spec permits calls to real external systems.

## 2. Terminology
| Term | Meaning |
|---|---|
| Boundary | A point where the agent interacts with something outside its own pure logic. Kinds: `DECISION`, `TOOL` (and the reserved kinds `CLOCK`, `IDGEN`). `AGENT_STEP` is a structural span, not a boundary. |
| Event | One observable record in `events.jsonl`, with a per-run sequence number `seq`. |
| Raw output | For a decision, what the policy returned. For a tool, what the tool implementation returned (S3). |
| Delivered output | What the agent actually observes after fault transforms (S5/D2). |
| State transition | `before_hash`, `after_hash`, `committed`, `delta` of the environment for a tool event. |
| Ledger | The privileged per-event record of raw outputs, `executed` flags and fault applications (`ledger.jsonl`). |
| Cassette | The observable events + ledger of a recorded run, used for strict replay. |
| Fence | The point after which no cassette lookups are allowed. |
| Trusted reference | A replacement value from an authorized mechanism (§10.2). |

## 3. Tool execution lifecycle (S1–S7)
All four facts are kept separate: **(a) state transition**, **(b) raw result**, **(c) fault applications**, **(d) delivered response**. A delivered timeout never implies that no mutation happened.

| Stage | Behaviour | Effect on records |
|---|---|---|
| **S1 Validate** | The tool name must exist in the manifest, and the args must parse against the tool's Pydantic args model. On failure, the **gateway** produces the response `ERROR(UNKNOWN_TOOL | INVALID_ARGUMENTS)`; S2–S4 are skipped, and S5 receives this response. There is no raw tool result, because nothing executed. | `executed=false`; ledger `raw_output = null` |
| **S2 Pre-execution faults** | Each `PRE_EXECUTION` fault whose trigger matches may return a response (e.g. a timeout) that **prevents** execution. S3–S4 are then skipped. | ledger: fault application `effect=prevented_execution`; `executed=false`; raw = null |
| **S3 Execute** | The tool runs against an **isolated working copy** (a deep copy) of the current state. | `executed=true`; raw result in the ledger |
| **S4 Commit / roll back** | If the tool is mutating, the raw result is ok, and the working copy differs from the current state, the working copy **replaces** the current state atomically (`committed=true`). Otherwise the working copy is discarded (`committed=false`). For a read-only tool, a working copy that differs from the current state is a programming error (`ReadOnlyToolMutatedState`) and aborts the run. | observable `StateTransition` with the delta |
| **S5 Post-execution faults** | Each `POST_EXECUTION` fault whose trigger matches transforms the response. Its input is the raw result, or the S2 response if execution was prevented. **The state transition is never modified at this stage.** | ledger: fault application `effect=transformed_output` |
| **S6 Deliver** | The agent receives only the delivered response. | observable `response`, `status` |
| **S7 Record** | Append the observable event and ledger entry with the same `seq`. | — |

**`committed` definition:** `true` iff S4 replaced the state with a different state (non-empty delta). An idempotent retry that returns an existing refund executes (`executed=true`) but does not commit (`committed=false`, `after_hash == before_hash`).

**Attempt numbering:** `attempt` = 1 + the number of earlier tool events in the run with the same `request_fp`.

**Atomicity:** an exception inside a tool implementation is converted to `ERROR(TOOL_EXCEPTION)` with no commit. Partial commits are impossible by construction (S4 is a single reference swap). A partial-commit fault is a Level 2 operator.

## 4. Decision lifecycle (D1–D4)
| Stage | Behaviour |
|---|---|
| D1 Decide | `policy.decide(task, history)` returns the raw Decision. The request recorded is `{policy_id, policy_version, history_fp}`, where `history_fp` is the fingerprint of the full observation history. |
| D2 Decision faults | `DECISION`-stage faults may transform the Decision (wrong tool, wrong args, decoy). |
| D3 Deliver | The runtime acts on the delivered Decision. |
| D4 Record | Observable event (delivered decision) + ledger entry (raw decision, fault applications). |

Decisions have **no state transition** (`state = null`).

## 5. Execution modes

### 5.1 RECORD
- Restore the scenario's initial state from its snapshot (a fresh object per run).
- Run the agent loop. Every decision and tool call goes through the gateway (S1–S7, D1–D4).
- Stop on a FINAL decision (`status=COMPLETED`) or on the step limit (`status=MAX_STEPS`).
- Evaluate the oracle on the final state. Write header, events, ledger and footer atomically.
- The header carries `config_fingerprint` (§8) and `fault_plan_hash` (null without faults).

### 5.2 REPLAY_STRICT (exact replay)
**Preconditions.** The recorded `config_fingerprint` must equal the fingerprint recomputed from current code and inputs; otherwise the result is `status=CONFIG_MISMATCH` before any execution. The cassette must load with valid integrity (TRACE_SCHEMA §7).

**Behaviour.**
1. Restore the initial state (fresh copy).
2. For each boundary event the runtime produces, take cassette entry *i* in order (§6) and check `boundary`, `name` and `request_fp`.
3. **Decision:** deliver the recorded delivered decision. The policy is **not** invoked, and no model call happens.
4. **Tool:** re-run S1–S7 on the replay state with the **recorded fault plan** (pre- and post-execution faults re-applied by the same triggers). Then verify, in this order:
   - (a) `executed` and the ledger raw-output fingerprint → else `DIVERGED(RAW_RESULT)`;
   - (b) `committed`, `before_hash`, `after_hash` → else `DIVERGED(STATE)`;
   - (c) the delivered `response_fp` → else `DIVERGED(RESPONSE)`.
5. At loop end: unconsumed entries → `DIVERGED(TRUNCATED)`. The final status and outcome must equal the recording's, else `DIVERGED(OUTCOME)`.

**Never:** call the policy, fall back to live execution after a mismatch, or touch anything outside the sandbox copy. The policy passed to the loop during strict replay is a guard object that raises if `decide` is called.

**Fault plan availability:** if the header has a `fault_plan_hash` but no matching plan is available, or the plan uses an operator this code does not register, strict replay refuses with `CONFIG_MISMATCH` (it cannot re-apply the faults faithfully).

**Known limit (decisions):** decisions are served from the cassette, not recomputed. A cassette whose *decision* payload was altered in a way that does not change any later tool request is therefore not detectable by replay itself. Such tampering is caught by the integrity chain at load time (TRACE_SCHEMA §7). Tool-side alterations (requests, raw results, state hashes, responses) are always detected by re-execution.

**Guarantee for deterministic sandbox tools:** the original final state hash and oracle outcome are reproduced, or a divergence is reported at the first differing event.

### 5.3 REPLAY_INTERVENE (counterfactual replay)
**Input:** recorded run *R* and an intervention spec: `target_seq`, `intervention_type`, `reference_source`, `is_placebo`, `expected_semantics`.

**Phases.**
1. **Prefix** (`seq < target_seq`): exactly §5.2. Any divergence → `status=INVALID_COUNTERFACTUAL`, `reason=prefix_diverged`.
2. **Intervention** (`seq = target_seq`): the live request must match *R*'s request at the target; the recorded entry is consumed. The replacement is applied per §10.1, and the intervention record is written to the header and marked `intervened=true` on the event. For tool targets the ledger keeps the truthful raw result and the fault applications of the execution that actually ran. The delivered replacement is the event's `response` (authoritative). `header.intervention.replacement_fp` is optional, because for `REFERENCE_TOOL` the value is only known when the target is reached.
   - OBSERVATION at a tool: the original lifecycle (with its faults) runs, so the state transition is the original one. Only the delivered value is replaced.
   - EXECUTION at a tool: the lifecycle runs with the fault layer disabled for this event (reference) or enabled (placebo).
3. **Fence:** immediately after the target, the cassette is closed. Any later lookup raises `CassetteFenceViolation`, which is a bug: the run fails and must never be silently caught. Downstream decisions are recomputed by the **live policy**, and downstream tools run live in the sandbox (S1–S7). The fault plan remains active for its other triggers.
4. **Oracle** on the new final state, with the same oracle id and version.

**Output:** a new run with `mode=REPLAY_INTERVENE` and `parent_run_id=R`.

**Invariant:** the new run's prefix events are identical to *R*'s prefix (request/response fingerprints and state hashes), and no recorded response is served at or after the target.

### 5.4 REGRESSION
- **Input:** a scenario, an environment fixture, a candidate agent configuration, and a repeat count. When derived from a recorded run, the fixture = the run's fault plan **restricted to `PRE_EXECUTION`/`POST_EXECUTION` faults**. `DECISION`-stage faults simulate agent errors and are dropped, because the candidate agent must be evaluated on its own decisions. Only the original's header and fault plan are read; its events and ledger are never used.
- **Behaviour:** fresh executions from the scenario's initial state with the fixture applied through the normal lifecycle. **No cassette parameter exists**; no recorded decisions or responses are consulted. The same oracle id and version are used.
- **Verdict:** `DETERMINISTIC_PASS` / `DETERMINISTIC_FAIL` only if the policy declares itself deterministic **and** ≥2 executions have equal semantic fingerprints. Otherwise `PROBABILISTIC(pass_rate, wilson_ci, n)` (Level 2).
- A REPLAY_STRICT of an old run under a changed agent returns `CONFIG_MISMATCH`. That result is never reported as "fixed".

## 6. Cassette matching
1. Entries are consumed **exactly once, in `seq` order** (positional), considering only `DECISION` and `TOOL` events (`AGENT_STEP` spans are re-created, not matched).
2. A match requires equality of `boundary`, `name` and `request_fp`. A `logical_key` match alone is never sufficient.
3. Lookups are allowed only in REPLAY_STRICT and in the REPLAY_INTERVENE prefix.
4. After a change in branching (different call count, order, arguments, repeated calls or length), positions no longer correspond. This is why everything after the fence runs live.
5. Comparing paths after a branch is **reporting only**: committed scope = first divergence point; stretch = LCS/Needleman-Wunsch alignment over `(boundary, name, normalized args)`.

## 7. Divergence kinds
| Kind | Detected when |
|---|---|
| `MISSING_EVENT` | the runtime requests an event but the cassette is exhausted |
| `TRUNCATED` | the run ended with unconsumed cassette entries |
| `BOUNDARY` / `NAME` | the kind or tool name differs at the same position |
| `REQUEST` | `request_fp` differs |
| `RAW_RESULT` | the `executed` flag or the ledger raw-output fingerprint differs |
| `STATE` | `committed`, `before_hash` or `after_hash` differs |
| `RESPONSE` | the delivered `response_fp` differs |
| `OUTCOME` | the final status, outcome or violated clauses differ |

The first divergence ends the replay with `status=DIVERGED` and a `divergence` record: `seq`, `kind`, `expected_fp`, `actual_fp`, `detail`.

## 8. Configuration fingerprint
`config_fingerprint = sha256(canonical({schema_version, scenario: {id, version, initial_state_hash}, agent: {policy_id, policy_version, source_hash}, tool_manifest_hash, fault_plan_hash, oracle: {id, version}, max_steps}))`
- `source_hash` covers the policy module source; `tool_manifest_hash` covers tool names, mutating flags, args JSON schemas and the tools module source (ADR-012).

## 9. Invariants
| ID | Invariant |
|---|---|
| I1 Exact replay | For each boundary event *i*: `boundary, name, request_fp, response_fp, executed, raw_output_fp, committed, before_hash, after_hash` are equal; same event count; same final state hash; same status, outcome and violated clauses. |
| I2 Counterfactual prefix | Same as I1 for every `seq < target_seq`; zero cassette accesses at or after the target. |
| I3 Regression isolation | Zero cassette accesses; the result is independent of stored recordings. |
| I4 State isolation | Each execution owns one state object restored from snapshot bytes; the scenario's initial state is never mutated; read-only tools never change state; commits are atomic. |
| I5 Ordering | The commit order equals the `seq` order; `seq` is contiguous from 0. |

## 10. Interventions

### 10.1 Types (not equivalent)
| Type | Allowed at | Semantics | Same-type placebo |
|---|---|---|---|
| `OBSERVATION_REPLACEMENT` | decision, tool | Re-apply the original execution exactly: same faults, same state transition. Only the **delivered** value is replaced. | Replace the delivered value with the original delivered value |
| `EXECUTION_REPLACEMENT` | tool only | Replace the original execution with a **trusted clean execution**: S1–S7 with the fault layer disabled for this event only. The clean transition commits, and the delivered value = the clean raw result. | Re-run the original execution, faults enabled, through the same intervention code path |

### 10.2 Trusted references
| Source | Mechanism | Allowed for |
|---|---|---|
| `REFERENCE_TOOL` | Re-execute the deterministic sandbox tool with the same args on a **scratch copy** of the same pre-state, with no faults | tool OBSERVATION / EXECUTION replacement |
| `REFERENCE_POLICY` | The reference policy registered for the **recorded agent**, queried with the recorded prefix history. For the scripted support agent this is the same scripted policy version: its fault-free decision function (injected decision faults are the only deviations). This is available only because the synthetic agent is scripted; LLM agents have no such reference (→ `UNSUPPORTED(no_trusted_reference)`). | decision OBSERVATION replacement |
| `ORIGINAL` | The recorded value/execution | placebos only |
| `INJECTION_CLEAN_VALUE` | The pre-injection raw value from the ledger | **benchmark validator only** (the API requires an explicit `allow_privileged=True`); never localizers. OBSERVATION_REPLACEMENT only. |

No reference is ever fabricated. Natural failures without a reference yield `UNSUPPORTED(no_trusted_reference)`.

### 10.3 Unsupported and invalid results
| Result | Condition |
|---|---|
| `UNSUPPORTED(no_state_transition_at_decision)` | `EXECUTION_REPLACEMENT` targeted at a decision event |
| `UNSUPPORTED(observation_inconsistent_with_state)` | `OBSERVATION_REPLACEMENT` of a **mutating** tool whose original state transition differs from the reference execution's transition (e.g. a pre-execution timeout prevented a refund that the reference reports as done) |
| `UNSUPPORTED(no_trusted_reference)` | no authorized source for this event |
| `UNSUPPORTED(target_not_boundary)` | the target seq is an `AGENT_STEP` span or out of range |
| `INVALID_COUNTERFACTUAL(prefix_diverged)` | the prefix failed I2 |
| `INVALID_COUNTERFACTUAL(machinery)` | a deterministic placebo did not reproduce the original outcome and final state |

UNSUPPORTED/INVALID results carry **no outcome**. They are reported, never converted to pass/fail.

### 10.4 Interpretation
- `INTERVENTIONAL_REPAIR` requires: the reference intervention → pass, **and** the same-type placebo → reproduces the original failure.
- It means *this single replacement is sufficient to repair this run*. It is **not** a unique causal explanation: other steps may also repair the run, and all are reported.
- With interacting faults, single-step interventions can produce several repair sites (jointly necessary faults) or none (individually sufficient faults → `NOT_ISOLATED`).

## 11. Fidelity metrics
Each metric is reported separately:
- response equality rate;
- event-sequence agreement (bool, and LCS ratio as stretch);
- raw-result agreement;
- state-transition agreement;
- final-state equality;
- outcome agreement;
- divergence rate, split into unmodified inputs (required 0) and deliberately perturbed inputs (required: 100% detected with the correct kind).

These are requirements verified by tests, not claims.

## 12. Replay report (Week 2 API: `agenttrace.replay.exact`)
A strict replay returns a `ReplayReport`:
- `verdict` ∈ `VERIFIED` (no divergence; all of I1 holds), `DIVERGED`, `CONFIG_MISMATCH` (refused before execution, with the list of mismatching components), `INTEGRITY_ERROR` (the recording failed TRACE_SCHEMA §7 validation, so nothing was replayed);
- the replay `RunRecord` (mode `REPLAY_STRICT`, `parent_run_id` = original), when executed;
- the first `divergence`, if any;
- the fidelity report (§11), computed positionally over boundary events;
- `policy_calls` (must be 0).

CLI: `atrace replay <run_id> [--policy vN] [--runs-dir DIR] [--save]`. Exit codes: 0 VERIFIED, 1 DIVERGED, 3 CONFIG_MISMATCH, 4 INTEGRITY_ERROR, 2 usage/not found.

## 14. Experiments, evidence and the localization service (Week 3)
- **Experiment** = one reference intervention plus its same-type placebo at one target. It records: original outcome, intervention outcome/status, placebo outcome/status, target seq and logical key, intervention type, reference source, `placebo_valid` (placebo reproduced the original status, outcome and final state hash), and `repair_observed` (original FAIL and intervention PASS).
- **Evidence labels** (per step; PLAN §11.3):
  - `SUSPICION`: heuristic score only;
  - `REFERENCE_DEVIATION`: the recorded value or transition differs from its trusted reference;
  - `INTERVENTIONAL_REPAIR`: `repair_observed` **and** `placebo_valid`;
  - `UNSUPPORTED`: no faithful intervention or reference is possible.
  
  Run conclusion: the list of repair sites, or `NOT_ISOLATED`. A repair means *this replacement is sufficient to repair this run*. It is never reported as a unique cause.
- **Intervention service:** localizers receive the observable `Trace` and an `InterventionService` bound to the privileged record. The service exposes only:
  - `reference_deviation(seq)` → deviates / consistent / unsupported(reason);
  - `experiment(seq)` → an experiment result (outcomes, statuses, booleans);
  - `replays_used`.
  
  It never returns ledger contents, raw outputs, fault plans or labels.
- **Replay cost:** every probe, intervention and placebo is one (partial) replay and is counted.

## 15. Test mapping
Acceptance tests #1–#21 are defined in PLAN_v0.2.1 §13 and TEST_PLAN.md §4:
- #1–#10, #15, #16, #21 → §5.2 (`tests/acceptance/test_replay_matrix.py`). Note for #5: with the check order of §5.2 step 4, a changed tool implementation surfaces first as `RAW_RESULT` (the raw result differs before the delivered response is compared).
- #11–#13, #17–#19 → §5.3 / §10 (`tests/acceptance/test_counterfactual_matrix.py`)
- #14, #20 → §5.4 (same file)
