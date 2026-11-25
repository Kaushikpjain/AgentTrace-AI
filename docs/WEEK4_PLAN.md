# Week 4 Plan: Evaluation, Freeze, Demo and Release Readiness (for approval)

> Status: **COMPLETED (2026-11-23).** CP-T was approved and the held-out split was run once at `bench-freeze-v0` (`eb6d95c`); results were committed on 2026-11-25 (`c684c41`). Run-log and result paths are `evaluation/…`, not `results/…` as drafted below. This plan is kept as the historical record; the current status is in `docs/TASKS.md`.
> Budget: 2–3 h/day on an 8 GB MacBook Air M2. **Committed: 14.5 h implementation + 2 h contingency = 16.5 h** over about 6–7 sessions; **stretch: ~5 h** (deferred first if time runs short).
> Correction: v0.2 of this plan said "~12.5 h". The task estimates summed to 13.5 h and the session table to 14.5 h. W4.7 is raised to 3.0 h (it now also covers the failure-investigation walkthrough), so both totals are 14.5 h.
> Baseline: local commit `ac33265` (Week 3), 306 tests passing, benchmark `synth_v0` (67 instances).

## 0. Starting facts (measured, not assumed)
- Benchmark: 67 instances (CAUSAL 40 = 38 single + 2 MULTI; MASKED 11; CLEAN 8; DECOY_ONLY 8).
  - Dev: 16 CAUSAL single-site + 6 MASKED + 4 CLEAN + 4 DECOY_ONLY.
  - Test: 22 CAUSAL single-site + 2 MULTI + 5 MASKED + 4 CLEAN + 4 DECOY_ONLY.
- Dev preview (Week 3): CF localization of 16 instances took 0.5 s at ~37 MB peak RSS. The full evaluation fits comfortably on 8 GB, so there's no parallelism and no caching layer.
- Small n: the test split has 22 single-site causal cases. All results are reported as k/n with intervals; no percentage appears without its count.

## 1. Tasks

### W4.1 Metrics module (`agenttrace/bench/metrics.py`): 3.0 h
Inputs: localizer `Investigation`s plus labels. This module is the only consumer of labels besides the validator.
- **Metric A (injection-site localization)**, on CAUSAL single-site instances:
  - per method: Top-1, Top-3, MRR;
  - by operator and by symptom distance (0 / ≥1);
  - decoy false-attribution rate (top-1 = decoy seq) on DECOY_PLUS instances;
  - an analytical random reference B0: E[Top-1] = mean of 1/|candidates|.
- **Metric B (interventional repair, CF only):**
  - repair success rate; injected-site repair rate;
  - multiple-repair-site cases, listed;
  - placebo validity rate (must be 1.0; otherwise the run **fails loudly**);
  - unsupported rate by reason; replays per investigation (mean / median / max); intervention-type mix.
- **Metric C (evidence):** label distribution per method; run conclusions (repair sites vs. NOT_ISOLATED), including the MULTI cases (qualitative table).
- **Statistics:**
  - Wilson 95% intervals for proportions.
  - MRR: percentile bootstrap, clustered by template, seed 0, 2,000 resamples (keeps 8 GB runs to seconds; documented).
  - Paired comparisons CF vs. B4, CF vs. B1, B4 vs. B1 on Top-1: exact McNemar (binomial on discordant pairs), Holm-corrected over the 3 comparisons. These are reported as descriptive only, given the small n.
- **Tests:** hand-computed fixtures for every metric; edge cases (n = 0, a site not ranked, ties); bootstrap determinism under the fixed seed; a Wilson check against known values.

### W4.2 `atrace bench run`: 2.0 h
- `atrace bench run --split dev [--methods b1,b3,b4,cf] [--out results/<name>]`.
- Records each instance from `instances.jsonl`. Localizers receive only `Trace` + `support_flags` + `InterventionService`. Metrics then read labels.
- Outputs:
  - `metrics.json`: deterministic, byte-identical across reruns;
  - `table.md`: human-readable A/B/C tables with counts and CIs;
  - `manifest.json`: git SHA and dirty flag, benchmark manifest fingerprint, config fingerprints, Python and package versions, method list, B3 weights, seed;
  - `timings.json`: wall time and peak RSS via `resource.getrusage`. Kept separate because it isn't deterministic.
- `make reproduce-dev`: two runs must give byte-identical `metrics.json` (also a test).
- **Tests:** a CLI smoke run on a 3-instance fixture benchmark; an AST/leakage check of the runner path; determinism.

### W4.3 Correctness and failure-case checks: 2.0 h
- **Structural checks** that run on every `bench run` and abort on violation:
  - placebo validity = 1.0;
  - no `INTERVENTIONAL_REPAIR` on passing runs (CLEAN, DECOY_ONLY and MASKED are investigated as a false-repair control);
  - every recording replays strict-VERIFIED;
  - the benchmark verifies against regeneration.
- **Failure-case gallery** (`failure_cases.md`), generated: every instance where CF top-1 ≠ injection site, every UNSUPPORTED step with its reason, every B4 decoy miss, and the MULTI conclusions. Each links to `atrace investigate` commands.
- **Negative controls:** CF on CLEAN runs must report "no repair possible"; MASKED runs report the outcome PASS and no repair.
- **Honesty checks in `table.md`:** text states that references exist for every step (the scripted agent), that F3/F4 are partly observable, and that n is small.

### W4.4 Dev evaluation and review (DEV ONLY): 1.0 h
- Run `bench run --split dev`. Review A/B/C and the failure cases.
- Any change to localizers, weights or thresholds must be justified by dev results only and recorded in DECISIONS.md *before* the freeze. B3 weights are expected to stay unchanged (ADR-018).

### W4.5 Freeze and held-out test protocol: 1.0 h (+ the single run after approval)
- **Freeze:**
  1. commit everything;
  2. write `docs/FREEZE.md` (git SHA, benchmark manifest fingerprint, methods, weights, seed, stats settings);
  3. create a **local** annotated tag `bench-freeze-v0`. Pushing the tag requires your approval.
- **Test-run guardrails** in `bench run --split test`: the command refuses unless
  - the working tree is clean,
  - HEAD equals `bench-freeze-v0`,
  - `bench verify` passes, and
  - `--confirm-single-test-run` is given.
  
  It appends an entry to `results/TEST_RUNS.log` (timestamp, SHA, metrics fingerprint).
- **CP-T: your explicit approval** is required before the one test run. A rerun is allowed only as a reproducibility check and must produce a byte-identical `metrics.json`. A different result is a bug, not a new result.
- After the run: commit `results/synth_v0-test/` (metrics, table, manifest, failure cases).

### W4.6 Demo and Makefile: 1.5 h
- `Makefile`: `check` (ruff, format, mypy, pytest), `bench-dev`, `reproduce-dev`, `demo`.
- `scripts/demo.sh`: the 3-minute story with fixed instance ids and a temp runs dir:
  1. clean run;
  2. `inject T1-D1+F4`;
  3. `show`;
  4. `replay` (VERIFIED);
  5. `investigate` (B4 fooled by the decoy, CF repair at seq 11);
  6. `intervene` (repair + placebo);
  7. `inject T1-F5`, then `regress --policy v2` (FIXED);
  8. print the frozen results table.
- Recording: asciinema isn't installed. Proposal: you record the terminal with the macOS screen recorder, or I can add `asciinema` as an optional tool (needs your approval). The plan doesn't depend on either.

### W4.7 README, walkthrough and documentation: 3.0 h
- README:
  - a 60-second overview;
  - a Mermaid architecture diagram;
  - quickstart (verified commands only) and "how evaluation works";
  - a **results** section: dev results labelled as development, test results from the frozen run only, every number with k/n and CI;
  - a **limitations** section (§3).
- `docs/EVALUATION.md` (stretch S11 moved here, slimmed): metric definitions, statistics, freeze protocol, file formats.
- Docs pass: TASKS (verification log), TEST_PLAN, DECISIONS (freeze ADR), PRD statuses.

### W4.8 Release readiness: 1.0 h (several items need your decisions)
- Version `0.1.0`, `CHANGELOG.md`.
- CI: pin `actions/checkout` and `astral-sh/setup-uv` to commit SHAs (looked up via the GitHub API). The first real CI run happens on the next push, after your approval.
- Licence: Apache-2.0 recommended. **Not added without approval** (ADR-010).
- `pip-audit` once via `uvx` (network; read-only).
- Release checklist in `docs/RELEASE.md`: tests, verify, reproduce-dev, frozen results present, no research material in the release tree (§4).

### Stretch (only if committed tasks are done): ~5 h
S3 rule-based failure classifier + confusion matrix (2.0) · S4 baseline B2 (0.5) · S8 Rich timeline in `show` (1.5) · S5 LCS alignment in counterfactual reports (1.0).

## 2. Session schedule (focused hours)
| Session | Work | h |
|---|---|---|
| 1 | W4.1 metrics + tests | 3.0 |
| 2 | W4.2 `bench run`, determinism; dev run | 2.5 |
| 3 | W4.3 checks + failure gallery; W4.4 dev review | 2.5 |
| 4 | W4.5 freeze → **CP-T approval** → single test run → commit results | 1.5 |
| 5 | W4.6 demo + Makefile; W4.7 README/EVALUATION | 3.0 |
| 6 | W4.7 remainder (walkthrough); W4.8 release checklist | 2.0 |
| 7 | contingency | 2.0 |
| **Total** | | **14.5 h + 2 h contingency = 16.5 h** |

**Checkpoints:**
- CP-A: metrics tests pass, end of session 1.
- CP-B: `reproduce-dev` byte-identical.
- CP-C: structural checks pass on dev (placebo 1.0, no false repairs).
- **CP-T: your approval before the test run.**
- CP-R: release checklist green.

If CP-B or CP-C fails, the stretch work is dropped and the cause is fixed before any freeze.

## 3. Known limitations to state in the release (honest framing)
1. A synthetic, scripted agent in one domain. Injected faults are not natural LLM failures.
2. Trusted references exist for every step only because the agent is scripted (ADR-017). CF accuracy here is an upper bound for settings where references are available. Real LLM agents mostly yield `UNSUPPORTED`.
3. Some faults are observable (F3 totals, F4 `archived` flag), which helps B1/B3.
4. Small n (22 test single-site cases): wide intervals. Paired tests are descriptive.
5. Single-step interventions cannot isolate jointly sufficient faults (MULTI → NOT_ISOLATED).
6. Probabilistic regression is implemented but unexercised (no stochastic agent yet).
7. The integrity chain is not a security control; localizer isolation is by construction plus tests.

## 4. Repository and disclosure risks (decisions needed)
- **The GitHub repository is PUBLIC** (verified via the GitHub API). `docs/PLAN_v0.2.1.md` and `docs/archive/PLAN_v0.2.md`, both with research and patent-sensitive sections, are publicly visible in commits `58a0c6d` and `9d8cd65`. Options (not executed):
  - (a) make the repo private now (reversible, recommended if the patent route matters);
  - (b) remove the files in a new commit (stops new readers of `main`, history remains);
  - (c) rewrite history and force-push (destructive; does not undo an existing disclosure).
  
  Further notes are kept privately (git-ignored, not in public docs).
- Week 3 commit `ac33265` and this plan (`cee6f50`) were pushed on 2026-11-23 at your request; CI status on GitHub is unverified from this machine.

## 5. Phase 2 roadmap (separate; not part of Week 4)
- **2A Real LLM agent (local, free):**
  - `LocalLLMPolicy` via llama.cpp or Ollama with ≤3B 4-bit models (gate: ≥5 clean runs per dev template; measure success, latency and peak RSS first).
  - JSON-schema-constrained decisions; raw model text in the ledger, parsed decision in the trace.
  - Strict replay of LLM runs without a model (cassette decisions); stochastic regression with Wilson CIs; counterfactuals with k replays per arm.
  - Decision references → UNSUPPORTED unless a gold trajectory exists.
  - About 10–14 h.
- **2B Framework integration:** a minimal LangGraph adapter mapping node and tool calls onto `BoundaryGateway`; record vs. live comparison; one investigation of a real (non-injected) failure with `ground_truth=UNKNOWN`. About 8–10 h.
- **2C Professional frontend:**
  - FastAPI read-only API over `TraceStore`.
  - React + TypeScript viewer: run list, trace timeline with state transitions, original vs. counterfactual diff, an investigation view with evidence labels and placebo results.
  - Runs locally; no database server (SQLite store first).
  - About 15–20 h.
- Later: SQLite/Postgres store, ddmin minimization, regression management, a security/injection suite (AgentDojo), OpenTelemetry export.

## 6. Approvals requested
1. Approve this plan (or adjust scope and hours).
2. Push of `ac33265`, and a separate decision on repository visibility (§4).
3. The CP-T moment for the single held-out test run.
4. Licence choice; optional asciinema install.
