# Evaluation Methodology (AgentTrace-Synth v0)

Authoritative for how results are computed. The implementation lives in `agenttrace.bench`. The commands are `atrace bench run`, `atrace bench verify` and `atrace bench config`.

## 1. What is evaluated
Four localizers rank the steps of a failed run of the scripted support agent (v1):
| Method | Inputs | Idea |
|---|---|---|
| B1 | observable trace + validator flags | earliest visible error (flagged or ERROR/TIMEOUT), then the symptom |
| B3 | same | fixed integer score: 2·chain + 3·flag + 1·error + 1·mutating (ADR-018) |
| B4 | + InterventionService | earliest step whose value or transition deviates from its trusted reference |
| CF | + InterventionService | placebo-controlled single-step counterfactual (REPLAY_SPEC §14) |
| B0 | — | analytical expectation of a uniformly random ranking (reference line only) |

Localizers never see labels, fault plans, ledgers or clean values. `bench/evaluate.py` produces label-free results; `bench/metrics.py` joins labels afterwards (both are checked by tests).

## 2. Benchmark and splits
- 67 validated instances (`benchmarks/synth_v0/`). The split is by scenario template: **dev = T1–T4, test = T5–T8**.
- Labels: CLEAN, CAUSAL (fault fired and the run failed), MASKED (fault fired, run passed), DECOY_ONLY (harmless decoy, validated).
- **Eligible set for Metric A:** CAUSAL instances with exactly one injection site. All methods are scored on the identical eligible set. The 2 MULTI instances (test split) are reported separately under Metric B.

## 3. Metrics
**Metric A: injection-site localization** (eligible set).
- Top-1 (primary): the method's first-ranked step is the injected step.
- Top-3; MRR (1/rank, 0 if not ranked).
- By fault operator; by symptom distance (tool calls between the injected step and the visible symptom: 0 vs. ≥1).
- Decoy false attribution: among eligible instances that contain a decoy, how often the decoy is ranked first.
- *Secondary* "same-step action" Top-1: a DECISION site also counts when its own tool call is ranked first. This was added in the dev review because B1/B3 by design flag the tool call that a faulty decision issues. The strict match remains primary.
- **Interpretation:** this measures agreement with *where the fault was injected*. It is not unique causal attribution.

**Metric B: interventional repair** (CF).
- Repair success: CAUSAL runs (including MULTI) with ≥1 `INTERVENTIONAL_REPAIR`.
- Injected site repaired (eligible set).
- Runs with multiple repair sites (listed).
- Placebo validity among completed placebos (any failure aborts the run as a violation). Placebos not completed are counted, never dropped.
- Experiments by status (COMPLETED / UNSUPPORTED / INVALID_COUNTERFACTUAL / CONFIG_MISMATCH) and by type. Unsupported steps by reason.
- Replay cost: replays per investigation (probes + interventions + placebos) for B4 and CF.

**Metric C: diagnostic evidence.** Per method: counts of step labels `SUSPICION`, `REFERENCE_DEVIATION`, `INTERVENTIONAL_REPAIR`, `UNSUPPORTED` on the eligible set, and run conclusions on all CAUSAL runs (repair sites vs. `NOT_ISOLATED`).

## 4. Statistics
- Every rate is reported as **k/n = rate [Wilson 95% CI]**.
- MRR intervals: percentile bootstrap resampling **templates** with replacement (seed 0, 2,000 resamples). With 4 templates per split these intervals are coarse and can be degenerate. They are reported, not relied on.
- Paired Top-1 comparisons (CF vs. B4, CF vs. B1, B4 vs. B1): exact two-sided McNemar on discordant pairs, Holm-adjusted. **Descriptive only.** With n = 16 (dev) or 22 (test single-site), no significance claim is made.
- Rates are rounded to 4 decimals (`Decimal`, ROUND_HALF_EVEN) before serialization.

## 5. Correctness checks (a run with any violation exits 1)
1. Every recorded instance replays strict-VERIFIED.
2. Every completed placebo reproduces the original status, outcome, clauses and final state.
3. No `INTERVENTIONAL_REPAIR` on passing original runs (CLEAN, MASKED, DECOY_ONLY are evaluated too).
4. Every `UNSUPPORTED` step carries a reason.
5. Zero cassette accesses after any intervention fence.
6. Regression runs (candidate v2, environment fixture only) construct zero cassettes.
7. Benchmark files equal a deterministic regeneration.

## 6. Reproducibility
- Canonical outputs (byte-identical for the same configuration): `metrics.json`, `config.json`, `results.jsonl`, `table.md`, `failure_cases.md`, `canonical_fingerprints.json`.
- Volatile outputs (never compared): `environment.json` (run id, timestamp, git state, versions), `timings.json` (wall time, peak RSS).
- `make reproduce-dev` runs the dev evaluation twice and compares the canonical files with `cmp`. A test does the same on a subset.

## 7. Held-out protocol
- Development decisions (metrics, the secondary match, report wording) use the dev split only. The test split has not been evaluated.
- `atrace bench run --split test` refuses unless the working tree is clean, `HEAD` equals the tag `bench-freeze-v0`, and `--confirm-single-test-run` is given. Each test run is appended to `evaluation/TEST_RUNS.log`.
- A rerun is permitted only as a reproducibility check and must produce identical canonical outputs.
- See `FREEZE.md` for the frozen configuration.

## 8. Threats to validity
- **Synthetic and scripted:** one domain, one agent; injected faults are not natural LLM failures.
- **References:** trusted references exist for every step only because the agent is scripted (ADR-017). CF and B4 results are upper bounds for settings with such references.
- **Observability:** some faults are visible in tool responses (inconsistent totals; the `archived` policy flag), which favours B1/B3 on those operators.
- **Small n and few templates:** wide intervals; template-level dependence.
- **Single-step interventions** cannot isolate jointly sufficient faults (MULTI → `NOT_ISOLATED`).
- **Benchmark-design coupling:** the generator, operators and localizers were written by the same team, in the same week.
