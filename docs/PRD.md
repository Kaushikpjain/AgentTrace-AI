# Product Requirements: AgentTrace AI (Level 1 MVP)

## 1. Vision
AgentTrace AI is a reliability, security-testing and failure-diagnosis platform for tool-using AI agents. It helps an engineer answer: *Why did my agent fail, can I reproduce it exactly, which step is responsible (and how strong is that evidence), and does my fix actually work?*

## 2. Target users
| User | Need |
|---|---|
| Agent developer | Reproduce a failing run exactly; test a fix without being fooled by replayed responses |
| Evaluation / reliability engineer | Benchmark failure localization against known ground truth, with honest metrics |
| Reviewer / interviewer | A small system whose correctness claims are backed by executable tests |

## 3. User stories (MVP)
- **US1:** As a developer, I run a scenario and see each decision and tool call, the state changes, and a pass/fail verdict with the violated clauses.
- **US2:** As a developer, every run is persisted as an immutable, validated trace that I can inspect later from the CLI.
- **US3:** As a developer, I replay a recorded run exactly. I either get the same final state and outcome, or a precise report of the first divergence.
- **US4:** As a developer, I replace one step's output, or its execution, with a trusted reference and see whether the outcome changes, with a placebo control.
- **US5:** As a developer, I run a changed agent against the same scenario and fixture, and the tool guarantees it executed fresh (no recorded responses).
- **US6:** As an evaluator, I inject controlled faults with known locations and measure localization (Metric A), repair (Metric B) and evidence (Metric C) separately.

## 4. Functional requirements
| ID | Requirement | Week |
|---|---|---|
| FR1 | Synthetic support environment with 5 sandboxed tools; Decimal money; deterministic ids; atomic commits; idempotency; audit | 1 |
| FR2 | Deterministic scripted agent (v1, v2) behind a decision boundary; max-step guard | 1 |
| FR3 | Declarative, versioned scenarios (≥5 committed templates) with a deterministic oracle | 1 |
| FR4 | Versioned trace schema; canonical JSON; fingerprints; observable trace + privileged ledger | 1 |
| FR5 | JSONL store with atomic writes, validation, integrity chain, corruption/incomplete detection | 1 |
| FR6 | CLI: `scenarios`, `run`, `show` | 1 |
| FR7 | REPLAY_STRICT with divergence detection and a fidelity report (**implemented, Week 2**) | 2 |
| FR8 | Fault layer with stage-declared operators F1–F5, decoy D1, T0 fixture (**implemented**: T0/F3/F5 in Week 2; F1, F2, F4, D1 in Week 3) | 2–3 |
| FR9 | REPLAY_INTERVENE with observation/execution replacement, same-type placebo, UNSUPPORTED results (**implemented**) | 3 |
| FR10 | REGRESSION execution without cassette access (**implemented**) | 3 |
| FR11 | Baselines B1, B3, B4 and a CF localizer with evidence labels (**implemented**) | 3 |
| FR12 | Benchmark generation + label validation (**implemented, Week 3**) + Metric A/B/C report (**implemented, Week 4**), reproducible with one command (`make reproduce-dev`) | 3–4 |

## 5. Non-functional requirements
| ID | Requirement |
|---|---|
| NFR1 | Runs on a MacBook Air M2 with 8 GB RAM alongside an IDE; no Docker, DB server, GPU or LLM in Level 1 |
| NFR2 | No paid API; no network access required at runtime; no real external side effects |
| NFR3 | Determinism: repeated runs of the same configuration have equal semantic fingerprints |
| NFR4 | Fail-closed replay: never silently fall back to live execution |
| NFR5 | Minimal dependencies (runtime: pydantic, typer, rich) |
| NFR6 | Quality: ruff and mypy (strict) clean; pytest green; CI config included |
| NFR7 | No fabricated results: every reported number comes from an executed command |

## 6. MVP scope
The committed scope is 50 h + ≥6 h debugging (PLAN_v0.2.1 §17): FR1–FR12. Stretch: PLAN_v0.2.1 §18.

## 7. Out of scope (Level 1)
React/FastAPI, PostgreSQL/Redis/Docker, LangGraph, OpenTelemetry ingestion, AgentDojo, injection suites, LLM-as-judge, any LLM inference, multi-agent systems, RBAC, hosted deployment, adaptive replay allocation, ddmin minimization, automated test generation, large benchmarks.

## 8. Acceptance criteria
- **Week 1 (CP1):** quality gates in TEST_PLAN.md §8.
- **MVP:** checkpoints CP1–CP5 (PLAN_v0.2.1 §19), acceptance tests #1–#21 passing, and `make reproduce` regenerating the Metric A/B/C tables identically.
