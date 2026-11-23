# Failure-case gallery

Representative cases where a method's top-1 is not the injection site, UNSUPPORTED steps, decoy misses and multi-fault conclusions. Reproduce any case with `atrace inject <instance>` and then `atrace investigate <run_id>`.

## Top-1 misses (eligible instances)

| instance | method | operator | injection seq | top-1 seq | note | conclusion |
|---|---|---|---|---|---|---|
| T1-F1 | B1 | WRONG_TOOL | 10 | 11 | other step ranked first | suspicion only |
| T1-F1 | B3 | WRONG_TOOL | 10 | 11 | other step ranked first | suspicion only |
| T1-F2-order | B1 | WRONG_ARGUMENT | 4 | 5 | other step ranked first | suspicion only |
| T1-F2-order | B3 | WRONG_ARGUMENT | 4 | 5 | other step ranked first | suspicion only |
| T1-F2-amount | B1 | WRONG_ARGUMENT | 10 | 11 | other step ranked first | suspicion only |
| T1-F2-amount | B3 | WRONG_ARGUMENT | 10 | 11 | other step ranked first | suspicion only |
| T1-D1+F4 | B4 | WRONG_RETRIEVAL | 11 | 4 | decoy ranked first | reference deviations only (no interventions) |
| T2-F1 | B1 | WRONG_TOOL | 10 | 11 | other step ranked first | suspicion only |
| T2-F1 | B3 | WRONG_TOOL | 10 | 11 | other step ranked first | suspicion only |
| T3-F1 | B1 | WRONG_TOOL | 10 | 14 | other step ranked first | suspicion only |
| T3-F1 | B3 | WRONG_TOOL | 10 | 14 | other step ranked first | suspicion only |
| T3-F2-order | B1 | WRONG_ARGUMENT | 4 | 5 | other step ranked first | suspicion only |

_7 more misses omitted; see results.jsonl._

## UNSUPPORTED steps

| instance | method | seq | reason |
|---|---|---|---|
| none | | | |
