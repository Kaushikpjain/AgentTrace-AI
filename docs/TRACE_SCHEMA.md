# Trace Schema v1.0 (authoritative)

> Authoritative for **serialized data contracts**. Replay semantics are in `REPLAY_SPEC.md`.
> Implementation: `src/agenttrace/trace/schema.py` (models), `canonical.py`, `fingerprint.py`, `store.py`.

## 1. Files per run
```
runs/<run_id>/
  header.json     RunHeader           (observable)
  events.jsonl    one Event per line   (observable, ordered by seq)
  ledger.jsonl    one LedgerEntry per boundary event (PRIVILEGED: replay engine and benchmark validator only)
  fault_plan.json FaultPlan           (PRIVILEGED; present iff header.fault_plan_hash is not null)
  footer.json     RunFooter           (observable; presence marks a complete recording)
```
- **Write protocol:** files are written into `runs/.tmp-<run_id>-<random>/`, fsynced, and then the directory is atomically renamed to `runs/<run_id>/`. If the target exists, the write fails (recordings are immutable). Hidden `.tmp-*` directories are ignored by readers.
- **Readers:** `load_trace(run_id)` returns `Trace(header, events, footer)` (no ledger, no fault plan). `load_ledger(run_id)`, `load_fault_plan(run_id)` and `load_record(run_id)` are privileged by convention: localizer code must not call them (test-enforced from Week 3).

## 2. Enumerations
| Enum | Values |
|---|---|
| `RunMode` | `RECORD`, `REPLAY_STRICT`, `REPLAY_INTERVENE`, `REGRESSION` |
| `RunStatus` | `COMPLETED`, `MAX_STEPS`, `DIVERGED`, `INVALID_COUNTERFACTUAL`, `UNSUPPORTED`, `CONFIG_MISMATCH`, `INTERRUPTED` |
| `Outcome` | `PASS`, `FAIL`, `NOT_EVALUATED` |
| `Boundary` | `AGENT_STEP` (structural span), `DECISION`, `TOOL`, `CLOCK` (reserved), `IDGEN` (reserved) |
| `EventStatus` | `OK`, `ERROR`, `TIMEOUT` |
| `FaultStage` | `DECISION`, `PRE_EXECUTION`, `POST_EXECUTION` |
| `FaultEffect` | `prevented_execution`, `transformed_output` |
| `InterventionType` | `OBSERVATION_REPLACEMENT`, `EXECUTION_REPLACEMENT` |
| `ReferenceSource` | `REFERENCE_TOOL`, `REFERENCE_POLICY`, `ORIGINAL`, `INJECTION_CLEAN_VALUE` (validator only) |
| `DivergenceKind` | `MISSING_EVENT`, `TRUNCATED`, `BOUNDARY`, `NAME`, `REQUEST`, `RAW_RESULT`, `STATE`, `RESPONSE`, `OUTCOME` |

## 3. Models
All models use `extra="forbid"` and are frozen. `Json` means a JSON-pure value: `str | int | bool | None | list[Json] | dict[str, Json]` (no floats; Decimals are already converted to strings, §5).

### RunHeader
| Field | Type | Notes |
|---|---|---|
| `schema_version` | str | `"1.0"` |
| `run_id` | str | execution-specific (ADR-008) |
| `mode` | RunMode | |
| `parent_run_id` | str? | for replays/counterfactuals |
| `scenario` | `{id, version, initial_state_hash}` | |
| `agent` | `{policy_id, policy_version, source_hash}` | |
| `tool_manifest_hash` | str | ADR-012 |
| `fault_plan_hash` | str? | null = no fault plan |
| `oracle` | `{id, version}` | |
| `max_steps` | int ≥1 | |
| `config_fingerprint` | str | REPLAY_SPEC §8; validated on load (recomputed from the fields above) |
| `intervention` | Intervention? | REPLAY_INTERVENE only |
| `started_at` | UTC datetime | execution-specific |
| `agenttrace_version` | str | package version |

### Intervention
`target_seq: int`, `target_logical_key: str`, `boundary: Boundary`, `intervention_type`, `reference_source`, `is_placebo: bool`, `replacement_fp: str?` (optional; the intervened event's `response`/`response_fp` is authoritative), `expected_semantics: str`.

### Event (observable)
| Field | Type | Notes |
|---|---|---|
| `span_id` | str | execution-specific |
| `parent_span_id` | str? | decision/tool → their `AGENT_STEP` span; steps → null |
| `run_id` | str | must equal the header |
| `seq` | int ≥0 | contiguous from 0, authoritative order |
| `step_index` | int ≥0 | agent-loop iteration |
| `logical_key` | str | `"{step_index}:{boundary}:{name}#{occurrence}"`, occurrence counted per (boundary, name) |
| `boundary` | Boundary | |
| `name` | str | tool name; `"decide"` for decisions; `"step"` for spans |
| `status` | EventStatus | |
| `request` / `request_fp` | Json? / str? | tool: `{tool, args}`; decision: `{policy_id, policy_version, history_fp}`; null for spans |
| `response` / `response_fp` | Json? / str? | **delivered** value: tool `{status, data, error}`; decision `{kind, tool, args, summary}` |
| `state` | StateTransition? | tool events only |
| `attempt` | int? | tool events only (REPLAY_SPEC §3) |
| `intervened` | bool | true only at an intervention target |

### StateTransition
`before_hash: str`, `after_hash: str`, `committed: bool`, `delta: list[DeltaOp]`.
- Constraint: `committed == (before_hash != after_hash)`, and `delta` is empty iff not committed. Validated on load.

### DeltaOp
`op: "add" | "remove" | "replace"`, `path: str` (JSON-pointer style, e.g. `/refunds/R-0001`, `/orders/O1/refunded_amount`), `old: Json?`, `new: Json?`.

### LedgerEntry (privileged)
| Field | Type | Notes |
|---|---|---|
| `seq` | int | equals the observable event's seq |
| `boundary` | Boundary | `DECISION` or `TOOL` |
| `executed` | bool? | tools only: did S3 run? |
| `raw_output` / `raw_output_fp` | Json? / str? | decision: the raw policy decision; tool: the raw result; null if not executed |
| `fault_applications` | list[FaultApplication] | in stage order |

### FaultApplication
`fault_id: str`, `operator: str`, `stage: FaultStage`, `effect: FaultEffect`, `input_fp: str?`, `output_fp: str`.

### FaultPlan (privileged; schema `1.0`)
| Field | Type | Notes |
|---|---|---|
| `schema_version` | str | `"1.0"` |
| `plan_id` | str | free-form label |
| `faults` | list[FaultSpec] | applied in list order when several match |

**FaultSpec:** `fault_id` (unique in the plan), `operator` (registered name, §3.1), `stage` (FaultStage; must equal the operator's declared stage), `trigger`, `params` (Json object).

**FaultTrigger:** `boundary` (`TOOL` or `DECISION`), `name` (tool name for `TOOL`; null for `DECISION`), `occurrence` (≥1: the n-th call of that tool, or the n-th decision, in the run).

`fault_plan_hash = fp(FaultPlan)`. A plan is part of the run's configuration (it enters `config_fingerprint`), and strict replay re-applies it (REPLAY_SPEC §5.2).

### 3.1 Registered fault operators (Week 2)
| Operator | Stage | Params | Effect |
|---|---|---|---|
| `TIMEOUT_BEFORE_EXECUTION` (T0) | PRE_EXECUTION | `message?` | prevents execution; delivers TIMEOUT |
| `LOST_ACK` (F5) | POST_EXECUTION | `message?` | execution and commit happen; delivers TIMEOUT |
| `CORRUPT_OUTPUT` (F3) | POST_EXECUTION | `path` (list of keys/indices into the delivered response), `value` (Json) | replaces the value at `path`; no-op (and no application recorded) if the path does not exist |
| `REPLACE_DECISION` | DECISION | `decision` (a Decision object) | delivers the given decision instead of the raw one |

| `WRONG_TOOL` (F1) | DECISION | `tool`, `args` (Json object) | if the raw decision is a tool call to a *different* tool, deliver a call to `tool` with `args` instead; otherwise no-op |
| `WRONG_ARGUMENT` (F2) | DECISION | `tool`, `arg`, `mode` (`drop` / `replace`), `value` (for `replace`) | if the raw decision calls `tool` and has `arg`, drop it or replace its value; otherwise no-op |
| `WRONG_RETRIEVAL` (F4) | POST_EXECUTION | `data` (Json object: the wrong document) | if the delivered response is OK, replace its `data` with `data`; otherwise no-op |
| `DECOY_READ` (D1) | DECISION | `tool`, `args` | deliver a harmless read-only call instead of the raw decision; the scripted agent then re-issues its intended call on the next step. Harmlessness is *validated* per instance (decoy-only variant must pass), not assumed |

A "no-op" records no fault application. The benchmark validator rejects instances whose faults never fired.

### RunFooter
| Field | Type |
|---|---|
| `status` | RunStatus |
| `outcome` | `{outcome: Outcome, violated_clauses: [{clause_id, message, symptom_seq?}]}` |
| `final_state_hash` | str |
| `totals` | `{events, decisions, tool_calls, steps}` |
| `divergence` | `{seq, kind, expected_fp?, actual_fp?, detail}`? |
| `ended_at` | UTC datetime (execution-specific) |
| `wall_ms` | int (execution-specific, informational) |
| `integrity` | `{event_count, ledger_count, chain_root}` |

## 4. Versioning
- `schema_version` follows `MAJOR.MINOR`. A minor bump is additive (optional fields only). Loaders accept any `1.x`; an unknown major is rejected with `UnsupportedSchemaVersion`.

## 5. Canonical serialization (ADR-013)
`canonical_bytes(value)`:
- Decimal → normalized plain string (`Decimal("80.00")` → `"80"`, `Decimal("0.50")` → `"0.5"`). NaN and infinity are rejected.
- float → **rejected** (`CanonicalizationError`).
- str → NFC-normalized. Dict keys must be str and are sorted.
- Enum → `.value`. datetime → ISO 8601 UTC with `Z` (naive datetimes rejected). Pydantic model → `model_dump(mode="python")`, then the same rules. Tuples are encoded as lists.
- `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
- `to_json_value(value)` applies the same conversion but returns Python objects. Event payloads are converted at record time, so models round-trip exactly.

## 6. Fingerprints
| Fingerprint | Definition |
|---|---|
| `fp(x)` | `"sha256:" + hex(sha256(canonical_bytes(x)))` |
| `request_fp`, `response_fp`, `raw_output_fp` | `fp` of the respective payload |
| state hash | `fp(state.model_dump(mode="python"))` |
| `history_fp` | `fp` of the list of observations `[{seq, tool, args, response}]` |
| `config_fingerprint` | REPLAY_SPEC §8 |
| **semantic fingerprint** | `fp` of the run with execution-specific fields removed: `run_id`, `parent_run_id`, `started_at`, `agenttrace_version`, `span_id`, `parent_span_id` (replaced by the parent's `seq`), `ended_at`, `wall_ms`, `integrity`. Everything else (including the ledger) is included. Two deterministic executions of the same configuration must have equal semantic fingerprints. |

## 7. Integrity validation (on load)
1. All four files exist. A missing `footer.json` → `IncompleteRecordingError`; any other missing file → `CorruptTraceError`.
2. Each JSON document or line parses (a parse error → `CorruptTraceError` naming the file and line). Each validates against its model (→ `TraceSchemaError`). The schema major version is checked first.
3. Events: `run_id` equals the header; `seq` is contiguous from 0; parent ids refer to earlier `AGENT_STEP` events; each `request_fp`/`response_fp` matches its payload; each StateTransition satisfies its constraint.
4. Ledger: one entry per DECISION/TOOL event, with the same seq and boundary.
5. `config_fingerprint` matches the recomputation from header fields.
6. **Hash chain:** `c₀ = sha256("agenttrace-chain-v1")`; then the **header**, each event, then each ledger entry: `cᵢ = sha256(cᵢ₋₁ ‖ canonical_bytes(record))`. `integrity.chain_root = hex(c_last)`, and `event_count`/`ledger_count` must match. A mismatch → `TraceIntegrityError`. Because the header carries `fault_plan_hash`, the fault plan is covered transitively. The footer is not chained (it holds the root itself); its outcome is independently re-derived by strict replay.
7. **Fault plan:** `fault_plan.json` must exist iff `header.fault_plan_hash` is non-null (missing → `CorruptTraceError`; unexpected → `TraceIntegrityError`), and `fp(plan)` must equal the header hash (→ `TraceIntegrityError`).
8. Size guard: any single file over 64 MiB → `CorruptTraceError` (no pathological inputs).

The chain detects accidental corruption and truncation. **It is not a security control** against a party who can rewrite every file.

## 8. Leakage separation
- Localizers receive `Trace` (header, events, footer) only.
- Fault applications, raw outputs and pre-injection values exist only in the ledger.
- Benchmark labels (`labels.jsonl`, Week 3) are a separate file, never inside a run directory read by localizers.
- The header's `fault_plan_hash` is an opaque hash; the fault plan itself is stored outside the observable trace.

## 9. Benchmark files (Week 3, `benchmarks/synth_v0/`)
| File | Audience | Content |
|---|---|---|
| `manifest.json` | public | benchmark/generator version, seed, policy version, code fingerprints (tool manifest, policy source, scenario hashes, oracle), split definition, instance-file fingerprints, counts |
| `instances.jsonl` | evaluation driver | per instance: `instance_id`, `scenario_id`, `split`, `policy_version`, `fault_plan`. The plan is needed to *record* the run; it never reaches localizers, which receive only the recorded observable `Trace`. |
| `labels.jsonl` | **privileged** (validator and metrics only) | per instance: `label` (`CLEAN`/`CAUSAL`/`MASKED`/`DECOY_ONLY`), operators, injection sites (seq and logical key), decoy seqs, `symptom_seq`, `symptom_distance`, `expected_category`, `confirmed_by_clean_value` |
| `rejected.jsonl` | public | generated candidates rejected by validation, with reasons |

Localizer modules must not import benchmark label loaders, the store's privileged loaders or the fault layer (test-enforced).
