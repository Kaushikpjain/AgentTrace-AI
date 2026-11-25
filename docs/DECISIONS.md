# Architecture Decision Records

Each ADR is short: context, decision, alternatives, trade-offs, and status. Change an ADR by adding a new one that supersedes it; do not silently edit history.

| ADR | Title | Status |
|---|---|---|
| 001 | Python 3.12 + uv, isolated project environment | Accepted |
| 002 | Modular monolith | Accepted |
| 003 | JSONL/JSON file persistence behind a `TraceStore` protocol | Accepted |
| 004 | Deterministic scripted agent policy for the MVP | Accepted |
| 005 | Explicit replay contracts with state re-application | Accepted |
| 006 | No mandatory paid API; hosted models optional and off by default | Accepted |
| 007 | CLI-first (Typer + Rich), no web stack in the MVP | Accepted |
| 008 | Ids from environment-state counters; no clock/idgen boundaries in the MVP | Accepted |
| 009 | Observable trace vs. privileged execution ledger | Accepted |
| 010 | Research isolation, licensing and disclosure | Accepted (licence choice pending) |
| 011 | Scenario templates shipped as package data | Accepted |
| 012 | Config fingerprint includes policy/tool source hashes | Accepted |
| 013 | Decimal-only money; canonical JSON with normalized Decimals; floats rejected | Accepted |
| 014 | FaultPlan as part of the trace contract; pulled into Week 2 | Accepted |
| 015 | Header included in the integrity hash chain | Accepted |
| 016 | Strict replay serves decisions and re-executes tools; verdicts and exit codes | Accepted |
| 017 | Decision reference = the recorded agent's own fault-free policy version | Accepted |
| 018 | B3 weights fixed a priori; no confidence scores | Accepted |
| 019 | InterventionService as the only privileged channel for localizers | Accepted |
| 020 | Benchmark files committed; instances carry fault plans, labels separate | Accepted |
| 021 | OBSERVATION_REPLACEMENT consistency rule and gateway lifecycle refactor | Accepted |
| 022 | Secondary "same-step action" Top-1 (dev review) | Accepted |
| 023 | Canonical vs. volatile evaluation outputs; guarded held-out split | Accepted |
| 024 | Private notes kept outside version control; 0.1.0rc1 | Accepted |

---

## ADR-001: Python 3.12 + uv
- **Context:** an 8 GB M2 laptop; Homebrew provides Python 3.12.14 and 3.14; uv 0.11 is installed. System Python must not be modified.
- **Decision:** `requires-python = ">=3.12,<3.13"`, with `.python-version = 3.12`. uv creates a project-local `.venv` from the existing Homebrew 3.12 interpreter. Dependencies are locked in `uv.lock`, and dev tools live in a PEP 735 `dev` dependency group.
- **Alternatives:** Python 3.14 (newer, but less library certainty and different CI images); Poetry (slower, extra tool); pip + venv (no lockfile).
- **Trade-offs:** pinning to 3.12 limits language features (no `uuid7` in the stdlib), which is acceptable.

## ADR-002: Modular monolith
- **Decision:** one package `agenttrace` with sub-packages `trace`, `env`, `policies`, `runtime`, `evals`, `cli` (later `replay`, `faults`, `localize`, `bench`, `report`). Dependencies point downward (see ARCHITECTURE.md §3).
- **Alternatives:** separate services (API + workers + UI): no need at this scale, and costly on 8 GB.
- **Trade-offs:** boundaries are enforced by convention plus tests, not by process isolation.

## ADR-003: JSONL persistence behind `TraceStore`
- **Decision:** each run is a directory `runs/<run_id>/` with `header.json`, `events.jsonl`, `ledger.jsonl` and `footer.json`. It is written to a hidden temp directory, then atomically renamed. Loading validates the schema, the hash chain and completeness.
- **Alternatives:** SQLite (queryable, but harder to read and diff, and unneeded at MVP scale); PostgreSQL (needs a server).
- **Trade-offs:** no indexed queries; listing runs is O(#runs). The `TraceStore` protocol allows a SQLite implementation in Level 2 without touching callers.

## ADR-004: Deterministic scripted policy
- **Decision:** the MVP agent is `ScriptedSupportPolicy` (versions `v1` and `v2`), a pure function of (task, observation history). It sits behind the same `decision` boundary an LLM would use. A `ReferencePolicy` interface wraps the gold (`v2`) policy for trusted references.
- **Alternatives:** a small local LLM (stochastic; RAM cost; ground truth unclear); a hosted LLM (cost).
- **Trade-offs:** no real LLM in the MVP, which weakens the GenAI signal. This is mitigated by Phase 2A (local LLM policy) directly after the MVP (PLAN §21).

## ADR-005: Explicit replay contracts with state re-application
- **Decision:** there are four modes, RECORD, REPLAY_STRICT, REPLAY_INTERVENE and REGRESSION, each with its own contract in REPLAY_SPEC.md. Exact replay **re-executes** sandbox tools and verifies state hashes, raw results and delivered responses. It does not simply play back outputs. Cassette lookups are positional and verified with all keys; a cassette fence applies at the intervention point; any mismatch fails closed.
- **Alternatives:** pure playback (cannot reproduce the final state for the oracle); lookup by request hash (can reuse the wrong response after branching).
- **Trade-offs:** tools must be deterministic and re-executable. Non-re-executable tools need the Level 2 `PLAYBACK_WITH_DELTAS` mode with a weaker guarantee.

## ADR-006: No mandatory paid API
- **Decision:** everything in Level 1 runs offline with no LLM. Any hosted model integration (Level 2+) is opt-in (`ATRACE_ALLOW_PAID=1`) and wrapped in a budget guard.

## ADR-007: CLI-first
- **Decision:** a Typer CLI (`atrace`) with Rich output. FastAPI/React come in Phase 2C.
- **Alternatives:** argparse (fewer dependencies, worse ergonomics); a web UI now (too costly).

## ADR-008: Ids from state counters; no clock/idgen boundaries
- **Context:** v0.2 planned `clock` and `idgen` boundaries.
- **Decision:** the support environment derives refund ids from `next_refund_number` in its state, which snapshots/restores and hashes with everything else. It never reads a clock. The `CLOCK` and `IDGEN` boundary kinds remain in the schema enum as reserved values. Run and span ids are generated by `agenttrace.trace.ids` (random UUIDs). They are execution-specific and excluded from semantic fingerprints.
- **Trade-offs:** an environment that needs time later must obtain it through a gateway boundary, which is reserved for that purpose.

## ADR-009: Observable trace vs. execution ledger
- **Context:** correction C2 requires recording raw results and fault applications separately from delivered responses. Correction C3 forbids localizers from seeing ground truth.
- **Decision:** `events.jsonl` (observable: requests, delivered responses, state transitions) is readable by localizers. `ledger.jsonl` (raw outputs, executed flags, fault applications with stage) is privileged: only the replay engine and the benchmark validator read it, via `TraceStore.load_ledger`. Benchmark labels live in a separate `labels.jsonl`.
- **Trade-offs:** state transitions are observable (it is a sandbox whose state can be inspected), so a lost-ack timeout shows `status=timeout` together with `committed=true`. This is realistic: a database log would show the same.

## ADR-010: Research isolation, licensing and disclosure
- **Decision:**
  - This repository holds only the engineering foundation and standard methods. Speculative research algorithms go in a separate private repository.
  - **No licence file is added yet**, and the `Private :: Do Not Upload` classifier blocks accidental PyPI upload.
  - Nothing is pushed or published without explicit approval.
  - The recommended future licence for the public foundation is Apache-2.0, pending approval and IPR-cell input.
  - `docs/PLAN_v0.2.1.md` §22 and `docs/archive/` contain research-sensitive planning material. **Before any public release they must be removed from the tree and from git history** (or never committed).
- **Note:** neither withholding publication nor choosing a licence creates patent rights.

## ADR-011: Scenario templates as package data
- **Decision:** clean scenario templates are JSON files inside `agenttrace/env/support/scenarios/`, loaded via `importlib.resources`, so the CLI works from any working directory. Generated benchmark instances (Week 3) go under `benchmarks/`.

## ADR-012: Config fingerprint covers source code
- **Decision:** `AgentRef.source_hash` = sha256 of the policy module source; the tool-manifest hash covers tool names, mutating flags, argument JSON schemas and the tools module source. Changing agent or tool code therefore changes the config fingerprint, so REPLAY_STRICT refuses with `CONFIG_MISMATCH` (REPLAY_SPEC §8).
- **Trade-offs:** comment-only edits also change the hash. This is deliberate: it is conservative and fails closed.

## ADR-013: Money and canonical JSON
- **Decision:** money is `Decimal`, quantized to 2 places in the environment models. Canonical JSON:
  - Decimals become their normalized plain string (`80.00` → `"80"`); NaN and infinity are rejected.
  - Floats are rejected.
  - Keys are sorted, with compact separators, UTF-8, and strings NFC-normalized.
  - Event payloads are converted to JSON-pure values at record time, so stored and reloaded events are equal.
- **Trade-offs:** stored money strings lose trailing zeros (`"80"`). Readability suffers a little in exchange for semantic equality.

## ADR-014: FaultPlan as part of the trace contract (Week 2)
- **Context:** strict replay must re-apply the faults of a recorded run (tests #9, #16, #21). Ad-hoc Python hooks cannot be reconstructed from a recording.
- **Decision:** a versioned, serializable `FaultPlan` (TRACE_SCHEMA §3) is stored as privileged `fault_plan.json`; its fingerprint is `header.fault_plan_hash` and enters the config fingerprint. `PlanFaultHook` is stateless (matches on gateway-provided occurrences), so RECORD and REPLAY behave identically. Operators are registered with a declared stage; unknown operators or stage mismatches are rejected (`FaultPlanError`). T0, F3, F5 and `REPLACE_DECISION` were pulled forward from Week 3; F1, F2, F4 and D1 remain Week 3.
- **Trade-offs:** `RunRecord` now requires a matching plan whenever the header has a fault-plan hash, so arbitrary Python hooks can no longer produce records (they remain usable for gateway-level unit tests).

## ADR-015: Header in the hash chain
- **Context:** the Week 1 chain covered events and ledger only; a self-consistent header edit (e.g. a different fault-plan hash with a recomputed config fingerprint) would pass load validation.
- **Decision:** the chain now starts with the canonical header. The fault plan is covered transitively via `fault_plan_hash`. The footer remains unchained (it holds the root); strict replay re-derives its status, outcome and final state.
- **Trade-offs:** recordings written before this change fail integrity checks. None were kept (pre-release).

## ADR-016: Strict replay semantics, verdicts and exit codes
- **Decision:** strict replay serves decisions from the cassette (the policy is replaced by a guard that raises on use) and re-executes sandbox tools, verifying raw result + fault applications, then state transition, then delivered response. The result is a `ReplayReport` with verdict `VERIFIED` / `DIVERGED` / `CONFIG_MISMATCH` / `INTEGRITY_ERROR`. `atrace replay` exits 0 / 1 / 3 / 4 respectively (2 = usage / not found).
- **Known limit:** a decision payload altered without affecting later tool requests cannot be detected by replay alone; the integrity chain catches it at load (REPLAY_SPEC §5.2).

## ADR-017: Decision reference = the recorded agent's own fault-free policy
- **Context:** the gold reference was hard-wired to v2. Every v1 refund decision differs from v2 (no idempotency key), so references would flag non-injected steps everywhere.
- **Decision:** `REFERENCE_POLICY` for a run is the reference registered for the *recorded* agent (`GoldSupportReference(version)`). Injected decision faults are then the only decision deviations.
- **Trade-offs / limits:** this is possible only because the agent is scripted. A latent agent bug (e.g. v1's missing idempotency key) is *not* a deviation under this reference; it is found through environment-fault interventions and regression instead. LLM agents will have no such reference (→ UNSUPPORTED).

## ADR-018: B3 weights fixed a priori
- **Decision:** B3 score = 2·[on the symptom's argument-origin chain] + 3·[validator flag] + 1·[delivered ERROR/TIMEOUT] + 1·[committed a state change]; ties earliest-first. These values were fixed before any benchmark run and are never tuned on the test split. Scores are integers for ranking only. No confidence scores or causal probabilities are reported, because no measurement method for them is defined.

## ADR-019: InterventionService
- **Decision:** B4 and CF receive an `InterventionService` bound to the privileged record. It exposes only `trace`, `reference_deviation(seq)`, `experiment(seq)` and `replays_used`. Summaries contain statuses, outcomes and booleans, never the counterfactual runs, because their ledgers would reveal fault applications. This is enforced by an AST test and an attribute test. Python cannot make the record truly inaccessible; the guarantee is by construction plus tests.

## ADR-020: Benchmark files
- **Decision:** `benchmarks/synth_v0/` is committed and must equal a deterministic regeneration (`atrace bench verify`, also a test). `instances.jsonl` contains each instance's fault plan, which is needed to *record* it. Localizers never see it: they receive the recorded observable `Trace` only. `labels.jsonl` is privileged.
- **Trade-offs:** fault plans in `instances.jsonl` reveal the injected operator to a human reader; the evaluation boundary is the localizer API, not file secrecy.

## ADR-021: Gateway lifecycle refactor; observation consistency rule
- **Decision:** stages S1–S4 became a pure `BoundaryGateway.lifecycle(name, args, ctx, hook, state)` that returns the resulting state without installing it. New seams: `_tool_hook(seq)`, `_transform_delivered(...)`, `_is_intervened(seq)`. All Week 1–2 tests pass unchanged. `OBSERVATION_REPLACEMENT` with `REFERENCE_TOOL` is refused (`observation_inconsistent_with_state`) whenever the reference execution's `(committed, after_hash)` differs from the original's.

## ADR-022: Secondary "same-step action" Top-1 (dev review, before freeze)
- **Context:** on dev, B1/B3 missed every F1/F2 instance under strict matching. In each case they ranked the tool call issued by the faulty decision (seq site+1, same step). By design they flag visible errors, not decisions.
- **Decision:** keep the strict site match as the **primary** Metric A. Add a secondary Top-1 in which a DECISION site also counts when its own tool call is ranked first. No localizer, weight or benchmark instance was changed.
- **Trade-offs:** the secondary metric is lenient towards observation-based baselines. Reporting both avoids hiding either the off-by-one effect or the strict result.

## ADR-023: Evaluation outputs and the held-out guard
- **Decision:** canonical outputs (`metrics.json`, `config.json`, `results.jsonl`, `table.md`, `failure_cases.md`, `canonical_fingerprints.json`) contain no timestamps, run ids, git state or timings, and must be byte-identical across reruns. Volatile metadata goes to `environment.json` and `timings.json`. `bench run --split test` refuses unless the tree is clean, HEAD equals `bench-freeze-v0` and `--confirm-single-test-run` is given. Each test run is appended to `evaluation/TEST_RUNS.log`. Evaluation outputs live in the tracked `evaluation/` directory (`runs/` and `results/` stay ignored).
- **Fingerprint convention (clarified 2026-11-25):** a canonical artifact fingerprint is `sha256(canonical_bytes(text))`, i.e. the file text encoded as a canonical JSON string, then hashed. It intentionally differs from `shasum` of the raw file; verification must use `agenttrace.trace.fingerprint`.

## ADR-024: Private notes and versioning
- **Decision:** the owner's private notes live in a git-ignored `private/` directory and are never referenced by public docs. The package version is `0.1.0rc1` until the owner approves the release. No licence file is added (ADR-010).

## ADR-025: `NO_FAILURE` conclusion for passing runs (post-freeze, 2026-11-25)
- **Context:** CF reported `NOT_ISOLATED` for every run without a repair site, including runs that *passed* (14 dev and 13 test runs). For a passing run that wording implies an unresolved failure.
- **Decision:** CF's run conclusion is now `repair sites: …` if any step repairs the run; otherwise `NOT_ISOLATED` (failed run), `NO_FAILURE` (passing run) or `NOT_EVALUATED` (no oracle verdict). Step labels, rankings, experiments and the false-repair check are unchanged. Baseline conclusions are unchanged.
- **Effect:** `make reproduce-dev` still produces byte-identical outputs across reruns. Against the committed freeze-time dev artifacts, `metrics.json`, `table.md` and `failure_cases.md` are identical; `results.jsonl` differs only in the CF `conclusion` of the 14 passing runs. The committed held-out artifacts keep the frozen wording.

## ADR-026: Hardened held-out guard and entry-point safeguards (post-freeze, 2026-11-25)
- **Context:** the frozen guard required only a clean tree, HEAD == the tag and a confirmation flag. Tags are movable. Other entry points (`inject`, `investigate`, `intervene`, Python `evaluate_split`/`run_benchmark`) could touch held-out cases without any guard. The run log recorded only time, commit, metrics fingerprint and run id.
- **Decision (`agenttrace.bench.heldout`):**
  - `bench run --split test` requires `--approved-commit <40-hex>` and `--confirm-single-test-run`. The annotated freeze tag must resolve to the approved commit and HEAD must equal it; the tree must be clean.
  - The config fingerprint must equal the recorded freeze (`KNOWN_FREEZES`; for future freezes, the fingerprint in the annotated tag message).
  - A second run for an evaluated commit is refused unless it is a `--reproducibility-check` into a new, separate `--out`. Official artifacts are never overwritten.
  - Python entry points refuse the test split without a `HeldOutAuthorization` minted by `authorize_test_split`.
  - `inject`, `investigate` and `intervene` refuse held-out (test-split) cases unless `--allow-held-out` is given.
  - Each authorized run appends a log entry with `log_schema` 2: kind, command, exit status, started/finished, git head and dirty flag, approved commit, tag, config fingerprint, run id, output directory and all artifact fingerprints. The entry is written even when the run fails. The original entry is never rewritten.
- **Scope:** these are operational safeguards against accidental use, not a security boundary. Benchmark generation and `bench verify` still record all instances, which label validation requires. `run` and `regress` are not guarded. Tests that exercise replay mechanics on T5–T8 scenarios do not evaluate the benchmark.
- **Consequence:** at any post-freeze HEAD the guard refuses the test split. A reproducibility check of the official result must run at `bench-freeze-v0`, i.e. with the frozen code and its frozen guard.

## ADR-027: Version 0.1.0 (2026-11-25)
- **Decision:** the owner authorised preparing 0.1.0 after full release verification. The version is set to `0.1.0` in `pyproject.toml`, `agenttrace.__version__` and `uv.lock`, in a local commit. The benchmark config fingerprints are unchanged by the bump (test `sha256:7a37fd81…`, dev `sha256:6dab492e…`).
- **Attribution of results:** the official held-out metrics belong to the frozen 0.1.0rc1 implementation (`bench-freeze-v0`). Post-freeze changes (ADR-025, ADR-026) are recorded separately and have not been evaluated on the held-out split.
- **Not done without approval:** the `v0.1.0` tag, any push, a GitHub release, a licence (ADR-010), and visibility changes.
