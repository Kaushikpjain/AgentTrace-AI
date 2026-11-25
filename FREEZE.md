# Benchmark freeze: AgentTrace-Synth v0 (APPROVED and EXECUTED)

> **Status: APPROVED and EXECUTED.** The owner approved the freeze; the annotated tag `bench-freeze-v0` was created locally on commit `eb6d95c19d0ae886cef1b0ae4fca431d6fa29a50`; the held-out test split was evaluated **exactly once** on 2026-11-23 (run `b9c61e380f3a402f986f7d98b5147bfd`, exit 0). Results are in `evaluation/synth_v0-test/` and summarised in `docs/EVALUATION.md` §9.
>
> This file was written before the freeze and is part of the frozen commit; this status block was updated afterwards. Code changed after the freeze is listed in "Post-freeze changes" below. The held-out metrics belong to the frozen implementation (released as 0.1.0rc1), not to later code.

## What is frozen
| Item | Value | Recompute with |
|---|---|---|
| Code | `eb6d95c19d0ae886cef1b0ae4fca431d6fa29a50` (annotated tag `bench-freeze-v0`, tag object `c2c3895c833929abec8ce696964d4ce6d7c5aae4`, local only) | `git rev-parse bench-freeze-v0^{commit}` |
| Benchmark | `benchmarks/synth_v0/` (67 instances; manifest fingerprint `sha256:522bad8b28c6cafd1f620ce842c8867f9d85f8468aa6f7f668e8d4039ec2816c`) | `uv run atrace bench verify` |
| Test-split evaluation configuration | `config_fingerprint: sha256:7a37fd81040a1bca42e11b8102a9ed91e2c429d453653c2542b7e05d8b8f5316` | `uv run atrace bench config --split test` |
| Dev-split evaluation configuration | `config_fingerprint: sha256:6dab492e96169dcdd45cd00e54ea4b9ab8313ce1f8c22c5c86ff967831fac470` | `uv run atrace bench config --split dev` |
| Methods | B1, B3, B4, CF (+ analytical B0) | `config.json` |
| B3 weights | chain 2, flag 3, error 1, mutating 1 (ADR-018) | `config.json` |
| Statistics | Wilson 95%; template bootstrap seed 0, 2,000 resamples; exact McNemar + Holm | `docs/EVALUATION.md` |
| Primary metric | Metric A strict Top-1 on CAUSAL single-site instances | `docs/EVALUATION.md` §3 |

## Changes made during the dev review (before freeze)
1. Added the *secondary* "same-step action" Top-1 (ADR-022). The primary metric is unchanged.
2. Documented that template-bootstrap MRR intervals are coarse with 4 templates per split.
3. Gallery text points to `results.jsonl`.

No localizer, weight, threshold or benchmark instance was changed in response to dev results.

## Held-out protocol (as executed)
1. Owner approved this file and the freeze commit. **Done.**
2. `git tag -a bench-freeze-v0 ... eb6d95c` (local; pushing the tag needs separate approval). **Done, not pushed.**
3. With a clean tree at the tag: `uv run atrace bench run --split test --confirm-single-test-run`. **Done once**: 2026-11-23T16:59:52Z, exit 0, `git_dirty: false`, logged in `evaluation/TEST_RUNS.log` (one entry).
4. Commit `evaluation/synth_v0-test/` and the log. **Done** in a results-only commit, after the integrity verification below. A rerun is only a reproducibility check and must produce identical canonical files. None has been run.
5. Report test results as-is, including where CF or any baseline is worse than on dev. See `docs/EVALUATION.md` §9.

## Integrity verification before committing the results (2026-11-25)
All checks passed. They used the original fingerprinting code (`agenttrace.trace.fingerprint` at the frozen commit).
- `TEST_RUNS.log` has exactly one entry; its `git_head` is the frozen commit and its `metrics_fp` equals the stored fingerprint.
- Recomputed canonical fingerprints of `metrics.json`, `config.json`, `results.jsonl`, `table.md` and `failure_cases.md` equal `canonical_fingerprints.json`.
- `fingerprint(config.json)` equals the test configuration fingerprint above; `atrace bench config --split test` prints the same value.
- `environment.json`: `git_head` = the frozen commit, `git_dirty: false`; the run ids in the log, `environment.json` and `timings.json` agree.
- Every artifact is byte-identical to the owner's private backup, and the backup's own SHA-256 manifest verifies.
- The tag still resolves to the frozen commit (tag object unchanged).

**Why the raw SHA-256 of `metrics.json` differs from its stored fingerprint.** Canonical artifact fingerprints are `sha256(canonical_bytes(text))`: the file's text is first encoded as a canonical JSON *string* (surrounding quotes, `\n` and `"` escaped), then hashed (see `bench/run.py`). `shasum` hashes the raw bytes instead. Both values are deterministic; they follow different conventions. This is not a mismatch. Example for `metrics.json`: raw `sha256:6498894906cb…`, canonical `sha256:d6792c7cb283…` (stored).

## Post-freeze changes
Recorded in `docs/DECISIONS.md` (ADR-025 onwards) and `CHANGELOG.md`. They do not alter the frozen commit, tag or held-out artifacts.
