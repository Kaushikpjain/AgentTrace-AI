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
- Development decisions (metrics, the secondary match, report wording) used the dev split only. The test split was evaluated **exactly once**, at the freeze (2026-11-23, run `b9c61e38…`, see §9 and `FREEZE.md`). Nothing has been tuned on it since; later code changes are post-freeze and listed separately.
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

## 9. Official held-out results (test split, frozen 0.1.0rc1 implementation)
**Provenance.** One run, 2026-11-23T16:59:52Z: `atrace bench run --split test --confirm-single-test-run` at `bench-freeze-v0` = `eb6d95c`, clean tree, exit 0, run `b9c61e380f3a402f986f7d98b5147bfd`. Artifacts: `evaluation/synth_v0-test/` (integrity verified, see `FREEZE.md`). Wall time 2.91 s for the whole process (`/usr/bin/time -l`; 2.345 s in-process `evaluation_seconds`), peak RSS ≈ 44 MB. These numbers belong to the frozen implementation. Post-freeze code has **not** been re-evaluated on the test split. The protocol allows a rerun only as a reproducibility check.

**Population.** 37 instances (CAUSAL 24, MASKED 5, CLEAN 4, DECOY_ONLY 4) from the 4 held-out templates T5–T8. **22 eligible** CAUSAL single-site instances for Metric A; the 2 MULTI instances are reported under Metric B.

### Metric A: injection-site localization (n = 22; k/n [Wilson 95% CI]; MRR with template-bootstrap CI)
| Method | Top-1 (primary) | Top-3 | MRR [95% CI] | Top-1 same-step action (secondary) | Decoy ranked first |
|---|---|---|---|---|---|
| B1 | 10/22 [0.27, 0.65] | 10/22 [0.27, 0.65] | 0.540 [0.394, 0.610] | 20/22 [0.72, 0.97] | 0/2 |
| B3 | 10/22 [0.27, 0.65] | 13/22 [0.39, 0.77] | 0.580 [0.433, 0.649] | 20/22 [0.72, 0.97] | 0/2 |
| B4 | 20/22 [0.72, 0.97] | 22/22 [0.85, 1.00] | 0.955 [0.933, 1.000] | 20/22 [0.72, 0.97] | 2/2 |
| CF | 22/22 [0.85, 1.00] | 22/22 [0.85, 1.00] | 1.000 [1.000, 1.000] | 22/22 [0.85, 1.00] | 0/2 |
| B0 (random, analytical) | expected 0.120 | expected 0.360 | expected 0.328 | | |

No method left the injection site unranked.

**Top-1 by fault operator**
| Operator (n) | B1 | B3 | B4 | CF |
|---|---|---|---|---|
| CORRUPT_OUTPUT (3) | 3/3 | 3/3 | 3/3 | 3/3 |
| LOST_ACK (3) | 3/3 | 3/3 | 3/3 | 3/3 |
| WRONG_ARGUMENT (8) | 0/8 | 0/8 | 8/8 | 8/8 |
| WRONG_RETRIEVAL (4) | 4/4 | 4/4 | 2/4 | 4/4 |
| WRONG_TOOL (4) | 0/4 | 0/4 | 4/4 | 4/4 |

**Top-1 by symptom distance:** distance 0 (n = 3): B1 0/3, B3 0/3, B4 3/3, CF 3/3. Distance ≥ 1 (n = 19): B1 10/19, B3 10/19, B4 17/19, CF 19/19.

**Paired Top-1 comparisons** (exact two-sided McNemar, Holm-adjusted; descriptive only):
| Comparison | only first correct | only second correct | p exact | p Holm |
|---|---|---|---|---|
| CF vs. B4 | 2 | 0 | 0.5000 | 0.5000 |
| CF vs. B1 | 12 | 0 | 0.0005 | 0.0015 |
| B4 vs. B1 | 12 | 2 | 0.0129 | 0.0259 |

### Metric B: interventional repair (CF)
- Repair success (CAUSAL runs with ≥ 1 `INTERVENTIONAL_REPAIR`): **22/24** [0.74, 0.98]. The two misses are the MULTI instances `T6-MULTI-F4+F2` and `T8-MULTI-F4+F3`, both `NOT_ISOLATED`.
- Injected site itself repaired (eligible): 22/22 [0.85, 1.00]. Runs with multiple repair sites: 0.
- Placebo validity: **39/39** [0.91, 1.00]; 0 placebos not completed. Experiments: 39 COMPLETED (18 execution, 21 observation replacements). UNSUPPORTED steps: 0/342.

### Metric C and cost
- Evidence on the 24 CAUSAL runs: B1/B3 suspicion only (24); B4 reference deviations only (24); CF 22 repair-site conclusions + 2 `NOT_ISOLATED`.
- Replays per investigation (eligible): CF mean 10.9, median 10, max 14, total 240. B4 mean 8.7, median 8, max 12, total 192. B1/B3 use none.

### Correctness checks (all OK)
Strict replay VERIFIED 37/37; placebo valid 39/39; false repairs on passing runs 0; UNSUPPORTED without reason 0; cassette accesses after the fence 0; 17 regression runs constructed 0 cassettes; benchmark equals its regeneration.

### How to read these results
- **Synthetic and scripted.** These are results on a scripted synthetic benchmark (one domain, one deterministic agent, injected faults). They are **not** real-world LLM accuracy results.
- **Trusted references.** CF and B4 can use a trusted reference for every step only because the agent is scripted. That limits generalization; for real LLM agents many interventions would be `UNSUPPORTED`. Treat CF here as an upper bound.
- **CF vs. B4 is not established.** CF beats B4 on 2 discordant instances and loses on none (p Holm = 0.50). With n = 22 that is not a statistically established difference.
- **The secondary metric narrows the gap.** Under the same-step action match, B1 and B3 reach 20/22, the same as B4, versus CF's 22/22. Most of their strict misses are the tool call issued by the faulty decision.
- **Four templates only.** The held-out split has 4 scenario templates. Instances within a template are dependent, so the template-bootstrap MRR intervals are coarse.
- **Repair is not unique causation.** `INTERVENTIONAL_REPAIR` means "replacing this step was sufficient to repair this run with a valid placebo". If several steps could each repair a run, none is "the" cause; injection-site Top-1 measures agreement with where the fault was injected.
- **Multi-fault localization is unresolved.** Single-step interventions cannot isolate jointly sufficient faults (both MULTI instances are `NOT_ISOLATED`).
- **Dev vs. test.** CF was 16/16 on dev and 22/22 on test; B4 13/16 and 20/22; B1/B3 8/16 and 10/22. No method was tuned on the test split.
