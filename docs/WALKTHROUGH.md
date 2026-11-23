# Failure-investigation walkthrough

A guided tour of one failure, using only commands that exist. Everything is deterministic, offline and runs in a few seconds on a laptop. Use a scratch store so `./runs` stays clean:

```bash
export ATRACE_RUNS_DIR=$(mktemp -d)
```

## 1. Record a failing run
```bash
uv run atrace inject T1-D1+F4
```
`T1-D1+F4` is a benchmark instance with two faults:
- **D1:** the agent's second decision is replaced by a harmless extra `get_customer` read (a decoy);
- **F4:** `search_policy` returns an *archived* policy document with a lower refund limit (50 instead of 100).

The 80.00 refund now looks over the limit, so the agent escalates. The oracle reports **FAIL**: `REFUND_SET`, `TICKET_STATE`.

Copy the printed run id (`run-…`) into `RUN` below.

## 2. Inspect and verify the recording
```bash
uv run atrace show $RUN       # schema, fingerprints, hash chain: "integrity verified"
uv run atrace replay $RUN     # REPLAY_STRICT: VERIFIED, no policy calls, all fidelity metrics equal
```
Strict replay restores the initial state, serves the recorded decisions and **re-executes** every tool with the recorded fault plan. It checks raw results, state transitions, delivered responses, the final state and the outcome. Any difference would be reported as the first divergence.

## 3. Rank suspicious steps
```bash
uv run atrace investigate $RUN --markdown report.md
```
| Method | Top-ranked step | Why |
|---|---|---|
| B1 / B3 | seq 11 `search_policy` | the validator flags `RETRIEVED_ARCHIVED_POLICY` (this fault is observable) |
| B4 | seq 4, the **decoy** decision | it is the *earliest* step that deviates from its reference, but harmless |
| CF | seq 11, `INTERVENTIONAL_REPAIR` | the only step whose replacement repairs the run with a valid placebo |

## 4. Run the controlled experiment yourself
```bash
uv run atrace intervene $RUN --seq 11 --type execution
```
- **Intervention:** EXECUTION_REPLACEMENT with REFERENCE_TOOL re-runs `search_policy` *without the fault layer*. The cassette is closed after seq 11, and the agent continues live. The run passes, because the refund is issued and the ticket closed as REFUNDED.
- **Placebo:** the same code path with the *original* faulty execution reproduces the failure exactly.
- **Evidence:** `INTERVENTIONAL_REPAIR`, meaning this replacement was *sufficient to repair this run*. It is not a unique cause.

Compare with the decoy:
```bash
uv run atrace intervene $RUN --seq 4 --type observation   # reference decision at the decoy
```
The intervention still fails and the placebo is valid, so the step is a reference deviation without repair evidence.

Unsupported requests are refused, not guessed:
```bash
uv run atrace intervene $RUN --seq 10 --type execution    # decision seq: exit 5, UNSUPPORTED
```

## 5. Regression: does a fix actually work?
```bash
uv run atrace inject T1-F5                  # lost acknowledgement: agent v1 refunds twice (FAIL)
uv run atrace regress <that run id> --policy v2
```
Regression runs the candidate **freshly** against the same scenario and environment fixture. No cassette is constructed and no recorded decision is reused. Agent v2 uses an idempotency key, giving `DETERMINISTIC_PASS` and `FIXED`.

## 6. What this does *not* show
- References exist for every step because the agent is scripted. For real LLM agents most steps would be `UNSUPPORTED` (no trusted reference).
- Two individually sufficient faults (the MULTI instances) cannot be isolated by single-step interventions; CF reports `NOT_ISOLATED`.
