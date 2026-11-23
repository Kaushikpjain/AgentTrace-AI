# Benchmark freeze: AgentTrace-Synth v0 (PROPOSED, not yet approved)

> **Status: PROPOSED.** The freeze tag has **not** been created and the held-out test split has **not** been evaluated. Both require the owner's explicit approval.

## What is frozen
| Item | Value | Recompute with |
|---|---|---|
| Code | the commit carrying this file (tag proposal: `bench-freeze-v0`) | `git rev-parse bench-freeze-v0^{commit}` |
| Benchmark | `benchmarks/synth_v0/` (67 instances; manifest fingerprint in `config.json`) | `uv run atrace bench verify` |
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

## Held-out protocol
1. Owner approves this file and the freeze commit.
2. `git tag -a bench-freeze-v0 -m "AgentTrace-Synth v0 freeze" <commit>` (local; pushing the tag needs separate approval).
3. With a clean tree at the tag: `uv run atrace bench run --split test --confirm-single-test-run`. The command refuses otherwise, and appends to `evaluation/TEST_RUNS.log`.
4. Commit `evaluation/synth_v0-test/` and the log. A rerun is only a reproducibility check and must produce identical canonical files.
5. Report test results as-is, including where CF or any baseline is worse than on dev.
