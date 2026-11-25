# AgentTrace-Synth synth_v0: split `test`

Instances: 37 {'CAUSAL': 24, 'CLEAN': 4, 'DECOY_ONLY': 4, 'MASKED': 5}. Eligible for Metric A: **22** (label CAUSAL with exactly one injection site (MULTI excluded)).

> Injection-site localization measures whether a method ranks the *step where the fault was injected* first. It is not unique causal attribution. Rates show k/n = rate [Wilson 95% CI]; MRR intervals are cluster (template) bootstrap. Small n: intervals are wide and the paired tests are descriptive only. MRR intervals resample templates; with only 4 templates per split they are coarse and can be degenerate.

> *Secondary* same-step action match: a DECISION injection site also counts when its own tool call is ranked first (that call is the decision's first visible effect). Added during the dev review; the strict site match is the primary metric.

## Metric A: injection-site localization

| method | Top-1 (primary) | Top-3 | MRR [95% CI] | Top-1 same-step action (secondary) | not ranked | decoy false attribution |
|---|---|---|---|---|---|---|
| B1 | 10/22 = 0.4545 [0.2692, 0.6534] | 10/22 = 0.4545 [0.2692, 0.6534] | 0.5402 [0.3944, 0.6097] | 20/22 = 0.9091 [0.7219, 0.9747] | 0 | 0/2 = 0.0000 [0.0000, 0.6576] |
| B3 | 10/22 = 0.4545 [0.2692, 0.6534] | 13/22 = 0.5909 [0.3873, 0.7674] | 0.5803 [0.4333, 0.6489] | 20/22 = 0.9091 [0.7219, 0.9747] | 0 | 0/2 = 0.0000 [0.0000, 0.6576] |
| B4 | 20/22 = 0.9091 [0.7219, 0.9747] | 22/22 = 1.0000 [0.8513, 1.0000] | 0.9545 [0.9333, 1.0000] | 20/22 = 0.9091 [0.7219, 0.9747] | 0 | 2/2 = 1.0000 [0.3424, 1.0000] |
| CF | 22/22 = 1.0000 [0.8513, 1.0000] | 22/22 = 1.0000 [0.8513, 1.0000] | 1.0000 [1.0000, 1.0000] | 22/22 = 1.0000 [0.8513, 1.0000] | 0 | 0/2 = 0.0000 [0.0000, 0.6576] |
| B0 (random, analytical) | E = 0.1201 | E = 0.3602 | E = 0.3284 | - | - | - |

### Top-1 by fault operator

| operator | B1 | B3 | B4 | CF |
|---|---|---|---|---|
| CORRUPT_OUTPUT | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] |
| LOST_ACK | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] |
| WRONG_ARGUMENT | 0/8 = 0.0000 [0.0000, 0.3244] | 0/8 = 0.0000 [0.0000, 0.3244] | 8/8 = 1.0000 [0.6756, 1.0000] | 8/8 = 1.0000 [0.6756, 1.0000] |
| WRONG_RETRIEVAL | 4/4 = 1.0000 [0.5101, 1.0000] | 4/4 = 1.0000 [0.5101, 1.0000] | 2/4 = 0.5000 [0.1500, 0.8500] | 4/4 = 1.0000 [0.5101, 1.0000] |
| WRONG_TOOL | 0/4 = 0.0000 [0.0000, 0.4899] | 0/4 = 0.0000 [0.0000, 0.4899] | 4/4 = 1.0000 [0.5101, 1.0000] | 4/4 = 1.0000 [0.5101, 1.0000] |

### Top-1 by symptom distance (tool calls between injection and visible symptom)

| distance | B1 | B3 | B4 | CF |
|---|---|---|---|---|
| 0 | 0/3 = 0.0000 [0.0000, 0.5615] | 0/3 = 0.0000 [0.0000, 0.5615] | 3/3 = 1.0000 [0.4385, 1.0000] | 3/3 = 1.0000 [0.4385, 1.0000] |
| >=1 | 10/19 = 0.5263 [0.3171, 0.7267] | 10/19 = 0.5263 [0.3171, 0.7267] | 17/19 = 0.8947 [0.6861, 0.9706] | 19/19 = 1.0000 [0.8318, 1.0000] |

### Paired Top-1 comparisons (exact two-sided McNemar on Top-1, Holm-adjusted over the listed comparisons; descriptive only; small n, no significance claim is made)

| comparison | only first correct | only second correct | n | p exact | p Holm |
|---|---|---|---|---|---|
| CF_vs_B4 | 2 | 0 | 22 | 0.5000 | 0.5000 |
| CF_vs_B1 | 12 | 0 | 22 | 0.0005 | 0.0015 |
| B4_vs_B1 | 12 | 2 | 22 | 0.0129 | 0.0259 |

## Metric B: interventional repair (CF)

- Repair success (CAUSAL runs with ≥1 INTERVENTIONAL_REPAIR): 22/24 = 0.9167 [0.7415, 0.9768]
- Injected site itself repaired (eligible): 22/22 = 1.0000 [0.8513, 1.0000]
- Placebo validity (completed placebos reproducing the original): 39/39 = 1.0000 [0.9103, 1.0000]; placebos not completed: 0
- Experiments: 39 by status {'COMPLETED': 39}, by type {'EXECUTION_REPLACEMENT': 18, 'OBSERVATION_REPLACEMENT': 21}
- UNSUPPORTED steps: 0/342 = 0.0000 [0.0000, 0.0111]; by reason {}
- Runs with multiple repair sites: 0 []
- Multi-fault `T6-MULTI-F4+F2`: NOT_ISOLATED
- Multi-fault `T8-MULTI-F4+F3`: NOT_ISOLATED

## Metric C: diagnostic evidence

| method | SUSPICION | REFERENCE_DEVIATION | INTERVENTIONAL_REPAIR | UNSUPPORTED | run conclusions (all CAUSAL) |
|---|---|---|---|---|---|
| B1 | 192 | 0 | 0 | 0 | {'suspicion only': 24} |
| B3 | 192 | 0 | 0 | 0 | {'suspicion only': 24} |
| B4 | 168 | 24 | 0 | 0 | {'reference deviations only (no interventions)': 24} |
| CF | 168 | 2 | 22 | 0 | {'NOT_ISOLATED': 2, 'repair sites': 22} |

## Replay cost (replays per investigation; eligible instances)

| method | mean | median | max | total |
|---|---|---|---|---|
| B1 | 0.0000 | 0.0000 | 0 | 0 |
| B3 | 0.0000 | 0.0000 | 0 | 0 |
| B4 | 8.7273 | 8.0000 | 12 | 192 |
| CF | 10.9091 | 10.0000 | 14 | 240 |

## Regression (candidate v2, environment fixture only)

| instance | baseline | verdict | comparison | runs | cassettes built |
|---|---|---|---|---|---|
| T5-F3 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T5-F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T5-D1+F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T6-F3 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T6-F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T6-F5 | FAIL | DETERMINISTIC_PASS | FIXED | 2/2 | 0 |
| T6-D1+F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T7-F3 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T7-F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T7-F5 | FAIL | DETERMINISTIC_PASS | FIXED | 2/2 | 0 |
| T7-D1+F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T8-F3 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T8-F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T8-F5 | FAIL | DETERMINISTIC_PASS | FIXED | 2/2 | 0 |
| T8-D1+F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T6-MULTI-F4+F2 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T8-MULTI-F4+F3 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |

## Correctness checks

- Strict replay VERIFIED: 37/37 = 1.0000 [0.9059, 1.0000]
- Placebo valid among completed: 39/39 = 1.0000 [0.9103, 1.0000]
- False repairs on passing runs: 0
- UNSUPPORTED steps without a reason: 0
- Max cassette accesses after fence: 0
- Regression runs checked: 17; cassettes built: 0
- Benchmark matches regeneration: True
- **Overall: OK**

## Limitations

- Synthetic scripted agent, one domain; injected faults are not natural LLM failures.
- Trusted references exist for every step only because the agent is scripted; CF results are an upper bound for settings where such references exist.
- Some faults are visible in tool responses (inconsistent totals, archived policy flag).
