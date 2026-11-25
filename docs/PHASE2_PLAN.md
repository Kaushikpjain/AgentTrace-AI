# Phase 2 Plan: Real GenAI Integration and Product Development

> **Status (2026-11-25): CP-2.0 APPROVED with conditions (§1.1); CP-2A.0 APPROVED (feasibility experiment only).** No other milestone is approved. 2A.1 and everything after it start only after their own checkpoints. ADR-028 records the direction, ADR-029 the measured model/runtime decision.
>
> **Baseline:** v0.1.0 local release commit `229fb5a`, 343 tests passing, total coverage 94%. Deterministic engine: trace schema, JSONL store, sandbox support environment, strict replay, counterfactual replay with placebos, regression, B1/B3/B4/CF localizers, AgentTrace-Synth v0 with its frozen held-out result (`docs/EVALUATION.md` §9).
>
> **Constraints:** MacBook Air M2 with 8 GB unified memory, alongside an IDE and a browser. Zero paid APIs. About 2–3 h of development per day. Local-first, offline at runtime, no Docker, no database server, no cloud.

Labels used in this plan: **[measured]** = produced by an executed command; **[estimate]** = derived from published specifications or experience, to be measured; **[assumption]** = to be confirmed before relying on it.

---

## 1. Goals, non-goals and invariants

**Goal.** Turn AgentTrace AI from a scripted research prototype into a practical, local-first debugging and reliability tool for tool-using LLM agents, while keeping the deterministic research engine intact.

**Mandatory outcomes**
1. A real local LLM agent runs behind the existing `Policy` protocol, and its decisions are recorded, strictly replayed without the model, regressed and investigated (2A).
2. A minimal LangGraph adapter routes a real LLM-driven graph through the same gateway, trace and replay machinery (2B).
3. A professional local web application for runs, timelines, investigations, comparisons and benchmark analytics (2C).
4. A new, independent evaluation (AgentTrace-Bench v1) with its own dev/test split and freeze, covering LLM agents, natural failures, imperfect and missing references and repeated trials (2D).

**Non-goals (Phase 2).** Hosted deployment, multi-user auth, paid or remote model APIs, models that do not fit in 8 GB, multi-agent systems, OpenTelemetry ingestion, ddmin minimization, LLM-as-judge oracles, and any use of the frozen synth_v0 held-out split for development.

### 1.1 Approval conditions (CP-2.0, binding for all of Phase 2)
1. The existing deterministic engine remains the foundation; Phase 2 extends it and does not replace it.
2. The LLM provider abstraction is independent of Ollama. Ollama is one provider implementation, and no Ollama-specific types cross the provider interface.
3. The final model and runtime are chosen from measurements (2A.0, ADR-029), never from these estimates.
4. Strict replay never invokes an LLM.
5. Regression and counterfactual execution explicitly account for nondeterminism (§4.1).
6. Unsupported interventions are always reported with a reason, never dropped.
7. Trusted-reference provenance stays explicit, and provenance is not treated as proof of correctness (§4.1).
8. No hidden model reasoning is collected or displayed. Thinking modes are disabled where possible; any emitted thinking content is discarded (only a flag and a length are kept).
9. Existing benchmark results (synth_v0, `bench-freeze-v0`) stay independent of Phase 2: they are not re-run, re-tuned or mixed with Phase 2 measurements.

**Invariants (must hold after every milestone)**
- All existing tests pass unchanged unless an ADR records why a test's contract changed.
- `make reproduce-dev` stays byte-identical. The synth_v0 artifacts, `bench-freeze-v0` and `TEST_RUNS.log` are never modified.
- Strict replay never calls a model or a live tool (fail-closed, NFR4).
- Localizers see only the observable trace and the `InterventionService` (C3, AST-enforced).
- No hidden model reasoning is displayed or presented as an explanation. Only recorded inputs, outputs and validation results are shown.
- Determinism is never assumed for LLM runs, whatever the seed or temperature. Repeated trials and intervals are used instead.

---

## 2. Architecture overview

```
                 ┌──────────────── existing, unchanged core ────────────────┐
 LangGraph graph │  AgentLoop ─▶ Policy.decide() ─▶ Decision ─▶ BoundaryGateway ─▶ sandbox tools
 (2B adapter) ──▶│     │              ▲                              │            (S1–S7 lifecycle)
                 │     ▼              │                              ▼
                 │  Trace (observable) + Ledger (privileged) ─▶ JSONL TraceStore ─▶ replay / CF / regression
                 └───────────────────│──────────────────────────────────────────┘
                                     │ new in 2A
                           LLMPolicy (implements Policy, deterministic=False)
                                     │
                           LLMProvider protocol ── OllamaProvider (HTTP, stdlib)
                                                └─ LlamaCppProvider (OpenAI-compatible HTTP, fallback)
                                                └─ FakeProvider (tests; scripted outputs, injected malformed outputs)
 Web (2C): FastAPI (read-mostly, localhost) ─▶ TraceStore / bench outputs ◀─ React + TypeScript UI
```

Key design choices (to be confirmed by ADR at each checkpoint):
- **Provider independence.** `LLMProvider.complete(request) -> LLMResponse` takes model id, messages, tool schemas, an optional JSON schema, sampling parameters and a timeout. It returns raw text, parsed tool call(s), token counts (when reported), latency and a runtime/model fingerprint. `LLMPolicy` owns prompting, parsing and validation; providers only transport. Talking to the local runtimes over HTTP with `urllib` keeps the runtime dependency count unchanged.
- **The decision boundary stays the unit of replay.** The trace already records every decision. Strict replay serves recorded decisions from the cassette, exactly as it does for scripted v1/v2. The model is never called during strict replay.
- **Additive schema.** LLM metadata goes into new optional ledger records and decision-event fields under a minor schema version. Old traces stay valid (TRACE_SCHEMA §versioning). The spec is updated before the code (repository rule).
- **Optional extras.** `agenttrace[llm]` (none expected, stdlib HTTP), `agenttrace[langgraph]` (`langgraph`), `agenttrace[web]` (`fastapi`, `uvicorn`). Core installs stay pydantic + typer + rich.

---

## 3. Local model and runtime selection (2A.0 confirms by measurement)

### 3.1 Runtimes
| Criterion | **Ollama** | **llama.cpp (`llama-server`)** | **MLX (`mlx-lm`)** |
|---|---|---|---|
| Apple Silicon | Metal backend, native arm64 | Metal backend, native arm64 | Apple-native (MLX), unified memory |
| Install | `brew install ollama` or the app; runs a local daemon | `brew install llama.cpp`; one binary per server | `pip install mlx-lm` (Python dependency, Apple-only) |
| Model format / quantization | GGUF (Q4_K_M, Q5_K_M, Q8_0, …) via registry tags | GGUF, all llama.cpp quant types; any local file | MLX format (4-bit/8-bit), converted or from the MLX community |
| Structured output | JSON schema via the `format` parameter; tool calling via chat API for supported templates | GBNF grammars / JSON schema in `llama-server` (strongest constraint); OpenAI-compatible tool calls | No built-in schema-constrained decoding in core (needs extra libraries) [assumption: re-check at 2A.0] |
| Integration effort | Lowest: stable local HTTP API, stdlib client | Low–medium: OpenAI-compatible HTTP, manual model files | Medium: in-process Python, platform-specific dependency |
| Determinism controls | `seed`, `temperature`; not guaranteed deterministic | `seed`, `temperature`, `n_threads`; not guaranteed | `seed`, temperature; not guaranteed |
| Licence | MIT | MIT | MIT |
| Offline / cost | fully offline after download; free | fully offline; free | fully offline; free |
| Memory overhead | daemon plus model; models unload after idle (configurable) | only the loaded model | in-process with Python |

**Recommendation.** **Ollama is the primary runtime**: lowest integration cost, a stable HTTP API, JSON-schema structured outputs, and an easy model lifecycle. **llama.cpp `llama-server` is the fallback**, used when grammar-constrained decoding or exact control of the model file is needed. Both sit behind the same `LLMProvider`. MLX is not planned (Python dependency, weaker structured output) but stays an option.

### 3.2 Models (≤ 4B parameters, 4-bit; candidates to verify at 2A.0)
| Model (instruct) | Params | Approx. Q4_K_M weights [estimate] | Tool calling | Licence [verify at download] | Notes |
|---|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | 4.0 B | 2.50 GB [verified registry size] | native tool-call template [verified] | Apache-2.0 [verified] | non-thinking instruct variant: its template has no thinking section |
| Qwen3-1.7B | 1.7 B | 1.36 GB [verified registry size] | native template | Apache-2.0 [verified] | hybrid thinking; disabled via the API `think: false` |
| Phi-4-mini-instruct | 3.8 B | ≈ 2.5 GB | function calling | MIT | alternative primary |
| Llama-3.2-3B-Instruct | 3.2 B | ≈ 2.0 GB | tool-call template | Llama 3.2 Community Licence (use restrictions) | licence less permissive |
| Gemma-3-4B-it | 4 B | ≈ 2.5–3 GB | prompt-based | Gemma Terms of Use | no native tool template |
| SmolLM3-3B | 3 B | ≈ 1.9 GB | tool-call support | Apache-2.0 | newer; less tested |

**Recommendation [to confirm by measurement]:**
- **Primary:** Qwen3-4B-Instruct-2507, Q4_K_M, via Ollama.
- **Lightweight fallback:** Qwen3-1.7B, Q4_K_M, with thinking disabled.
- **Licence-diversity alternative:** Phi-4-mini-instruct.

Selection gate at 2A.0 (dev scenarios only, ≥ 5 runs per template): valid tool-call JSON ≥ 95% of decisions after one repair retry, clean-run task success measured and reported, peak memory within budget, median decision latency ≤ 15 s.

### 3.3 Memory estimate [estimate; measured in 2A.0]
KV-cache size per token = 2 × layers × KV heads × head dim × 2 bytes (fp16), using the published model configurations.

| Model | Weights (Q4_K_M) | KV cache at 4k context | Runtime overhead | **Total resident** |
|---|---|---|---|---|
| Qwen3-4B (36 layers, 8 KV heads, dim 128) | ≈ 2.5 GB | ≈ 0.6 GB (≈ 1.2 GB at 8k) | ≈ 0.3–0.5 GB | **≈ 3.4–3.6 GB** (≈ 4.2 GB at 8k) |
| Qwen3-1.7B (28 layers, 8 KV heads, dim 128) | 1.36 GB | ≈ 0.5 GB | ≈ 0.3 GB | **≈ 2.2 GB** |

On 8 GB, with macOS, an IDE and a browser using roughly 4 GB, the 4B model fits at a **4k context**. 8k is marginal. Policy: `num_ctx = 4096` by default; history truncation is recorded in the trace; the model unloads when idle; peak RSS of the runtime process is recorded per run. If memory pressure (swap) appears in 2A.0, the default becomes Qwen3-1.7B.

**Speed [estimate]:** about 15–25 generated tokens/s and 100–300 prompt tokens/s for a 4B Q4 model on an M2. With 1.5–3k-token prompts, the first decision of a run may take 5–15 s; prefix caching should make later ones faster. A support episode (5–8 decisions) is then roughly 0.5–2 minutes. That makes compute budgeting central in 2B–2D (§7.4).

---

## 4. Phase 2A: Real local LLM integration (mandatory)

### 2A.0 Feasibility experiment (approved; protocol and criteria pre-registered before any run)
**Pre-checks (2026-11-25, before any download).**
- Ollama 0.40.16 was already installed (Ollama.app, Apple Silicon); its server listens on `127.0.0.1:11434` only.
- Free disk: 29 GiB.
- Memory: 8 GiB RAM, with **4.67 GB of 6 GB swap already in use** and 34% free memory before any model was loaded.
- Official registry manifests:

| Tag | Model layer | Total download | Licence | Template |
|---|---|---|---|---|
| `qwen3:1.7b-q4_K_M` | `sha256:3d0b7905…`, 1,359,279,776 B | 1,359,292,957 B | Apache-2.0 | `<tool_call>`, honours `think` |
| `qwen3:4b-instruct-2507-q4_K_M` | `sha256:85e4a5b7…`, 2,497,280,480 B | 2,497,293,316 B | Apache-2.0 | `<tool_call>`, no thinking section |

An unrelated model already on disk (`qwen2.5-coder:7b`) is not used or modified.

**Implementation boundary.** The experiment lives in `experiments/llm_feasibility/` (outside `src/`, excluded from distributions). It runs an experimental policy that implements the existing `Policy` protocol through the unchanged `run_episode`, gateway, sandbox tools and oracle. No production module, schema, replay or counterfactual code is changed. Raw per-call logs stay in the git-ignored `experiments/*/raw/`; only small summaries are committed. Results are never mixed with synth_v0.

**Stages.**
- **A (feasibility, per model).** Local inference; structured tool call; JSON parsing; argument validation (rejection of an invalid call); multi-turn sequential calls; context accounting (prompt tokens vs. `num_ctx`, and a guard that aborts a run before 90% of `num_ctx` instead of letting Ollama truncate silently); timeout path; thinking content absent or discarded; traffic only to 127.0.0.1 (socket guard).
- **B (pilot, per model).** One run per dev template at temperature 0 plus a cold-load measurement.
- **C (comparison).** 4 templates (T1–T4) × 2 models × temperatures {0, 0.7} × 5 repetitions = 80 runs. One model is loaded at a time, the smaller model first, and each model is unloaded (`keep_alive: 0`) afterwards.

**Fixed configuration (identical for both models unless noted).**
- System prompt and tool schemas: same text for both, with schemas generated from the tools' pydantic models; the system prompt states the support procedure in prose.
- Run limits: `max_steps` from the scenario (12); one bounded repair retry per decision.
- Sampling: `num_ctx` 4096, `num_predict` 512, `top_p` 0.8, `top_k` 20, `repeat_penalty` 1.0, `seed` = 1000 + repetition (recorded; determinism is not assumed).
- Timeouts: per-call 120 s, per-run 600 s.
- Run order: model → repetition → temperature → template.
- **Unavoidable difference:** `think: false` is sent to Qwen3-1.7B only; the 4B instruct model has no thinking mode.

**Definitions.**
- *Decision turn*: one model request for the next action.
- *Syntactically valid*: exactly one tool call with a known name, plus arguments that pass the tool's pydantic schema. A text-only answer counts as valid only after `close_ticket` has succeeded; otherwise it is invalid.
- *Argument-caused error*: an executed call that returns `VALIDATION_ERROR`, `NOT_FOUND`, `INVALID_AMOUNT` or `AMOUNT_EXCEEDS_ORDER_TOTAL`.
- *Reference agreement* (semantic, strict): given the run's actual history, the tool matches the decision of the scripted gold reference (v2); when it does, the arguments are compared (amounts numerically; `idempotency_key` and `note` ignored). Legitimate alternative orders count as disagreement, so this is reported, not gated.
- *Task success*: the oracle verdict is PASS.
- Runs that are aborted (invalid after retry, timeout, context guard, run cap) count as failures. They are never excluded.

**Selection criteria (pre-specified; not to be relaxed after seeing results).** A model qualifies only if **all** of these hold:

| # | Criterion | Population |
|---|---|---|
| S1 | Syntactic validity after ≤ 1 repair retry ≥ 95% of decision turns | all Stage C runs (both temperatures) |
| S2 | ≥ 95% of executed tool calls free of argument-caused errors | all Stage C runs |
| S3 | Clean-run task success ≥ 15/20 (75%) **and** ≥ 3/5 for every template | Stage C, temperature 0 |
| S4 | Warm decision latency median ≤ 15 s and p90 ≤ 30 s | all warm decision calls |
| S5 | No sustained critical memory pressure (pressure level 4 in > 10% of 1 s samples) and swap growth ≤ 1.0 GB during the model's runs | Stage B + C |
| S6 | Licence verified Apache-2.0/MIT-compatible; inference traffic only to 127.0.0.1 | — |

- **Rationale for S3:** the scripted agent solves every clean dev task. Phase 2 needs clean baselines that mostly succeed, so that recorded failures and repairs are informative. Below 75%, failures would be dominated by baseline incompetence. With n = 20 the Wilson lower bound at 15/20 is ≈ 0.53, so S3 is a feasibility threshold, not a precise estimate.
- **Reported, not gating:** first-attempt validity, reference agreement (tool and arguments), temperature-0.7 success, outcome consistency across repetitions, retry and timeout rates, tokens, cold load time, time to first token (derived from Ollama's `load_duration` + `prompt_eval_duration`), end-to-end run time, peak runtime memory.
- **Choice:**
  - Primary: the qualifying model with the highest temperature-0 task success. Within 1 run of each other, lower median latency wins, then lower peak memory.
  - Fallback: the other qualifying model.
  - If none qualify, the result is reported as such and alternatives are proposed as a **new** experiment.

**Stop rules.**
- A candidate failing Stage A is stopped.
- In Stage B, a candidate is stopped if ≥ 3/4 pilot runs abort, if swap grows > 1.5 GB, or if critical pressure is sustained.
- Total wall budget is 3 h. If it is exceeded, the completed runs are reported and a reduced protocol is proposed.

| Item | Plan |
|---|---|
| Effort | 4 h · 2 sessions (plus unattended run time) |
| Deliverables | `experiments/llm_feasibility/` (script, config, summary), ADR-029, TASKS log entries, go/no-go for 2A.1 |
| Stretch | Phi-4-mini; llama.cpp grammar-constrained mode (only if Ollama proves unsuitable) |

### 2A.1 Provider interface and `LLMPolicy`
| Item | Plan |
|---|---|
| Objective | A provider-independent LLM policy that plugs into `AgentLoop` with validated, structured decisions. |
| Scope | `LLMProvider` protocol + `OllamaProvider` + `FakeProvider`; `LLMPolicy` (system prompt, task rendering, history rendering, tool schemas generated from `ToolSpec`); parsing to `Decision`; argument validation against the tool's pydantic model; malformed-output handling (one bounded repair retry with the validation error, then a recorded `INVALID_DECISION` final); model timeouts (recorded as an agent-step error, never silently retried); context management (deterministic truncation of the oldest observations; the truncation is recorded). |
| Approach | `deterministic = False`; `source_hash` covers prompt templates and parser code; `policy_version` encodes model id + quantization + prompt version; the config fingerprint includes model digest and sampling parameters. |
| Dependencies | none (stdlib `urllib`, `json`). |
| Files | new `src/agenttrace/llm/{provider.py,ollama.py,fake.py,policy.py,prompts.py,parse.py}`; `runtime/types.py` (decision provenance field, additive); `runner.py` (policy registry); `cli.py` (`--policy llm:<model>`). |
| Effort | 6 h · 3 sessions |
| Hardware | tests use `FakeProvider` (no model); a manual check uses the model. |
| Acceptance | CLI `atrace run T1 --policy llm:qwen3-4b` completes with recorded decisions; all malformed-output classes (non-JSON, unknown tool, invalid args, multiple calls, empty) handled and tested; timeout path tested; no network beyond `localhost` (socket test). |
| Testing | unit tests with `FakeProvider` (golden prompts, parser cases, Hypothesis fuzzing of malformed outputs); one opt-in integration test marked `llm` (skipped by default and in CI). |
| Risks | Prompt sensitivity → versioned prompts; template differences between models → provider-level adapters. |
| Depends on | 2A.0 go. |
| Deliverables | `LLMPolicy`, tests, REPLAY_SPEC/TRACE_SCHEMA updates (spec first), ADR. |
| Stretch | `LlamaCppProvider` with a JSON-schema grammar. |

### 2A.2 Recording, privacy and strict replay of LLM runs
| Item | Plan |
|---|---|
| Objective | Record real LLM decisions with full provenance and replay them strictly without the model. |
| Scope | Ledger record per model call: provider, runtime version, model id + digest + quantization, sampling parameters (temperature, top_p, seed, num_ctx, max tokens), prompt-template version, prompt hash, tool-schema hash, raw output, parsed decision, validation errors and retries, token counts (when reported), latency, timeout flag. Observable trace: the parsed decision plus validation status. Sensitive-data handling: prompts and raw outputs are stored in the privileged ledger by default; `--redact-prompts` stores only hashes and lengths; a configurable redaction hook for PII patterns; prompts never leave the machine. Thinking-mode content, if a model emits it, is stripped from the parsed decision, never displayed, and stored only as a hash by default. Strict replay: the cassette serves recorded decisions; any request for a model call during replay is a fail-closed divergence. |
| Dependencies | none |
| Files | `trace/schema.py` (minor version, additive), `docs/TRACE_SCHEMA.md`, `docs/REPLAY_SPEC.md`, `replay/exact.py` (decision-cassette path reused), `llm/policy.py`. |
| Effort | 5 h · 2–3 sessions |
| Acceptance | 20 recorded LLM runs (dev templates) all strictly replay VERIFIED with 0 provider calls (counted by an instrumented provider); old traces still load; redaction mode tested; schema migration tests. |
| Testing | replay acceptance tests with `FakeProvider` recordings; property test: replaying never constructs a provider. |
| Risks | Prompts can contain sensitive data → ledger-only by default, redaction option, documented threat model. |
| Depends on | 2A.1 |
| Deliverables | schema v1.x, specs, tests. |
| Stretch | Per-run memory sampling of the runtime process. |

### 2A.3 Nondeterminism-aware regression and counterfactuals; references
| Item | Plan |
|---|---|
| Objective | Fresh LLM execution for regression and counterfactuals, with honest handling of nondeterminism and reference availability. |
| Scope | **Regression:** k fresh runs (default k = 5) of a candidate (model, prompt or policy version); pass rate with Wilson CI; verdicts `DETERMINISTIC_*` only when all k runs agree and the policy is deterministic, otherwise `STOCHASTIC` with rate and interval; comparison against the baseline rate (Newcombe interval). **Counterfactuals:** downstream decisions after the fence are fresh model calls; three arms (intervention, same-type placebo, no-intervention control) each run k times under the rules of §4.1; `INCONCLUSIVE` is a new, additive label. **References:** each reference carries provenance (`ENVIRONMENT_TOOL` trusted, `SCRIPTED_REFERENCE_POLICY`, `GOLD_TRAJECTORY`, `HUMAN_ANNOTATION`, `NONE`); LLM decisions without a reference → `UNSUPPORTED (no_trusted_reference)`, always reported, never dropped. |
| Files | `replay/regression.py`, `replay/counterfactual.py`, `replay/service.py`, `localize/types.py` (`INCONCLUSIVE`), `localize/counterfactual.py`, `bench/stats.py` (Newcombe), docs. |
| Effort | 6 h · 3 sessions |
| Acceptance | Deterministic scripted policies give byte-identical results to v0.1.0 (regression guard); stochastic paths tested with a seeded `FakeProvider` that flips outcomes with known probabilities; `UNSUPPORTED` reasons always present. |
| Testing | statistical unit tests against hand-computed intervals; simulation tests of the evidence rule's false-repair rate under a null (no real effect). |
| Risks | Compute cost (k × arms × steps) → replay budget caps; the evidence rule is too strict or too lenient → fixed before any held-out use, checked by simulation. |
| Depends on | 2A.2 |
| Deliverables | stochastic regression/CF, provenance, ADRs, specs. |
| Stretch | Adaptive k (sequential stopping) — explicitly out of scope unless approved. |

### 4.1 Stochastic counterfactual methodology (requirements for 2A.3 and 2D; not implemented in 2A.0)
1. **Natural recovery.** A nondeterministic agent can recover without any intervention, so every counterfactual has three arms from the same fence:
   - **intervention**: replace the step;
   - **placebo**: same-type replacement with the original value;
   - **no-intervention control**: fresh re-execution from the fence with nothing replaced.
   
   The control's pass rate is the natural-recovery rate.
2. **Comparable arms.** The arms share model, digest, sampling parameters, seed schedule, prompt version, `max_steps`, timeouts and number of trials. Any difference (e.g. a trial that timed out) is reported per arm.
3. **Transparent trials.** Every trial is a recorded run with arm, trial index and seed. Failed, timed-out or invalid trials count as failures and are never dropped.
4. **Seeds.** A fixed seed does not guarantee identical outputs (batching, kernels, runtime versions). Determinism is measured as an outcome-agreement rate, never assumed.
5. **Trial counts.** k = 5 per arm is a pilot setting. At k = 5 only extreme splits (e.g. 5/5 vs. 0/5) can exclude zero in a 95% interval. 2D sets k from a power analysis (e.g. ≈ 20 per arm to detect a 0.5 difference).
6. **Evidence rule.**
   - **Definitions:**
     - *I*, *P*, *C* are the pass rates of the three arms;
     - *Δ* = *I* − max(*P*, *C*);
     - all intervals are Newcombe 95%.
   - `INTERVENTIONAL_REPAIR` requires the lower bound of *Δ* > 0, ≥ 80% completed trials in every arm, and a valid placebo.
   - **Invalid placebo:** the placebo is invalid if the lower bound of *P* − *C* > 0, i.e. replaying the original value itself changes outcomes. The step is then `INVALID_COUNTERFACTUAL`.
   - `INCONCLUSIVE` applies when any of these holds:
     - the interval of *Δ* includes 0;
     - more than 20% of an arm's trials did not complete;
     - *C* ≥ 0.5 (natural recovery too frequent to attribute anything).
   - `NO_REPAIR_EVIDENCE` applies when the upper bound of *Δ* ≤ 0.1.
   - The rule's false-repair rate is checked by simulation under the null before use.
7. **Multiple candidate repair sites.** Every step meeting the rule is reported with its effect estimate and interval. Holm correction is applied across the steps tested in one run. The run conclusion is `MULTIPLE_REPAIR_SITES` when there is more than one site. No site is singled out as "the" cause.
8. **Interpretation.** Interventional repair means "replacing this step was sufficient to raise the pass rate in this run's context". It is not proof of unique causality.
9. **References.** Provenance says where a reference came from, not that it is correct. References are validated before use (agreement with the oracle on clean runs, spot checks). An unvalidated reference yields `UNSUPPORTED (reference_unvalidated)` or evidence explicitly marked as conditional on that reference. 2D measures the effect of imperfect references.

### 2A.4 End-to-end local LLM demonstration
| Item | Plan |
|---|---|
| Objective | A reproducible demo: a real local LLM agent fails, is replayed, investigated and regressed. |
| Scope | `scripts/demo_llm.sh`: run T-dev scenarios with the LLM policy until a natural failure appears (or use a controlled `FaultPlan` if none appears in N runs; labelled as such); strict replay (0 model calls); B1/B3/B4/CF investigation with provenance and `UNSUPPORTED` counts; regression of a prompt fix over k runs. Pre-recorded traces are committed so the demo also runs without a model (replay-only path). |
| Effort | 2 h · 1 session |
| Acceptance | `DEMO_NONINTERACTIVE=1` replay-only demo exits 0 in CI-like conditions; live demo documented with measured timings. |
| Depends on | 2A.3 · Approval **CP-2A** (end of 2A review) |
| Deliverables | demo script, recorded traces, README section. |

**2A total: 23 h (≈ 9–10 sessions).**

---

## 5. Phase 2B: LangGraph integration (mandatory core, minimal adapter)

### 2B.1 Adapter and tracing
| Item | Plan |
|---|---|
| Objective | Run a real LLM-driven LangGraph agent with every tool call and model decision going through AgentTrace's boundary. |
| Scope | `agenttrace.adapters.langgraph`: (a) a tool wrapper that turns AgentTrace `ToolSpec`s into graph tools whose execution goes through `BoundaryGateway` (lifecycle S1–S7, faults, audit); (b) an LLM node that calls `LLMPolicy`/`LLMProvider` directly (no LangChain chat-model dependency), so decisions are recorded exactly as in 2A; (c) node-level tracing from the graph's streamed updates (node start/end, conditional-edge choice, super-step index) as new observable `GRAPH_NODE` events (additive); (d) state capture: a JSON-serialisable snapshot of the graph state per super-step (non-serialisable state → recorded as `UNSUPPORTED_STATE` with type name); (e) exceptions in nodes recorded as agent failures with type and message. Checkpoints: an in-memory checkpointer only; checkpoint ids are linked to trace events (no SQLite or Postgres). |
| Dependencies | `langgraph` (optional extra `[langgraph]`; exact version pinned in `uv.lock` after the approval). |
| Files | new `src/agenttrace/adapters/langgraph/{tools.py,llm_node.py,tracer.py,state.py}`; `trace/schema.py` (event kind, additive); docs. |
| Effort | 7 h · 3 sessions |
| Acceptance | A ReAct-style support graph (agent ↔ tools, conditional routing to END) completes on dev scenarios with recorded node, decision and tool events; tool calls bypassing the gateway are detected and fail the run (test). |
| Testing | unit tests with `FakeProvider`; graph-structure tests (routing, loop limit, exception path); import guard so core never imports `langgraph`. |
| Risks | LangGraph API changes → pin the version, test against it, keep the adapter thin; dependency weight → optional extra only. |
| Depends on | 2A.2 · Approval **CP-2B.0** (add the `langgraph` dependency) |

### 2B.2 Replay, faults, counterfactuals and regression through the adapter
| Item | Plan |
|---|---|
| Objective | The same guarantees for supported graphs. |
| Scope | Strict replay re-executes the graph with decisions from the cassette and tools re-executed against the restored sandbox state; divergence detection includes node order and routing choices. `FaultPlan` operators apply at the gateway (unchanged). Counterfactuals use the 2A.3 stochastic protocol. Regression runs a candidate graph or model freshly. **Supported subset (documented and tested):** single graph, sequential super-steps, tools only via the wrapper, JSON-serialisable state, no interrupts or human-in-the-loop, no `Send` fan-out, no subgraphs. Anything outside → explicit `UNSUPPORTED` with a reason, never silent. |
| Effort | 6 h · 3 sessions |
| Acceptance | 20 recorded graph runs strictly replay VERIFIED; injected faults reproduce; one counterfactual and one regression complete with provenance; unsupported graph features produce `UNSUPPORTED`. |
| Testing | acceptance matrix on the supported subset; negative tests per unsupported feature. |
| Risks | Hidden side effects in user nodes cannot be captured → documented limitation; the adapter only guarantees what goes through the gateway. |
| Depends on | 2B.1 |

### 2B.3 Real-agent demonstration
| Item | Plan |
|---|---|
| Objective | The nine-step story with an actual LLM-driven LangGraph agent. |
| Scope | (1) task received → (2) tool selection and execution → (3) a natural failure, or a controlled fault if none occurs (labelled) → (4) recording → (5) strict replay → (6) suspicious-step ranking → (7) a supported counterfactual with placebo arms → (8) evidence labels with provenance → (9) a regression of a fix. Recorded traces are committed for a model-free replay path. |
| Effort | 3 h · 1–2 sessions |
| Acceptance | Replay-only demo exits 0; live demo timings measured; claims limited to the supported subset. |
| Depends on | 2B.2 · Approval **CP-2B** |

**2B total: 16 h (≈ 6–7 sessions).**

---

## 6. Phase 2C: Professional web platform (mandatory core; polish items optional)

### 6.1 Stack and principles
- **Backend:** FastAPI + uvicorn (optional extra `[web]`), bound to `127.0.0.1` only. A read-mostly API over the existing JSONL `TraceStore` and bench outputs, with an in-memory index built at startup. SQLite (stdlib) only if measured listing latency over ~5,000 runs requires it. Long operations (replay, investigation, regression) run as background jobs in-process (thread pool) with job status endpoints. No Redis or Celery. Run ids are validated against the id pattern (no path traversal). CORS is restricted to the dev server origin.
- **Frontend:** React + TypeScript + Vite. Deliberately small library set, each justified in ADR at CP-2C.0:
  - **Radix UI primitives**: accessible dialogs, tabs, tooltips, menus; unstyled.
  - **TanStack Query**: server state, caching, loading/error states.
  - **TanStack Virtual**: long traces.
  - **one chart library** (Recharts by default; uPlot if bundle size matters).
  - Styling with CSS variables (design tokens) and CSS modules; no CSS framework.
  - Tests: Vitest + Testing Library; Playwright for a few end-to-end flows.
- **Design system:**
  - Tokens for colour, spacing (4 px grid), radii and elevation.
  - Typography: a system UI or Inter text face plus a monospace face for ids, JSON and seq numbers.
  - A neutral palette with one accent and semantic colours for PASS/FAIL and evidence labels. Labels always carry text or an icon as well as colour.
  - Light and dark themes via `prefers-color-scheme` with a manual toggle; WCAG AA contrast; full keyboard navigation and visible focus.
  - Skeleton loading states, error boundaries with retry, and empty states that show the CLI command that would populate the view.
  - Minimal motion (`prefers-reduced-motion` respected).
- **API contract:** pydantic response models generate an OpenAPI schema; TypeScript types are generated from it (`openapi-typescript`, dev-only dependency), so the UI and engine cannot drift silently.

### 6.2 Modules
| Module | Content |
|---|---|
| Dashboard | total runs; PASS/FAIL; recent activity; replay verification rate; investigations by conclusion; regression verdicts; replay and model-call cost (count, latency, tokens where recorded) |
| Run history | search (id, scenario, agent, model); filters (outcome, mode, policy, model, date); sorting; duration; agent and model identity; select two runs → comparison |
| Execution timeline | virtualised event list and lane view: decisions, tool requests/responses, state transitions (JSON delta), fault events, errors, graph nodes (2B), timing; expandable details with raw JSON; jump to seq; integrity status |
| Decision inspector | recorded model input summary (prompt-template version, hash, optionally the redacted prompt), tool schemas, structured arguments, validation errors and repair retries, model configuration, recorded output. **No hidden reasoning or invented explanation is shown.** |
| Failure investigation | suspicious-step ranking per method (B1/B3/B4/CF); evidence labels with definitions; reference deviations with provenance; supported vs. `UNSUPPORTED` (with reasons); experiments with intervention/placebo arms (rates and intervals for stochastic runs); multiple repair sites listed, with the caveat that repair ≠ unique cause |
| Counterfactual comparison | original vs. modified run side by side, aligned by seq/logical key; event, state, tool-response and outcome diffs; repair evidence; replay cost |
| Regression comparison | baseline vs. fresh runs; policy or model version diff; outcome change; behavioural diff (tool-call sequence); verdict with interval |
| Benchmark analytics | dev and held-out results from bench outputs (read-only); baseline comparisons; Top-1/Top-3/MRR with intervals; per-operator and symptom-distance tables; cost analysis; the limitations text shown alongside the numbers |
| Report export | JSON (investigation and run summaries), CSV (run lists, metrics tables), Markdown/HTML investigation report (reusing `localize/report.py`), and the evaluation bundle (`metrics.json`, `table.md`) |

### 6.3 Milestones
| ID | Objective and scope | Effort | Acceptance | Depends on / approval |
|---|---|---|---|---|
| 2C.0 | API contract, information architecture, wireframes and design tokens; library choices as ADR | 4 h · 2 sessions | reviewed wireframes for all modules; OpenAPI draft | 2A.2 · **CP-2C.0** (design and dependency approval; Node.js LTS install) |
| 2C.1 | FastAPI backend: runs, events, investigations, comparisons, bench results, exports, background jobs | 7 h · 3 sessions | API tests (httpx test client) for every endpoint, incl. path-traversal and invalid-id tests; localhost-only bind test | 2C.0 |
| 2C.2 | Frontend shell: routing, theme, design system components, data layer, error/empty/loading states | 6 h · 3 sessions | component tests; axe accessibility checks on the shell; both themes | 2C.1 |
| 2C.3 | Dashboard, run history, timeline (virtualised), decision inspector | 9 h · 4 sessions | a 2,000-event trace scrolls smoothly (measured); e2e: open run → inspect decision | 2C.2 |
| 2C.4 | Investigation, counterfactual and regression comparison views | 8 h · 3–4 sessions | e2e: investigate → open experiment → compare arms; caveats rendered | 2C.3, 2A.3 |
| 2C.5 | Benchmark analytics and report export | 5 h · 2 sessions | numbers equal `metrics.json` (test); exports validated against schemas | 2C.3 |

**2C total: 39 h (≈ 16 sessions).** Hardware: Node dev server + API ≈ 0.5–1 GB [estimate]; the UI does not need the model loaded. **Stretch:** run-to-run diff of arbitrary runs, keyboard command palette, saved filters, print stylesheet.

**Risks:** scope creep (the biggest one) → modules ship in order, with polish as stretch; large traces → virtualisation and server-side paging from 2C.1; UI showing more than the evidence supports → every evidence view renders its caveat text from one shared source.

---

## 7. Phase 2D: Expanded research evaluation (AgentTrace-Bench v1)

A new, independent benchmark. **The synth_v0 held-out split is not used for any development, tuning or design decision.** synth_v0 and its frozen results stay as they are.

### 7.1 Questions
1. How well do B1/B3/B4/CF rank the responsible step for **LLM-driven** agents, under controlled injection and for natural failures?
2. How do **missing and imperfect references** change CF's coverage (`UNSUPPORTED` rate) and its false-repair rate?
3. What does **nondeterminism** cost? (outcome-flip rate across repeats; the k needed for stable evidence; placebo-validity rate)
4. What is the trade-off between **localization accuracy and execution cost** (replays, model calls, wall time)?
5. How **model-dependent** are the results (primary vs. fallback model)?

### 7.2 Design
- **Domains:** support (existing environment) plus **two new sandboxed domains** with deterministic oracles, chosen for low build cost, e.g. a scheduling/calendar domain and an inventory/order-fulfilment domain. Each has ≥ 6 templates.
- **Splits:** dev/test by **template within each domain**. One whole domain is optionally held out for an out-of-domain check. The split is fixed before any LLM run on the new templates.
- **Instance types:**
  - (a) controlled injection on LLM runs (FaultPlan operators at the gateway; decision faults via `REPLACE_DECISION`);
  - (b) natural failures collected from repeated LLM runs, with ground truth from a written annotation protocol. The owner is the single annotator; this is mitigated by a blind re-annotation of a 20% subset after ≥ 1 week and reported as intra-annotator agreement, and labels can be `UNKNOWN`;
  - (c) multi-fault instances (two injected faults, jointly and individually sufficient);
  - (d) clean, masked and decoy controls.
- **References:**
  - complete trusted references (scripted reference policy plus environment tools);
  - **imperfect references** (a reference policy with a known, injected error rate);
  - **missing references** (none for LLM decisions).
  - Reference quality is measured on clean runs (agreement with the oracle) and recorded with provenance.
- **Repeated trials:** every instance is recorded r times (e.g., r = 3) to estimate outcome variability; counterfactual arms (intervention, placebo, no-intervention control) use k repeats under §4.1, with k from the power analysis.
- **Metrics, kept strictly separate:**
  1. **Injection-site localization** (Top-1/Top-3/MRR on controlled single-site instances);
  2. **Suspicious-step ranking** quality on natural failures where an annotated responsible step exists;
  3. **Reference deviation** rate and precision;
  4. **Interventional repair evidence** (repair rate, placebo validity, `INCONCLUSIVE` and `UNSUPPORTED` rates, multiple repair sites);
  5. **False repairs** (on passing runs and on placebo arms).
  
  **Unique causal attribution is not measured and is not claimed.**
- **Statistics:** Wilson intervals for rates; Newcombe for differences; cluster bootstrap over templates/tasks; exact McNemar + Holm for paired comparisons; a pre-specified primary metric and primary comparison; a power estimate before data collection (the number of eligible instances needed for a meaningful CF vs. B4 comparison).
- **Cost and resources:** replays, model calls, tokens, wall time and peak memory per investigation; accuracy-vs-budget curves at fixed replay caps.
- **Protocol:**
  - a pre-registration document (`docs/BENCH_V1_PROTOCOL.md`) is approved before any test-split run;
  - freeze `bench-freeze-v1` with the hardened guard (ADR-026), extended to the new benchmark;
  - a single official test run; results reported as-is.

### 7.3 Milestones
| ID | Objective and scope | Effort | Acceptance | Depends on / approval |
|---|---|---|---|---|
| 2D.0 | Literature and prior-work review; protocol and pre-registration; power and compute budget | 5 h · 2 sessions | approved protocol | 2A.3 · **CP-2D.0** |
| 2D.1 | Two new domains (environments, tools, oracles, ≥ 6 templates each) | 10 h · 4 sessions | env/oracle tests as in Week 1; determinism checks | 2D.0 |
| 2D.2 | Benchmark v1 generator, label validation, natural-failure collection and annotation, imperfect references | 8 h · 3–4 sessions | `bench verify` equivalent for v1; annotation protocol followed; split frozen before evaluation | 2D.1 |
| 2D.3 | Dev evaluation, freeze, single held-out run, report | 7 h · 3 sessions (plus compute time) | correctness checks OK; report with intervals and limitations | 2D.2 · **CP-2D.F** (freeze) · **CP-2D.T** (test run) |

**2D total: 30 h (≈ 12 sessions) plus unattended compute.** Compute [estimate]: about 1 min per LLM episode, so 300 instances × r = 3 ≈ 15 h of recording. CF with k = 3 per arm and a cap of 8 probed steps is up to ~50 episodes per investigation. A full CF sweep is therefore days of unattended compute. Mitigations: replay caps, CF on a stratified subset, overnight batch runs, and the fallback 1.7B model for scale-out ablations only.

### 7.4 Possible research contributions (no novelty or patentability claimed)
These are candidate directions, to be assessed in 2D.0 against prior work: replay-based debugging and record/replay systems, delta debugging, agent failure attribution benchmarks, counterfactual and causal attribution for agents, and agent safety/security benchmarks.
- **Evidence-typed failure diagnosis.** One report that keeps suspicion, reference deviation, interventional repair, `INCONCLUSIVE` and `UNSUPPORTED` separate, with reference provenance.
- **Placebo-controlled counterfactuals under nondeterminism.** An explicit statistical decision rule and a measured false-repair rate.
- **An evaluation protocol** separating injection-site localization from repair evidence, with cost curves.

Any external claim, publication or patent filing needs the literature review and the owner's IPR review first. Notes on this stay in `private/`.

---

## 8. Timeline and budget

| Phase | Mandatory effort | Sessions (2.5 h) | Calendar at ~15 h/week |
|---|---|---|---|
| 2A | 23 h | 9–10 | ~1.5 weeks |
| 2B | 16 h | 6–7 | ~1 week |
| 2C | 39 h | 16 | ~2.5–3 weeks |
| 2D | 30 h (+ compute) | 12 | ~2 weeks (+ overnight compute) |
| **Subtotal** | **108 h** | **~43** | **~7–7.5 weeks** |
| Contingency (20%) | 22 h | ~9 | ~1.5 weeks |
| **Total mandatory** | **≈ 130 h** | **~52** | **≈ 9 weeks** |
| Optional/stretch pool | ≈ 20 h | ~8 | as time allows |

Recommended order: 2A → 2B → 2C.0–2C.3 → 2D.0–2D.1 → 2C.4–2C.5 → 2D.2–2D.3. 2C can be paused at any milestone boundary without blocking 2D.

**Optional improvements (not in the mandatory total):** `LlamaCppProvider`; adaptive k; MLX provider; SQLite index; command palette and saved views; screen-recorded demo; JSON-schema export of the trace format; out-of-domain held-out domain.

---

## 9. Approval checkpoints
| Checkpoint | What is approved |
|---|---|
| **CP-2.0** | This plan (scope, hours, order); ADR-028 |
| **CP-2A.0** | Installing Ollama and downloading the two candidate models (≈ 3.6 GB) |
| CP-2A | End of 2A: model/runtime ADR, schema extension, demo |
| **CP-2B.0** | Adding `langgraph` as an optional dependency |
| CP-2B | End of 2B: supported-subset statement, demo |
| **CP-2C.0** | Wireframes, design tokens and frontend dependencies; installing Node.js LTS |
| CP-2C | End of 2C |
| **CP-2D.0** | Benchmark v1 protocol and pre-registration |
| **CP-2D.F / CP-2D.T** | Freeze of benchmark v1, then its single held-out run |

Pushes, tags, releases, licence and repository visibility stay separate owner decisions at every point.

---

## 10. Workflow
- After each verified milestone, update `docs/TASKS.md`, add ADRs to `docs/DECISIONS.md`, update specs (`REPLAY_SPEC.md`, `TRACE_SCHEMA.md`) **before** behaviour changes, and update `README.md` for user-facing changes.
- Each milestone ends with a recorded run of `make check`, coverage, `make reproduce-dev` and the relevant demo. Results go in the TASKS verification log.
- One logical change per local commit; no push without approval.
- No phase proceeds into the next without its checkpoint.
