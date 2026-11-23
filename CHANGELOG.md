# Changelog

## 0.1.0rc1 (unreleased release candidate)

Deterministic MVP. No release has been published.

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

### Known limitations
See README "Limitations" and `docs/EVALUATION.md` §8.
