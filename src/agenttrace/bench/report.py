"""Deterministic human-readable outputs: table.md and failure_cases.md."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def _p(prop: dict[str, Any] | None) -> str:
    if not prop or prop.get("n") in (None, 0):
        return "n/a (n=0)"
    ci = prop["ci95"]
    return f"{prop['k']}/{prop['n']} = {prop['rate']} [{ci[0]}, {ci[1]}]"


def render_table(metrics: dict[str, Any], config: dict[str, Any]) -> str:
    pop = metrics["population"]
    a = metrics["metric_a"]
    lines = [
        f"# AgentTrace-Synth {config['benchmark_version']}: split `{config['split']}`",
        "",
        f"Instances: {pop['instances']} {pop['by_label']}. Eligible for Metric A: "
        f"**{pop['eligible_for_metric_a']}** ({pop['eligibility']}).",
        "",
        "> Injection-site localization measures whether a method ranks the *step where the fault "
        "was injected* first. It is not unique causal attribution. Rates show k/n = rate "
        "[Wilson 95% CI]; MRR intervals are cluster (template) bootstrap. Small n: intervals are "
        "wide and the paired tests are descriptive only. MRR intervals resample templates; with "
        "only 4 templates per split they are coarse and can be degenerate.",
        "",
        "> *Secondary* same-step action match: a DECISION injection site also counts when its own "
        "tool call is ranked first (that call is the decision's first visible effect). "
        "Added during the dev review; the strict site match is the primary metric.",
        "",
        "## Metric A: injection-site localization",
        "",
        "| method | Top-1 (primary) | Top-3 | MRR [95% CI] | Top-1 same-step action (secondary) "
        "| not ranked | decoy false attribution |",
        "|---|---|---|---|---|---|---|",
    ]
    for method, m in a["by_method"].items():
        mrr = m["mrr"]
        ci = mrr["ci95_cluster_bootstrap"]
        mrr_text = f"{mrr['value']} [{ci[0]}, {ci[1]}]" if ci else "n/a"
        lines.append(
            f"| {method} | {_p(m['top1'])} | {_p(m['top3'])} | {mrr_text} | "
            f"{_p(m['top1_same_step_action'])} | "
            f"{m['injection_site_not_ranked']} | {_p(m['decoy_false_attribution'])} |"
        )
    b0 = a["random_reference_B0"]
    if b0.get("n"):
        lines.append(
            f"| B0 (random, analytical) | E = {b0['expected_top1']} | E = {b0['expected_top3']} | "
            f"E = {b0['expected_mrr']} | - | - | - |"
        )
    lines += [
        "",
        "### Top-1 by fault operator",
        "",
        "| operator | " + " | ".join(a["by_method"]) + " |",
        "|---|" + "---|" * len(a["by_method"]),
    ]
    operators = sorted({op for m in a["by_method"].values() for op in m["by_operator"]})
    for op in operators:
        cells = [_p(m["by_operator"].get(op, {}).get("top1")) for m in a["by_method"].values()]
        lines.append(f"| {op} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "### Top-1 by symptom distance (tool calls between injection and visible symptom)",
        "",
        "| distance | " + " | ".join(a["by_method"]) + " |",
        "|---|" + "---|" * len(a["by_method"]),
    ]
    buckets = sorted({b for m in a["by_method"].values() for b in m["by_symptom_distance"]})
    for bucket in buckets:
        cells = [
            _p(m["by_symptom_distance"].get(bucket, {}).get("top1"))
            for m in a["by_method"].values()
        ]
        lines.append(f"| {bucket} | " + " | ".join(cells) + " |")
    paired = a["paired_top1"]
    lines += [
        "",
        f"### Paired Top-1 comparisons ({paired['test']}; {paired['interpretation']})",
        "",
        "| comparison | only first correct | only second correct | n | p exact | p Holm |",
        "|---|---|---|---|---|---|",
    ]
    for name, row in paired["comparisons"].items():
        lines.append(
            f"| {name} | {row['only_first_correct']} | {row['only_second_correct']} | "
            f"{row['n']} | {row['p_exact']} | {row['p_holm']} |"
        )
    b = metrics.get("metric_b")
    if b:
        lines += [
            "",
            "## Metric B: interventional repair (CF)",
            "",
            "- Repair success (CAUSAL runs with ≥1 INTERVENTIONAL_REPAIR): "
            f"{_p(b['repair_success'])}",
            f"- Injected site itself repaired (eligible): {_p(b['injected_site_repaired'])}",
            "- Placebo validity (completed placebos reproducing the original): "
            f"{_p(b['placebo_validity'])}; placebos not completed: {b['placebo_not_completed']}",
            f"- Experiments: {b['experiments']['total']} by status "
            f"{b['experiments']['by_status']}, by type {b['experiments']['by_type']}",
            f"- UNSUPPORTED steps: {_p(b['unsupported_steps'])}; "
            f"by reason {b['unsupported_by_reason']}",
            f"- Runs with multiple repair sites: {b['multiple_repair_sites']['count']} "
            f"{b['multiple_repair_sites']['instances']}",
        ]
        for case in b["multi_fault_cases"]:
            lines.append(f"- Multi-fault `{case['instance_id']}`: {case['conclusion']}")
    lines += [
        "",
        "## Metric C: diagnostic evidence",
        "",
        "| method | SUSPICION | REFERENCE_DEVIATION | INTERVENTIONAL_REPAIR | UNSUPPORTED | "
        "run conclusions (all CAUSAL) |",
        "|---|---|---|---|---|---|",
    ]
    for method, c in metrics["metric_c"].items():
        labels = c["step_labels_on_eligible"]
        lines.append(
            f"| {method} | {labels['SUSPICION']} | {labels['REFERENCE_DEVIATION']} | "
            f"{labels['INTERVENTIONAL_REPAIR']} | {labels['UNSUPPORTED']} | "
            f"{c['run_conclusions_on_causal']} |"
        )
    lines += [
        "",
        "## Replay cost (replays per investigation; eligible instances)",
        "",
        "| method | mean | median | max | total |",
        "|---|---|---|---|---|",
    ]
    for method, cost in metrics["replay_cost"].items():
        e = cost["eligible"]
        lines.append(f"| {method} | {e['mean']} | {e['median']} | {e['max']} | {e['total']} |")
    if metrics["regression"]:
        lines += [
            "",
            "## Regression (candidate v2, environment fixture only)",
            "",
            "| instance | baseline | verdict | comparison | runs | cassettes built |",
            "|---|---|---|---|---|---|",
        ]
        for r in metrics["regression"]:
            lines.append(
                f"| {r['instance_id']} | {r['baseline_outcome']} | {r['verdict']} | "
                f"{r['comparison']} | {r['passes']}/{r['n']} | {r['cassettes_constructed']} |"
            )
    checks = metrics["checks"]
    lines += [
        "",
        "## Correctness checks",
        "",
        f"- Strict replay VERIFIED: {_p(checks['strict_replay_verified'])}",
        f"- Placebo valid among completed: {_p(checks['placebo_valid_among_completed'])}",
        f"- False repairs on passing runs: {checks['false_repairs_on_passing_runs']}",
        f"- UNSUPPORTED steps without a reason: {checks['unsupported_steps_without_reason']}",
        f"- Max cassette accesses after fence: {checks['max_cassette_accesses_after_fence']}",
        f"- Regression runs checked: {checks['regression_runs_checked']}; cassettes built: "
        f"{checks['regression_cassettes_constructed']}",
        f"- Benchmark matches regeneration: {checks['benchmark_matches_regeneration']}",
        "- **Overall: "
        + ("OK" if checks["ok"] else "VIOLATIONS: " + "; ".join(checks["violations"]))
        + "**",
        "",
        "## Limitations",
        "",
        "- Synthetic scripted agent, one domain; injected faults are not natural LLM failures.",
        "- Trusted references exist for every step only because the agent is scripted; CF "
        "results are an upper bound for settings where such references exist.",
        "- Some faults are visible in tool responses (inconsistent totals, archived policy flag).",
        "",
    ]
    return "\n".join(lines)


def render_failures(
    results: Sequence[dict[str, Any]],
    labels: dict[str, dict[str, Any]],
    methods: Sequence[str],
    limit: int = 12,
) -> str:
    lines = [
        "# Failure-case gallery",
        "",
        "Representative cases where a method's top-1 is not the injection site, UNSUPPORTED "
        "steps, decoy misses and multi-fault conclusions. Reproduce any case with "
        "`atrace inject <instance>` and then `atrace investigate <run_id>`.",
        "",
    ]
    rows: list[str] = []
    for r in results:
        label = labels[r["instance_id"]]
        if label["label"] != "CAUSAL":
            continue
        sites = [s["seq"] for s in label["injection_sites"]]
        for method in methods:
            inv = r["methods"][method]
            top = inv["ranking"][0] if inv["ranking"] else None
            if len(sites) == 1 and top != sites[0]:
                why = (
                    "decoy ranked first"
                    if top in label["decoy_sites"]
                    else "other step ranked first"
                )
                rows.append(
                    f"| {r['instance_id']} | {method} | {label['operators'][0]} | "
                    f"{sites[0]} | {top} | {why} | {inv['conclusion']} |"
                )
    lines += [
        "## Top-1 misses (eligible instances)",
        "",
        "| instance | method | operator | injection seq | top-1 seq | note | conclusion |",
        "|---|---|---|---|---|---|---|",
        *(rows[:limit] or ["| none | | | | | | |"]),
    ]
    if len(rows) > limit:
        lines.append(f"\n_{len(rows) - limit} more misses omitted; see results.jsonl._")
    unsupported = [
        f"| {r['instance_id']} | {m} | {s['seq']} | {s['note'] or s['reference']} |"
        for r in results
        for m in methods
        for s in r["methods"][m]["steps"]
        if s["label"] == "UNSUPPORTED"
    ]
    lines += [
        "",
        "## UNSUPPORTED steps",
        "",
        "| instance | method | seq | reason |",
        "|---|---|---|---|",
        *(unsupported[:limit] or ["| none | | | |"]),
    ]
    multi = [r for r in results if labels[r["instance_id"]]["kind"] == "MULTI"]
    if multi:
        lines += ["", "## Multi-fault cases (single-step interventions cannot isolate)", ""]
        for r in multi:
            conclusion = r["methods"].get("CF", {}).get("conclusion", "n/a")
            lines.append(f"- `{r['instance_id']}`: CF conclusion **{conclusion}**")
    return "\n".join(lines) + "\n"
