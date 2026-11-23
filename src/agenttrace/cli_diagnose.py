"""Week 3 CLI commands: inject, intervene, regress, investigate, bench.

Registered on the main ``atrace`` app (imported at the end of ``agenttrace.cli``).

Exit codes:
- ``intervene``: 0 completed (see output for repair/placebo), 2 usage / not found,
  3 CONFIG_MISMATCH, 5 UNSUPPORTED, 6 INVALID_COUNTERFACTUAL.
- ``regress``: 0 candidate deterministic PASS, 1 otherwise, 3 CONFIG_ERROR.
- ``investigate``: 0 ok, 2 usage / not found.
- ``bench verify``: 0 files match a fresh regeneration, 1 otherwise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table

from agenttrace.bench.io import DEFAULT_DIR, build_benchmark, load_instances, verify_benchmark
from agenttrace.cli import RunsDir, _print_trace, _store, app, console
from agenttrace.env.support.scenario import load_scenario
from agenttrace.evals.validators import support_flags
from agenttrace.localize.baselines import rank_b1, rank_b3, rank_b4
from agenttrace.localize.counterfactual import rank_cf
from agenttrace.localize.report import render_markdown
from agenttrace.localize.types import Investigation
from agenttrace.replay.counterfactual import (
    CounterfactualResult,
    CounterfactualStatus,
    InterventionRequest,
    run_experiment,
)
from agenttrace.replay.regression import RegressionVerdict, regression_from_store
from agenttrace.replay.service import InterventionService
from agenttrace.runner import record_scenario, support_replay_context
from agenttrace.trace.schema import (
    Boundary,
    FaultPlan,
    InterventionType,
    Outcome,
    ReferenceSource,
    RunRecord,
)
from agenttrace.trace.store import RunNotFoundError, TraceStoreError

bench_app = typer.Typer(help="Synthetic benchmark: generate and verify (labels stay private).")
app.add_typer(bench_app, name="bench")

BenchDir = Annotated[Path, typer.Option("--bench-dir", help="Benchmark directory")]


def _load(run_id: str, runs_dir: Path | None) -> RunRecord:
    """Load a stored run (privileged; the CLI itself is a trusted operator tool)."""
    try:
        return _store(runs_dir).load_record(run_id)
    except (RunNotFoundError, TraceStoreError) as exc:
        console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
        raise typer.Exit(2) from exc


# ---------------------------------------------------------------- inject
@app.command("inject")
def inject_cmd(
    instance_id: Annotated[str, typer.Argument(help="Benchmark instance id, e.g. T1-F4")],
    runs_dir: RunsDir = None,
    bench_dir: BenchDir = DEFAULT_DIR,
) -> None:
    """Record a benchmark instance (scenario + its fault plan) and save the trace."""
    instances = {i["instance_id"]: i for i in load_instances(bench_dir)}
    instance = instances.get(instance_id)
    if instance is None:
        console.print(f"[red]unknown instance {instance_id!r}; see `atrace bench list`[/red]")
        raise typer.Exit(2)
    plan = FaultPlan.model_validate(instance["fault_plan"]) if instance["fault_plan"] else None
    record = record_scenario(
        load_scenario(instance["scenario_id"]),
        policy_version=instance["policy_version"],
        fault_plan=plan,
    )
    store = _store(runs_dir)
    store.save(record)
    _print_trace(record.observable(), saved_to=store.root / record.header.run_id)
    raise typer.Exit(0 if record.footer.outcome.outcome is Outcome.PASS else 1)


# ---------------------------------------------------------------- intervene
def _status_text(result: CounterfactualResult) -> str:
    if result.status is CounterfactualStatus.COMPLETED:
        assert result.outcome is not None
        return f"COMPLETED → {result.outcome.value}"
    return f"{result.status.value} ({result.reason})"


@app.command("intervene")
def intervene_cmd(
    run_id: Annotated[str, typer.Argument(help="Recorded run to intervene on")],
    seq: Annotated[int, typer.Option("--seq", help="Target event seq (DECISION or TOOL)")],
    kind: Annotated[str, typer.Option("--type", help="observation | execution")] = "execution",
    source: Annotated[
        str, typer.Option("--source", help="reference | original (placebo only)")
    ] = "reference",
    runs_dir: RunsDir = None,
    save: Annotated[bool, typer.Option("--save", help="Persist the counterfactual runs")] = False,
) -> None:
    """Counterfactual replay at one step, always paired with a same-type placebo."""
    if kind not in ("observation", "execution") or source not in ("reference", "original"):
        console.print(
            "[red]--type must be observation|execution, --source reference|original[/red]"
        )
        raise typer.Exit(2)
    record = _load(run_id, runs_dir)
    events = {e.seq: e for e in record.events}
    target = events.get(seq)
    itype = (
        InterventionType.OBSERVATION_REPLACEMENT
        if kind == "observation"
        else InterventionType.EXECUTION_REPLACEMENT
    )
    if source == "original":
        ref = ReferenceSource.ORIGINAL
    elif target is not None and target.boundary is Boundary.DECISION:
        ref = ReferenceSource.REFERENCE_POLICY
    else:
        ref = ReferenceSource.REFERENCE_TOOL
    request = InterventionRequest(seq, itype, ref, f"cli: {kind} replacement from {source}")
    result = run_experiment(record, support_replay_context(), request)
    main, placebo = result.intervention, result.placebo

    console.print(
        f"[bold]Counterfactual on {run_id}[/bold] at seq {seq} "
        f"({result.target_logical_key or 'invalid target'}): {itype.value} · source {ref.value}"
    )
    table = Table()
    for column in ("run", "status / outcome", "cassette after fence"):
        table.add_column(column)
    table.add_row("original", record.footer.outcome.outcome.value, "-")
    table.add_row("intervention", _status_text(main), str(main.cassette_accesses_after_fence))
    table.add_row(
        "placebo (same type, original value)",
        _status_text(placebo),
        str(placebo.cassette_accesses_after_fence),
    )
    console.print(table)
    if main.status is not CounterfactualStatus.COMPLETED:
        console.print(f"  [red]{main.status.value}: {main.reason}[/red] (no outcome is reported)")
    if main.status is CounterfactualStatus.COMPLETED:
        console.print(
            f"  repair observed: {'yes' if result.repair_observed else 'no'}; "
            f"placebo valid: {'yes' if result.placebo_valid else 'no'}"
        )
        label = (
            "INTERVENTIONAL_REPAIR (sufficient to repair this run; not proof of a unique cause)"
            if result.interventional_repair
            else "no interventional repair evidence"
        )
        console.print(f"  evidence: [bold]{label}[/bold]")
    if save:
        store = _store(runs_dir)
        for item in (main, placebo):
            if item.run is not None:
                store.save(item.run)
                console.print(f"[dim]saved {item.run.header.run_id}[/dim]")
    codes = {
        CounterfactualStatus.COMPLETED: 0,
        CounterfactualStatus.CONFIG_MISMATCH: 3,
        CounterfactualStatus.UNSUPPORTED: 5,
        CounterfactualStatus.INVALID_COUNTERFACTUAL: 6,
    }
    raise typer.Exit(codes[main.status])


# ---------------------------------------------------------------- regress
@app.command("regress")
def regress_cmd(
    run_id: Annotated[str, typer.Argument(help="Baseline run (its scenario + env fixture)")],
    policy: Annotated[str, typer.Option("--policy", help="Candidate policy version")],
    repeats: Annotated[int, typer.Option("--repeats", min=1, max=20)] = 2,
    runs_dir: RunsDir = None,
) -> None:
    """Execute a candidate agent freshly (no cassette) and compare with the baseline."""
    try:
        report = regression_from_store(
            _store(runs_dir),
            run_id,
            support_replay_context(),
            policy_version=policy,
            repeats=repeats,
        )
    except (RunNotFoundError, TraceStoreError) as exc:
        console.print(f"[red]{type(exc).__name__}: {exc}[/red]")
        raise typer.Exit(2) from exc
    console.print(f"[bold]Regression of {run_id}[/bold] with candidate policy {policy}")
    if report.verdict is RegressionVerdict.CONFIG_ERROR:
        console.print(f"[red]CONFIG_ERROR: {report.detail}[/red]")
        raise typer.Exit(3)
    console.print(f"  baseline outcome: {report.baseline_outcome.value}")
    console.print(
        f"  candidate: {report.passes}/{report.n} fresh runs PASS; verdict "
        f"[bold]{report.verdict.value}[/bold]; comparison [bold]{report.comparison.value}[/bold]"
    )
    console.print(f"  deterministic reproduction across runs: {report.deterministic_reproduced}")
    for diff in report.config_differences:
        console.print(f"  config difference: {diff}")
    for fault in report.dropped_decision_faults:
        console.print(f"  dropped DECISION-stage fault (agent error, not environment): {fault}")
    console.print("  [dim]no cassette used; no recorded decision reused[/dim]")
    raise typer.Exit(0 if report.verdict is RegressionVerdict.DETERMINISTIC_PASS else 1)


# ---------------------------------------------------------------- investigate
def _print_investigation(inv: Investigation, limit: int) -> None:
    table = Table(title=f"{inv.method}: {inv.conclusion} (replays: {inv.replays_used})")
    for column in ("rank", "seq", "step", "label", "score", "flags", "reference", "experiment"):
        table.add_column(column, overflow="fold")
    for rank, step in enumerate(inv.ranking[:limit], start=1):
        exp = step.experiment
        experiment = "-"
        if exp is not None:
            outcome = (
                exp.intervention_outcome.value
                if exp.intervention_outcome
                else exp.intervention_status.value
            )
            placebo = exp.placebo_outcome.value if exp.placebo_outcome else "-"
            experiment = (
                f"int→{outcome}, placebo→{placebo}{'' if exp.placebo_valid else ' (invalid)'}"
            )
        table.add_row(
            str(rank),
            str(step.seq),
            step.logical_key,
            step.label.value,
            str(step.score),
            ", ".join(step.flags) or "-",
            step.reference or "-",
            experiment + (f" {step.note}" if step.note else ""),
        )
    console.print(table)


@app.command("investigate")
def investigate_cmd(
    run_id: Annotated[str, typer.Argument(help="Run to investigate (normally a failed run)")],
    methods: Annotated[
        str, typer.Option("--methods", help="Comma list of b1,b3,b4,cf")
    ] = "b1,b3,b4,cf",
    runs_dir: RunsDir = None,
    markdown: Annotated[
        Path | None, typer.Option("--markdown", help="Write a Markdown report")
    ] = None,
    top: Annotated[int, typer.Option("--top", min=1)] = 5,
) -> None:
    """Rank suspicious steps with baselines and the placebo-controlled counterfactual localizer."""
    wanted = [m.strip().lower() for m in methods.split(",") if m.strip()]
    unknown = set(wanted) - {"b1", "b3", "b4", "cf"}
    if unknown or not wanted:
        console.print(f"[red]unknown methods {sorted(unknown)}[/red]")
        raise typer.Exit(2)
    record = _load(run_id, runs_dir)
    trace = record.observable()  # localizers only ever see this ...
    flags = support_flags(trace)
    ctx = support_replay_context()
    investigations: list[Investigation] = []
    for method in wanted:
        if method == "b1":
            investigations.append(rank_b1(trace, flags))
        elif method == "b3":
            investigations.append(rank_b3(trace, flags))
        elif method == "b4":
            investigations.append(rank_b4(InterventionService(record, ctx), flags))  # ... and this
        else:
            investigations.append(rank_cf(InterventionService(record, ctx), flags))
    console.print(
        f"[bold]Investigation of {run_id}[/bold]: oracle {record.footer.outcome.outcome.value}, "
        f"symptom seq {investigations[0].symptom_seq}"
    )
    for inv in investigations:
        _print_investigation(inv, top)
    console.print(
        "[dim]INTERVENTIONAL_REPAIR = sufficient to repair this run with a valid placebo; "
        "not proof of a unique cause.[/dim]"
    )
    if markdown is not None:
        markdown.write_text(render_markdown(trace, investigations), encoding="utf-8")
        console.print(f"[dim]report written to {markdown}[/dim]")


# ---------------------------------------------------------------- bench
@bench_app.command("generate")
def bench_generate(bench_dir: BenchDir = DEFAULT_DIR) -> None:
    """Generate and validate AgentTrace-Synth v0 into the benchmark directory."""
    from agenttrace.bench.io import write_benchmark

    result = build_benchmark(support_replay_context())
    write_benchmark(result, bench_dir)
    counts: dict[str, Any] = result.manifest["counts"]
    console.print(
        f"wrote {counts['instances']} instances ({counts['rejected']} rejected) to {bench_dir}"
    )
    console.print(f"by label: {counts['by_label']}")


@bench_app.command("verify")
def bench_verify(bench_dir: BenchDir = DEFAULT_DIR) -> None:
    """Regenerate deterministically and check the files on disk are identical."""
    problems = verify_benchmark(support_replay_context(), bench_dir)
    if problems:
        for problem in problems:
            console.print(f"[red]✗ {problem}[/red]")
        raise typer.Exit(1)
    console.print("[green]✓ benchmark files match a fresh deterministic regeneration[/green]")


@bench_app.command("list")
def bench_list(
    bench_dir: BenchDir = DEFAULT_DIR,
    split: Annotated[str | None, typer.Option("--split", help="dev | test")] = None,
) -> None:
    """List instance ids (labels are private and are not shown)."""
    table = Table(title="Benchmark instances (labels hidden)")
    for column in ("instance", "scenario", "split", "kind"):
        table.add_column(column)
    for instance in load_instances(bench_dir):
        if split and instance["split"] != split:
            continue
        table.add_row(
            instance["instance_id"], instance["scenario_id"], instance["split"], instance["kind"]
        )
    console.print(table)
