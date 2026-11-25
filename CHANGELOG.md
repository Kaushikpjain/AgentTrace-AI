# Changelog

## 0.1.0 (2026-11-25, local release commit; not tagged, not published)

Deterministic MVP. Version 0.1.0 is the frozen 0.1.0rc1 implementation (`bench-freeze-v0` = `eb6d95c`) plus the post-freeze corrections listed below. **The official held-out metrics belong to the frozen 0.1.0rc1 implementation.** The post-freeze code has not been re-evaluated on the held-out split, and no claim is made that it reproduces those metrics. On the development split it reproduces the frozen `metrics.json` and `table.md` byte for byte (ADR-025).

No release has been published and no release tag exists. The proposed tag `v0.1.0` awaits owner approval.

### Added
- **Week 1:**
  - Versioned trace schema (observable trace + privileged ledger), canonical JSON, SHA-256 and semantic fingerprints.
  - JSONL store with atomic writes and integrity validation.
  - Synthetic support environment (5 sandboxed tools).
  - Boundary gateway with the 7-stage tool lifecycle; scripted agent v1/v2; 8 scenario templates; CLI `scenarios`, `run`, `show`.
- **Week 2:**
  - Versioned `FaultPlan` with stage-declared operators (timeout before execution, lost acknowledgement, output corruption, decision replacement).
  - Strict exact replay with fail-closed divergence detection, a configuration check and a fidelity report; `atrace replay`.
- **Week 3:**
  - Operators F1 wrong tool, F2 wrong argument, F4 wrong retrieval, D1 decoy.
  - Counterfactual replay with typed observation/execution replacement, cassette fence and same-type placebos.
  - Regression execution without cassette reuse.
  - Localizers B1, B3, B4, CF with evidence labels.
  - AgentTrace-Synth v0 benchmark (67 validated instances).
  - CLI `inject`, `intervene`, `regress`, `investigate`, `bench generate|verify|list`.
- **Week 4:**
  - Metric A/B/C evaluation with Wilson intervals, template bootstrap and descriptive paired tests.
  - `atrace bench run` with byte-identical canonical outputs and separated volatile metadata; correctness checks.
  - Guarded held-out test command; `atrace bench config`.
  - Makefile, scripted terminal demo, evaluation methodology, walkthrough, release checklist.
  - CI with SHA-pinned actions, a benchmark check and a dependency audit.

### Held-out evaluation (frozen implementation)
- Benchmark freeze `bench-freeze-v0` on `eb6d95c`. The held-out test split was evaluated once (2026-11-23): CF Top-1 22/22, B4 20/22, B1 and B3 10/22 each; repair 22/24; strict replay 37/37; placebo validity 39/39; 0 false repairs. Details are in `docs/EVALUATION.md` §9; artifacts were committed after an integrity check.

### Post-freeze corrections (after `bench-freeze-v0`; not part of the evaluated implementation)
- CF reports `NO_FAILURE` instead of `NOT_ISOLATED` for passing runs (ADR-025).
- Hardened held-out guard: explicit `--approved-commit`, annotated-tag and config-fingerprint checks, refusal of second official runs and overwrites, `--reproducibility-check` (ADR-026).
- `inject`, `investigate` and `intervene` refuse held-out cases without `--allow-held-out`; Python evaluation entry points require a `HeldOutAuthorization`.
- Test-run log entries (schema 2) record command, exit status, commits, config fingerprint, run id, timestamps and artifact fingerprints.

### Known limitations
See README "Limitations" and `docs/EVALUATION.md` §8.
