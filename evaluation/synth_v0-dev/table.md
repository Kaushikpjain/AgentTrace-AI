# AgentTrace-Synth synth_v0: split `dev`

Instances: 30 {'CAUSAL': 16, 'CLEAN': 4, 'DECOY_ONLY': 4, 'MASKED': 6}. Eligible for Metric A: **16** (label CAUSAL with exactly one injection site (MULTI excluded)).

> Injection-site localization measures whether a method ranks the *step where the fault was injected* first. It is not unique causal attribution. Rates show k/n = rate [Wilson 95% CI]; MRR intervals are cluster (template) bootstrap. Small n: intervals are wide and the paired tests are descriptive only. MRR intervals resample templates; with only 4 templates per split they are coarse and can be degenerate.

> *Secondary* same-step action match: a DECISION injection site also counts when its own tool call is ranked first (that call is the decision's first visible effect). Added during the dev review; the strict site match is the primary metric.

## Metric A: injection-site localization

| method | Top-1 (primary) | Top-3 | MRR [95% CI] | Top-1 same-step action (secondary) | not ranked | decoy false attribution |
|---|---|---|---|---|---|---|
| B1 | 8/16 = 0.5000 [0.2800, 0.7200] | 8/16 = 0.5000 [0.2800, 0.7200] | 0.5748 [0.3798, 0.6253] | 14/16 = 0.8750 [0.6398, 0.9650] | 0 | 0/3 = 0.0000 [0.0000, 0.5615] |
| B3 | 8/16 = 0.5000 [0.2800, 0.7200] | 9/16 = 0.5625 [0.3318, 0.7690] | 0.5875 [0.3667, 0.6627] | 14/16 = 0.8750 [0.6398, 0.9650] | 0 | 0/3 = 0.0000 [0.0000, 0.5615] |
| B4 | 13/16 = 0.8125 [0.5699, 0.9341] | 16/16 = 1.0000 [0.8064, 1.0000] | 0.9062 [0.8750, 0.9375] | 13/16 = 0.8125 [0.5699, 0.9341] | 0 | 3/3 = 1.0000 [0.4385, 1.0000] |
| CF | 16/16 = 1.0000 [0.8064, 1.0000] | 16/16 = 1.0000 [0.8064, 1.0000] | 1.0000 [1.0000, 1.0000] | 16/16 = 1.0000 [0.8064, 1.0000] | 0 | 0/3 = 0.0000 [0.0000, 0.5615] |
| B0 (random, analytical) | E = 0.1167 | E = 0.3500 | E = 0.3220 | - | - | - |

### Top-1 by fault operator

| operator | B1 | B3 | B4 | CF |
|---|---|---|---|---|
| CORRUPT_OUTPUT | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] |
| LOST_ACK | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] |
| WRONG_ARGUMENT | 0/4 = 0.0000 [0.0000, 0.4899] | 0/4 = 0.0000 [0.0000, 0.4899] | 4/4 = 1.0000 [0.5101, 1.0000] | 4/4 = 1.0000 [0.5101, 1.0000] |
| WRONG_RETRIEVAL | 6/6 = 1.0000 [0.6097, 1.0000] | 6/6 = 1.0000 [0.6097, 1.0000] | 3/6 = 0.5000 [0.1876, 0.8124] | 6/6 = 1.0000 [0.6097, 1.0000] |
| WRONG_TOOL | 0/4 = 0.0000 [0.0000, 0.4899] | 0/4 = 0.0000 [0.0000, 0.4899] | 4/4 = 1.0000 [0.5101, 1.0000] | 4/4 = 1.0000 [0.5101, 1.0000] |

### Top-1 by symptom distance (tool calls between injection and visible symptom)

| distance | B1 | B3 | B4 | CF |
|---|---|---|---|---|
| 0 | 0/1 = 0.0000 [0.0000, 0.7935] | 0/1 = 0.0000 [0.0000, 0.7935] | 1/1 = 1.0000 [0.2065, 1.0000] | 1/1 = 1.0000 [0.2065, 1.0000] |
| >=1 | 8/15 = 0.5333 [0.3012, 0.7519] | 8/15 = 0.5333 [0.3012, 0.7519] | 12/15 = 0.8000 [0.5481, 0.9295] | 15/15 = 1.0000 [0.7961, 1.0000] |

### Paired Top-1 comparisons (exact two-sided McNemar on Top-1, Holm-adjusted over the listed comparisons; descriptive only; small n, no significance claim is made)

| comparison | only first correct | only second correct | n | p exact | p Holm |
|---|---|---|---|---|---|
| CF_vs_B4 | 3 | 0 | 16 | 0.2500 | 0.4531 |
| CF_vs_B1 | 8 | 0 | 16 | 0.0078 | 0.0234 |
| B4_vs_B1 | 8 | 3 | 16 | 0.2266 | 0.4531 |

## Metric B: interventional repair (CF)

- Repair success (CAUSAL runs with ≥1 INTERVENTIONAL_REPAIR): 16/16 = 1.0000 [0.8064, 1.0000]
- Injected site itself repaired (eligible): 16/16 = 1.0000 [0.8064, 1.0000]
- Placebo validity (completed placebos reproducing the original): 30/30 = 1.0000 [0.8865, 1.0000]; placebos not completed: 0
- Experiments: 30 by status {'COMPLETED': 30}, by type {'EXECUTION_REPLACEMENT': 13, 'OBSERVATION_REPLACEMENT': 17}
- UNSUPPORTED steps: 0/268 = 0.0000 [0.0000, 0.0141]; by reason {}
- Runs with multiple repair sites: 0 []

## Metric C: diagnostic evidence

| method | SUSPICION | REFERENCE_DEVIATION | INTERVENTIONAL_REPAIR | UNSUPPORTED | run conclusions (all CAUSAL) |
|---|---|---|---|---|---|
| B1 | 144 | 0 | 0 | 0 | {'suspicion only': 16} |
| B3 | 144 | 0 | 0 | 0 | {'suspicion only': 16} |
| B4 | 125 | 19 | 0 | 0 | {'reference deviations only (no interventions)': 16} |
| CF | 125 | 3 | 16 | 0 | {'repair sites': 16} |

## Replay cost (replays per investigation; eligible instances)

| method | mean | median | max | total |
|---|---|---|---|---|
| B1 | 0.0000 | 0.0000 | 0 | 0 |
| B3 | 0.0000 | 0.0000 | 0 | 0 |
| B4 | 9.0000 | 10.0000 | 12 | 144 |
| CF | 11.3750 | 12.0000 | 16 | 182 |

## Regression (candidate v2, environment fixture only)

| instance | baseline | verdict | comparison | runs | cassettes built |
|---|---|---|---|---|---|
| T1-F3 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T1-F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T1-F5 | FAIL | DETERMINISTIC_PASS | FIXED | 2/2 | 0 |
| T1-D1+F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T2-F3 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T2-F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T2-D1+F4 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T3-F3 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T3-F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T3-D1+F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T4-F3 | PASS | DETERMINISTIC_PASS | STILL_PASSING | 2/2 | 0 |
| T4-F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |
| T4-D1+F4 | FAIL | DETERMINISTIC_FAIL | STILL_FAILING | 0/2 | 0 |

## Correctness checks

- Strict replay VERIFIED: 30/30 = 1.0000 [0.8865, 1.0000]
- Placebo valid among completed: 30/30 = 1.0000 [0.8865, 1.0000]
- False repairs on passing runs: 0
- UNSUPPORTED steps without a reason: 0
- Max cassette accesses after fence: 0
- Regression runs checked: 13; cassettes built: 0
- Benchmark matches regeneration: True
- **Overall: OK**

## Limitations

- Synthetic scripted agent, one domain; injected faults are not natural LLM failures.
- Trusted references exist for every step only because the agent is scripted; CF results are an upper bound for settings where such references exist.
- Some faults are visible in tool responses (inconsistent totals, archived policy flag).
