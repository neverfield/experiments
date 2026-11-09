"""Assemble and write the held-out test report from ``heldout_score``'s per-case values.

``build`` runs the scoring in its blind order: the registration check is the caller's,
then the cases, the pass plan (pending passes stop it), the trace audits (a failing
registered pass stops it), and only then the predictions. ``write`` puts everything
under one directory:

- ``report.md``: every table below, in §4's order, with the exploratory and S1 sections
  labelled as such;
- ``tables/*.md``: the same tables one per file, for the paper;
- ``figures/forest.svg`` (the six confirmatory differences with a per-ecosystem strip)
  and ``figures/hit-vs-cr.svg`` (Hit@10 against CR@10 by size, static methods);
- ``frontier/``: the test cost frontier, written by the dev selection's code;
- ``results.json`` and the CSVs: every cell, comparison, pass and case.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from heldout_plan import (
    ALPHA,
    CELLS,
    CHOICES,
    CONFIRMATORY,
    DIGITS,
    KEY_SECONDARY,
    MEMORY_CUTOFF,
    MEMORY_SPLIT,
    METRICS,
    N_BOOT,
    NAMES,
    PASSES,
    PRIMARY,
    PRIMARY_PICKS,
    REGISTRATION,
    S1_PASSES,
    S1_TOOL_BROKEN,
    SECONDARY_PICKS,
    SEED,
    SIZES,
    CellSpec,
)
from heldout_runs import PassAudit, audit_pass
from heldout_score import (
    ABOVE_LAST,
    GIVEN,
    OWNER,
    REVIEWED,
    TOP10,
    TOP10_KEYS,
    CaseSet,
    CellResult,
    Difference,
    Inputs,
    Interval,
    audit_passes,
    compare,
    comparisons,
    estimate,
    frontier_rows,
    gap,
    load_cases,
    plan_passes,
    s1_results,
    score_all,
    stability,
)

from repo_discovery import selection
from repo_discovery.stats import group_replicates, percentile_interval

REPO = Path(__file__).resolve().parents[1]
SET_QUALITY = (GIVEN, "CompleteRecall@3", "CompleteRecall@5", PRIMARY)
# H2's control is weak on dev (entry 3 of §7): its dev numbers sit beside H2.
DEV_H2 = "On dev at U5000 with real names, `scripted-search` scored CR@10 0.295 and `bm25f` 0.443 (§7, entry 3)."
FIGURE_STATIC = ("bm25f", "hybrid-rrf", "dense-cards", "name-match", "scripted-search")
COLORS = ("#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00")
FIRST_SEARCH = ("named", "not-named", "none")
GROUPS = ("all", "none")


# Building -----------------------------------------------------------------------------


@dataclass
class Report:
    registered: str
    code: dict
    cases: dict[str, CaseSet]
    results: dict[str, CellResult]
    refs: dict[tuple[int, str], dict[str, float]]
    audits: list[PassAudit]
    notes: list[str]
    diffs: list[Difference]
    skipped: list[str]
    merge_dates: dict[str, str | None] | None = None
    costs: selection.CostTables | None = None
    s1: dict | None = None
    tables: dict[str, str] = field(default_factory=dict)

    @property
    def ecosystem(self) -> Mapping[str, str]:
        return self.cases["real"].ecosystem


def code_version(repo: Path = REPO) -> dict:
    """The checkout's HEAD, and whether its code differs from it."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    changed = git("status", "--porcelain", "--", "src", "scripts", "pyproject.toml")
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(changed), "changed": changed.splitlines()}


def load_merge_dates(inputs: Inputs, cases: Mapping[str, CaseSet]) -> dict[str, str | None] | None:
    """Each real-name test case's last target merge (``model_cutoffs.py --out``)."""
    if inputs.merge_dates is None:
        return None
    rows = [json.loads(line) for line in inputs.merge_dates.read_text(encoding="utf-8").splitlines() if line.strip()]
    found = {r["case_id"]: r.get("last_merge") for r in rows}
    return {i: found.get(i) for i in cases["real"].ids}


def build(inputs: Inputs, registered: str, allow_pending: bool = False, s1: bool = False) -> Report:
    cases = load_cases(inputs, registered)
    sources, notes = plan_passes(inputs, allow_pending)
    audits, more = audit_passes(sources, cases, inputs)
    results, refs = score_all(inputs, cases, sources)
    ecosystem = cases["real"].ecosystem
    diffs, skipped = comparisons(results, ecosystem)
    report = Report(
        registered,
        code_version(),
        cases,
        results,
        refs,
        audits,
        notes + more,
        diffs,
        skipped,
        load_merge_dates(inputs, cases),
        selection.cost_tables(selection.load_registry(inputs.costs)) if inputs.costs else None,
    )
    if s1:
        report.s1 = build_s1(inputs, cases, results, allow_pending)
    return report


def build_s1(
    inputs: Inputs, cases: Mapping[str, CaseSet], results: Mapping[str, CellResult], allow_pending: bool
) -> dict:
    """S1, minimal: the five passes' audits as written and H1–H3 with them in place."""
    rescored = s1_results(inputs, cases, results, allow_pending)
    sources, _ = plan_passes(inputs, allow_pending, s1=True)
    audits = [
        audit_pass(
            CELLS[s.registered.cell],  # type: ignore[union-attr]
            s.registered,
            s.predictions.parent,
            s.traces,  # type: ignore[arg-type]
            list(cases[CELLS[s.registered.cell].names].cases),  # type: ignore[union-attr]
            inputs.run_env_commit_key,
        )
        for cell in sources.values()
        for s in cell
        if s.as_written
    ]
    diffs, skipped = comparisons(rescored, cases["real"].ecosystem)
    touched = sorted({k.split("/", 1)[1] for k in S1_PASSES})
    return {
        "results": {k: rescored[k] for k in touched if k in rescored},
        "audits": audits,
        "diffs": [d for d in diffs if d.comparison.family == "confirmatory"],
        "skipped": skipped,
    }


# Summaries ----------------------------------------------------------------------------


def group_ids(report: Report, result: CellResult, group: str) -> list[str]:
    ids = sorted(result.per_case)
    if group == "all":
        return ids
    visibility = report.cases[result.spec.names].visibility
    return [i for i in ids if visibility[i] == group]


def estimated_keys(result: CellResult) -> list[str]:
    if not result.per_case:
        return []
    return [k for k in next(iter(result.per_case.values())) if k != ABOVE_LAST]


def above_last(result: CellResult, ids: Sequence[str]) -> dict:
    """Item 17: the median of non-targets above the last target, censored cases above
    every other value, and how many were censored."""
    values = sorted(result.per_case[i][ABOVE_LAST] for i in ids)
    if not values:
        return {"median": None, "censored": 0, "n": 0}
    median = statistics.median(values)
    return {
        "median": None if math.isinf(median) else median,
        "median_censored": math.isinf(median),
        "censored": sum(math.isinf(v) for v in values),
        "n": len(values),
    }


@dataclass
class CellSummary:
    result: CellResult
    groups: dict[str, dict[str, Interval]]
    above_last: dict[str, dict]
    first_search: dict[str, Counter]
    median_last: dict[str, float | None]


def summarize(report: Report, result: CellResult) -> CellSummary:
    groups, above, searches, medians = {}, {}, {}, {}
    keys = estimated_keys(result)
    visibility = report.cases[result.spec.names].visibility
    for group in GROUPS:
        ids = group_ids(report, result, group)
        groups[group] = {k: estimate({i: result.per_case[i][k] for i in ids}, ids, report.ecosystem) for k in keys}
        above[group] = above_last(result, ids)
        medians[group] = (
            statistics.median(result.per_case[i]["LastRequiredRank"] for i in ids) if ids else None
        )
        searches[group] = Counter(
            kind for case_id, _, kind in result.first_search if group == "all" or visibility[case_id] == group
        )
    return CellSummary(result, groups, above, searches, medians)


def reference_rows(report: Report) -> list[dict]:
    """Item 17's two owner-given references per size and name condition."""
    rows, key = [], f"{OWNER}{PRIMARY}"
    for (size, names), values in sorted(report.refs.items(), key=lambda kv: (kv[0][0], NAMES.index(kv[0][1]))):
        visibility = report.cases[names].visibility
        bm25f = report.results.get(f"u{size}-{names}-bm25f")
        within = bm25f is not None and bm25f.per_case and key in next(iter(bm25f.per_case.values()))
        for group in GROUPS:
            ids = [i for i in sorted(values) if group == "all" or visibility[i] == group]
            rows.append(
                {
                    "size": size,
                    "names": names,
                    "group": group,
                    "random": estimate(values, ids, report.ecosystem),
                    "bm25f": (
                        estimate({i: bm25f.per_case[i][key] for i in ids}, ids, report.ecosystem)  # type: ignore[union-attr]
                        if within
                        else None
                    ),
                }
            )
    return rows


def memory_rows(report: Report) -> tuple[list[dict], list[str]]:
    """§4's change memory: agent cells split at composer-2.5's reported cutoff."""
    if report.merge_dates is None:
        return [], ["no merge_dates in the inputs; change memory not computed"]
    period = {
        i: "undated" if d is None else ("before" if d[:10] < MEMORY_CUTOFF else "after")
        for i, d in report.merge_dates.items()
    }
    counts = Counter(period.values())
    notes = [f"{counts['before']} cases before {MEMORY_CUTOFF}, {counts['after']} after, {counts['undated']} undated"]
    if counts["before"] != MEMORY_SPLIT["before"] or counts["after"] != MEMORY_SPLIT["after"]:
        notes.append(
            f"the registration says {MEMORY_SPLIT['before']} before and {MEMORY_SPLIT['after']} after; "
            "these merge dates differ"
        )
    rows = []
    for name, r in report.results.items():
        if not r.spec.agent or not r.per_case:
            continue
        ids = sorted(r.per_case)
        row: dict = {"cell": name, "role": r.spec.role}
        for metric in (PRIMARY, KEY_SECONDARY):
            values = {i: r.per_case[i][metric] for i in ids}
            for p in ("before", "after"):
                chosen = [i for i in ids if period.get(i) == p]
                row[f"{metric}:{p}"] = estimate(values, chosen, report.ecosystem)
            reps = group_replicates(
                [values[i] for i in ids],
                [report.ecosystem[i] for i in ids],
                [period.get(i, "undated") for i in ids],
                N_BOOT,
                SEED,
            )
            mean = row[f"{metric}:after"].mean - row[f"{metric}:before"].mean
            low, high = percentile_interval(reps["after"] - reps["before"], ALPHA)
            row[f"{metric}:after-before"] = Interval(mean, low, high, len(ids))
        rows.append(row)
    return rows, notes


def reviewed_rows(report: Report) -> list[dict]:
    """Reviewed labels against WideSWE labels, per cell, and the paired difference."""
    rows = []
    for name, r in report.results.items():
        key = f"{REVIEWED}{PRIMARY}"
        if not r.per_case or key not in next(iter(r.per_case.values())):
            continue
        ids = sorted(r.per_case)
        diffs = {i: r.per_case[i][key] - r.per_case[i][PRIMARY] for i in ids}
        rows.append(
            {
                "cell": name,
                "wideswe": estimate({i: r.per_case[i][PRIMARY] for i in ids}, ids, report.ecosystem),
                "reviewed": estimate({i: r.per_case[i][key] for i in ids}, ids, report.ecosystem),
                "reviewed-wideswe": estimate(diffs, ids, report.ecosystem),
            }
        )
    return rows


def miss_summary(result: CellResult) -> dict:
    """Per-case error analysis: the runs that missed CR@10, by where their targets were."""
    runs = len(result.sources) * len(result.per_case)
    ranks = [[r for r in m["target_ranks"].split(",")] for m in result.misses]
    out = {
        "runs": runs,
        "missed": len(result.misses),
        "a target unranked": sum("-" in r for r in ranks),
        "a target below 100": sum(any(x == "-" or int(x) > 100 for x in r) for r in ranks),
        "all in top 20": sum(all(x != "-" and int(x) <= 20 for x in r) for r in ranks),
    }
    if result.spec.agent:
        out["a target outside the agent's list"] = sum(m.get("outside_own_list", 0) > 0 for m in result.misses)
        out["errored or timed out"] = sum(m.get("status") in ("error", "timeout") for m in result.misses)
        out["turn budget"] = sum(m.get("status") == "turn_budget" for m in result.misses)
    return out


def per_ecosystem(report: Report, d: Difference) -> list[tuple[str, int, float]]:
    a, b = report.results[d.comparison.a], report.results[d.comparison.b]
    by: dict[str, list[float]] = defaultdict(list)
    for i in sorted(a.per_case):
        by[report.ecosystem[i]].append(a.per_case[i][d.comparison.metric] - b.per_case[i][d.comparison.metric])
    return [(e, len(v), float(np.mean(v))) for e, v in sorted(by.items())]


# Text ---------------------------------------------------------------------------------


def iv(value: Interval | None, sign: bool = False) -> str:
    return "–" if value is None else value.text(3, sign)


def num(value: float | None, digits: int = 3) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "–"
    return f"{value:.{digits}f}"


def p_text(p: float | None) -> str:
    if p is None:
        return "–"
    return f"< {1 / N_BOOT:.4f}" if p == 0 else f"{p:.4f}"


def table(header: Sequence[str], rows: Iterable[Sequence[object]], right: Sequence[int] = ()) -> str:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("--:" if i in right else "---" for i in range(len(header))) + "|")
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def cell_order(results: Mapping[str, CellResult]) -> list[str]:
    role = {"primary": 0, "secondary": 1, "exploratory": 2, "baseline": 3}
    return sorted(
        results,
        key=lambda n: (results[n].spec.size, NAMES.index(results[n].spec.names), role[results[n].spec.role], n),
    )


def decision(d: Difference) -> str:
    if d.reject is None:
        return "–"
    return "reject H0" if d.reject else "don't reject H0"


def confirmatory_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    rows = []
    for d in report.diffs:
        if d.comparison.family != "confirmatory":
            continue
        a, b = summaries[d.comparison.a], summaries[d.comparison.b]
        rows.append(
            [
                d.comparison.id,
                d.comparison.question,
                f"`{d.comparison.a}`",
                iv(a.groups["all"][PRIMARY]),
                f"`{d.comparison.b}`",
                iv(b.groups["all"][PRIMARY]),
                iv(d.interval, sign=True),
                f"{d.won} / {d.lost} / {d.tied}",
                p_text(d.p_one_sided),
                p_text(d.p_holm),
                decision(d),
            ]
        )
    head = ["Test", "Question", "A", "CR@10 A", "B", "CR@10 B", "A − B [95% CI]", "Won / lost / tied", "p (one-sided)", "Holm p", "Decision"]
    notes = [
        "",
        f"Paired per-case differences of pass-pooled CR@10 (addendum item 15), {N_BOOT} ecosystem resamples, seed {SEED}. "
        "The interval is two-sided and unadjusted; p is the share of resamples with a difference ≤ 0; "
        f"Holm's step-down runs over these six tests at α = {ALPHA}.",
        "",
        DEV_H2,
    ]
    notes += [f"- Not computed: {s}" for s in report.skipped if "Holm" in s or s.startswith("H")]
    return table(head, rows, right=(3, 5, 6, 8, 9)) + "\n".join(notes) + "\n"


def comparison_table(diffs: Iterable[Difference], with_p: bool = False) -> str:
    rows = [
        [
            d.comparison.id,
            d.comparison.question,
            f"`{d.comparison.a}` − `{d.comparison.b}`",
            d.comparison.metric,
            iv(d.interval, sign=True),
            f"{d.won} / {d.lost} / {d.tied}",
            *([p_text(d.p_one_sided), p_text(d.p_holm)] if with_p else []),
        ]
        for d in diffs
    ]
    head = ["ID", "Question", "Difference", "Metric", "A − B [95% CI]", "Won / lost / tied"]
    if with_p:
        head += ["p (one-sided)", "Holm p"]
    return table(head, rows, right=(4,))


def main_rows(size: int, names: str) -> list[str]:
    secondary = SECONDARY_PICKS[(size, names)]
    out = [PRIMARY_PICKS[(size, names)], secondary]
    out += [f"u{size}-{names}-{m}" for m in ("random", "name-match", "bm25f", "hybrid-rrf", "scripted-search")]
    budget = CELLS[secondary].budget
    if budget:
        out.append(f"u{size}-{names}-scripted-open{budget}")
    return list(dict.fromkeys(out))


def main_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    """Paper table 7: picks and key baselines by size and name condition, with cost."""
    parts = []
    for size in SIZES:
        for names in NAMES:
            rows = []
            for name in main_rows(size, names):
                s = summaries.get(name)
                if s is None or not s.result.per_case:
                    rows.append([f"`{name}`", CELLS[name].role, *["–"] * 7])
                    continue
                g, costs = s.groups["all"], cost_means(s.result)
                rows.append(
                    [
                        f"`{name}`",
                        s.result.spec.role,
                        iv(g[PRIMARY]),
                        iv(g[KEY_SECONDARY]),
                        iv(g["Hit@10"]),
                        iv(g["RequiredRecall@10"]),
                        num(s.median_last["all"], 1),
                        num(costs.get("usd")),
                        num(costs.get("tokens"), 0),
                    ]
                )
            parts.append(f"**U{size}, {names} names**\n\n" + table(
                ["Cell", "Role", "CR@10", "CR@20", "Hit@10", "RequiredRecall@10", "Median LastRequiredRank", "$ per case", "Tokens per case"],
                rows,
                right=(2, 3, 4, 5, 6, 7, 8),
            ))
    note = "LastRequiredRank is censored at 101 and summarised by its median over pass-pooled per-case values."
    return "\n".join(parts) + "\n" + note + "\n"


def cells_table(report: Report, summaries: Mapping[str, CellSummary], names: Iterable[str]) -> str:
    rows = []
    for name in names:
        s = summaries[name]
        if not s.result.per_case:
            rows.append([f"`{name}`", s.result.spec.role, 0, *["–"] * 6, "; ".join(s.result.notes)])
            continue
        g = s.groups["all"]
        rows.append(
            [
                f"`{name}`",
                s.result.spec.role,
                len(s.result.sources),
                iv(g[PRIMARY]),
                iv(g[KEY_SECONDARY]),
                iv(g["Hit@10"]),
                iv(g["RequiredRecall@10"]),
                iv(g["LastRequiredRank"]),
                num(s.median_last["all"], 1),
                "; ".join(s.result.notes),
            ]
        )
    return table(
        ["Cell", "Role", "Runs", "CR@10", "CR@20", "Hit@10", "RequiredRecall@10", "LastRequiredRank (mean)", "(median)", "Notes"],
        rows,
        right=(2, 3, 4, 5, 6, 7, 8),
    )


def gap_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    gaps = gap(report.results, report.ecosystem)
    rows = [
        [f"`{n}`", summaries[n].result.spec.role, iv(summaries[n].groups["all"]["Hit@10"]),
         iv(summaries[n].groups["all"][PRIMARY]), iv(gaps[n], sign=True)]
        for n in cell_order(report.results)
        if n in gaps and summaries[n].result.spec.registered
    ]
    return table(["Cell", "Role", "Hit@10", "CR@10", "Hit@10 − CR@10"], rows, right=(2, 3, 4))


def pass_info(report: Report) -> dict[str, PassAudit]:
    return {a.key: a for a in report.audits}


def host_of(key: str, audit: PassAudit | None) -> str:
    env_host = (audit.run_env or {}).get("host") if audit else None
    registered = PASSES.get(key)
    return env_host or (registered.host if registered else "") or "–"


def stability_table(report: Report) -> str:
    audits = pass_info(report)
    rows = []
    for metric in (PRIMARY, KEY_SECONDARY):
        for row in stability(report.results, report.ecosystem, metric):
            labels = [
                f"{p}: {audits[p].commit if p in audits else '–'}, {host_of(p, audits.get(p))}" for p in row["passes"]
            ]
            per_pass = [iv(x) for x in row["per_pass"]] + ["–"] * (2 - len(row["per_pass"]))
            rows.append(
                [f"`{row['cell']}`", row["role"], metric, *per_pass[:2], iv(row["pooled"]),
                 iv(row["p2_minus_p1"], sign=True), "<br>".join(labels)]
            )
    return table(
        ["Cell", "Role", "Metric", "Pass 1", "Pass 2", "Pooled", "Pass 2 − pass 1", "Commit and host"],
        rows,
        right=(3, 4, 5, 6),
    )


def cost_means(result: CellResult) -> dict[str, float]:
    if not result.costs:
        return {}
    keys = next(iter(result.costs.values()))
    out = {k: statistics.fmean(result.costs[i][k] for i in result.costs) for k in keys}
    if "seconds" in keys:
        out["median_seconds"] = statistics.median(result.costs[i]["seconds"] for i in result.costs)
    return out


def cost_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    rows = []
    for name in cell_order(report.results):
        r = report.results[name]
        costs = cost_means(r)
        if not costs or not r.spec.registered:
            continue
        cr = summaries[name].groups["all"][PRIMARY].mean
        usd = costs.get("usd", 0.0)
        rows.append(
            [
                f"`{name}`",
                r.spec.role,
                num(usd),
                num(costs.get("tokens"), 0),
                num(costs.get("median_seconds"), 0),
                num(costs.get("fetch_requests"), 1),
                num(None if "fetch_bytes" not in costs else costs["fetch_bytes"] / 1e6, 2),
                num(usd / cr if cr else None) if usd else "–",
            ]
        )
    return table(
        ["Cell", "Role", "$ per case", "Tokens per case", "Median s per case", "Fetch requests per case", "Fetch MB per case", "$ per complete set (CR@10)"],
        rows,
        right=(2, 3, 4, 5, 6, 7),
    ) + "\n$ per complete set is the mean $ per case over the mean CR@10. Latency is the laptop runner's (§6, deviation 6).\n"


def passes_table(report: Report) -> str:
    rows = []
    for a in report.audits:
        registered = PASSES.get(a.key)
        rows.append(
            [
                a.key,
                registered.status if registered else "–",
                registered.accepted_run if registered else "–",
                a.commit,
                host_of(a.key, a),
                a.traces,
                len(a.timeouts),
                len(a.provider_errors),
                len(a.cli_not_server) if CELLS[a.key.split("/", 1)[1]].tool else "–",
                len(a.no_call) if CELLS[a.key.split("/", 1)[1]].tool else "–",
                ", ".join(a.provider_errors) or "–",
            ]
        )
    out = table(
        ["Pass", "Registry", "Accepted run (item 12)", "Commit", "Host", "Traces", "Timeout cases", "Provider-error cases", "Tool bound (a)", "Tool bound (b)", "Cases still erroring (§5)"],
        rows,
        right=(5, 6, 7, 8, 9),
    )
    if report.notes:
        out += "\n" + "\n".join(f"- {n}" for n in report.notes) + "\n"
    return out


def per_ecosystem_table(report: Report) -> str:
    parts = []
    for d in report.diffs:
        if d.comparison.family != "confirmatory":
            continue
        rows = [[e, n, f"{m:+.3f}"] for e, n, m in per_ecosystem(report, d)]
        parts.append(f"**{d.comparison.id}** (`{d.comparison.a}` − `{d.comparison.b}`)\n\n" + table(["Ecosystem", "Cases", "Mean difference"], rows, right=(1, 2)))
    return "\n".join(parts)


def none_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    rows = []
    for name in cell_order(report.results):
        s = summaries[name]
        if not s.result.per_case:
            continue
        a, n = s.groups["all"], s.groups["none"]
        rows.append(
            [f"`{name}`", s.result.spec.role, n[PRIMARY].n, iv(a[PRIMARY]), iv(n[PRIMARY]), iv(a[KEY_SECONDARY]),
             iv(n[KEY_SECONDARY]), iv(n["Hit@10"]), iv(n[GIVEN])]
        )
    out = table(
        ["Cell", "Role", "`none` cases", "CR@10 all", "CR@10 `none`", "CR@20 all", "CR@20 `none`", "Hit@10 `none`", "CR@|G| `none`"],
        rows,
        right=(2, 3, 4, 5, 6, 7, 8),
    )
    within = []
    for c in CONFIRMATORY:
        a = report.results.get(c.a)
        if a is None or not a.per_case:
            continue
        ids = group_ids(report, a, "none")
        d = compare(c, report.results, report.ecosystem, ids=ids) if ids else None
        if d is not None:
            within.append(d)
    out += "\nH1–H3 within the `none` group (no p-values):\n\n" + comparison_table(within)
    out += "\nEvery metric of item 17 for this group is in `cells.csv` (`group` = `none`).\n"
    return out


def owner_tables(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    refs = [
        [f"U{r['size']}", r["names"], r["group"], iv(r["random"]), iv(r["bm25f"])]
        for r in reference_rows(report)
    ]
    out = "Owner-given references per size and name condition: (i) O first in a uniformly random order, " \
          "the exact expected CR@10; (ii) `bm25f` at L4 restricted to O.\n\n"
    out += table(["Size", "Names", "Cases", "(i) random order", "(ii) `bm25f` within O"], refs, right=(3, 4))
    rows = []
    for name in cell_order(report.results):
        s = summaries[name]
        if not s.result.per_case or f"{OWNER}{PRIMARY}" not in s.groups["all"]:
            continue
        g = s.groups["all"]
        fs = s.first_search["all"]
        searches = " / ".join(str(fs[k]) for k in FIRST_SEARCH) if s.result.spec.agent else "–"
        rows.append(
            [f"`{name}`", s.result.spec.role, iv(g[PRIMARY]), iv(g[f"{OWNER}{PRIMARY}"]),
             iv(g[f"{OWNER}{KEY_SECONDARY}"]), iv(g[f"{OWNER}{GIVEN}"]), searches]
        )
    out += "\nWithin-owner rescoring (each ranking restricted to O) and, for agent cells, the first search " \
           "over runs (case × pass): names a target owner / doesn't / no grep, glob or `search_repos` call.\n\n"
    out += table(
        ["Cell", "Role", "CR@10", "Within O: CR@10", "Within O: CR@20", "Within O: CR@|G|", "First search named / not named / none"],
        rows,
        right=(2, 3, 4, 5),
    )
    return out


def set_quality_table(report: Report, summaries: Mapping[str, CellSummary]) -> str:
    rows = []
    for name in cell_order(report.results):
        s = summaries[name]
        if not s.result.per_case:
            continue
        g, above = s.groups["all"], s.above_last["all"]
        median = "censored" if above.get("median_censored") else num(above["median"], 1)
        fill = [num(g[k].mean, 2) if k in g else "–" for k in TOP10_KEYS]
        rows.append([f"`{name}`", s.result.spec.role, *(iv(g[m]) for m in SET_QUALITY), median, above["censored"], *fill])
    head = [
        "Cell", "Role", "CR@|G|", "CR@3", "CR@5", "CR@10", "Median non-targets above last", "Censored",
        *(k[len(TOP10):] for k in TOP10_KEYS),
    ]
    return table(head, rows, right=tuple(range(2, len(head)))) + (
        "\nThe last seven columns are the mean count per case among the first 10 ranks: every non-target, then by "
        "layer (WideSWE context, same-owner layer, frame sample, anything else) and by owner (a target owner or not). "
        "A case is censored when a target ranks below 100; a pass-pooled case is censored when either pass is.\n"
    )


def memory_table(report: Report) -> str:
    rows, notes = memory_rows(report)
    out = "\n".join(f"- {n}" for n in notes) + "\n\n"
    if rows:
        out += table(
            ["Cell", "Role", "CR@10 before", "CR@10 after", "After − before", "CR@20 before", "CR@20 after", "After − before"],
            [
                [f"`{r['cell']}`", r["role"],
                 *(iv(r[f"{m}:{p}"], sign=p == "after-before") for m in (PRIMARY, KEY_SECONDARY) for p in ("before", "after", "after-before"))]
                for r in rows
            ],
            right=(2, 3, 4, 5, 6, 7),
        )
    return out


def reviewed_table(report: Report) -> str:
    rows = reviewed_rows(report)
    if not rows:
        return "No reviewed labels in the inputs; not computed.\n"
    out = table(
        ["Cell", "CR@10, WideSWE labels", "CR@10, reviewed labels", "Reviewed − WideSWE"],
        [[f"`{r['cell']}`", iv(r["wideswe"]), iv(r["reviewed"]), iv(r["reviewed-wideswe"], sign=True)] for r in rows],
        right=(1, 2, 3),
    )
    key = f"{REVIEWED}{PRIMARY}"
    reviewed = {r["cell"] for r in rows}
    again = [
        d
        for c in CONFIRMATORY
        if c.a in reviewed and c.b in reviewed
        and (d := compare(c, report.results, report.ecosystem, metric=key)) is not None
    ]
    if again:
        out += "\nH1–H3 on reviewed labels (no p-values):\n\n" + comparison_table(again)
    return out


def misses_table(report: Report) -> str:
    rows = []
    for name in cell_order(report.results):
        r = report.results[name]
        if not r.per_case:
            continue
        m = miss_summary(r)
        rows.append([f"`{name}`", r.spec.role, m["runs"], m["missed"], m["a target unranked"], m["a target below 100"],
                     m["all in top 20"], m.get("a target outside the agent's list", "–"),
                     m.get("errored or timed out", "–"), m.get("turn budget", "–")])
    return table(
        ["Cell", "Role", "Runs", "Missed CR@10", "A target unranked", "A target below 100", "All targets in top 20",
         "A target outside the agent's own list", "Errored or timed out", "Turn budget"],
        rows,
        right=tuple(range(2, 10)),
    ) + "\nOne row per run (case × pass or draw) in `misses.csv`, with each target's rank.\n"


def s1_section(report: Report) -> str:
    s1 = report.s1
    if s1 is None:
        return "S1 is off (the default). `--s1` scores the five concurrency-withdrawn passes as written in place of their reruns.\n"
    rows = [
        [a.key, a.commit, a.traces, len(a.timeouts), len(a.provider_errors),
         "yes" if a.key in S1_TOOL_BROKEN else "", "; ".join(a.problems) or "–"]
        for a in s1["audits"]
    ]
    out = (
        "**Sensitivity analysis S1, not registered.** The five passes withdrawn under entry 7's concurrency rule "
        "(addendum item 18), scored as written in place of their reruns; errored and timed-out cases count as written. "
        "Everything else is as registered.\n\n"
    )
    out += table(["Withdrawn pass", "Commit", "Traces", "Timeout cases", "Provider-error cases", "Tool never reached its server (†)", "Bounds it fails"], rows, right=(2, 3, 4))
    out += "\nH1–H3 under S1:\n\n" + comparison_table(s1["diffs"], with_p=True)
    return out


# Figures ------------------------------------------------------------------------------


def forest_svg(report: Report) -> str:
    """The six confirmatory differences with their intervals, and each ecosystem's mean
    difference as a strip; the size of a strip dot grows with the ecosystem's cases."""
    rows = [d for d in report.diffs if d.comparison.family == "confirmatory"]
    width, top, row_h, left, right = 760, 48, 46, 210, 40
    height = top + row_h * len(rows) + 50
    span = width - left - right

    def x(v: float) -> float:
        return left + (v + 1) / 2 * span

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="11">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{left}" y="20" font-size="13">Confirmatory differences in CR@10 (A − B), 95% ecosystem-bootstrap intervals</text>',
        f'<line x1="{x(0)}" x2="{x(0)}" y1="{top - 10}" y2="{height - 40}" stroke="#999" stroke-dasharray="3,3"/>',
    ]
    for v in (-1, -0.5, 0, 0.5, 1):
        out.append(f'<text x="{x(v)}" y="{height - 24}" text-anchor="middle">{v:+.1f}</text>')
    for k, d in enumerate(rows):
        y = top + k * row_h + row_h / 2
        out.append(f'<text x="{left - 10}" y="{y + 4}" text-anchor="end">{d.comparison.id}: {d.won} won, {d.lost} lost</text>')
        for _, n, m in per_ecosystem(report, d):
            out.append(f'<circle cx="{x(m):.1f}" cy="{y + 12:.1f}" r="{1.5 + n ** 0.5:.1f}" fill="#aaa" fill-opacity="0.5"/>')
        i = d.interval
        if not math.isnan(i.low):
            out.append(f'<line x1="{x(i.low):.1f}" x2="{x(i.high):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{COLORS[0]}" stroke-width="2"/>')
        out.append(f'<circle cx="{x(i.mean):.1f}" cy="{y:.1f}" r="4" fill="{COLORS[0]}"/>')
    out.append(f'<text x="{left}" y="{height - 6}">n = {len(report.ecosystem)} cases in {len(set(report.ecosystem.values()))} ecosystems; grey dots: per-ecosystem mean differences</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def hit_cr_svg(summaries: Mapping[str, CellSummary]) -> str:
    """Hit@10 (dashed) against CR@10 (solid) by size, for the static methods."""
    width, height, pad, gap_w = 980, 400, 56, 40
    panel_w = (width - 2 * pad - gap_w) / 2
    plot_h = height - 2 * pad
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="11">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{pad}" y="20" font-size="13">Hit@10 (dashed) against CR@10 (solid) by universe size, static methods</text>',
    ]
    for p, names in enumerate(NAMES):
        x0 = pad + p * (panel_w + gap_w)

        def x(k: int, x0: float = x0) -> float:
            return x0 + 0.08 * panel_w + k / (len(SIZES) - 1) * 0.7 * panel_w

        def y(v: float) -> float:
            return pad + (1 - v) * plot_h

        out.append(f'<rect x="{x0}" y="{pad}" width="{panel_w}" height="{plot_h}" fill="none" stroke="#999"/>')
        out.append(f'<text x="{x0 + panel_w / 2}" y="{pad - 8}" text-anchor="middle">{names} names</text>')
        for q in (0, 0.25, 0.5, 0.75, 1):
            out.append(f'<text x="{x0 - 4}" y="{y(q) + 4}" text-anchor="end">{q:.2f}</text>')
        for k, size in enumerate(SIZES):
            out.append(f'<text x="{x(k)}" y="{height - pad + 16}" text-anchor="middle">U{size}</text>')
        for method, color in zip(FIGURE_STATIC, COLORS, strict=True):
            for metric, dash in ((PRIMARY, ""), ("Hit@10", ' stroke-dasharray="4,3"')):
                points = [
                    (x(k), y(summaries[f"u{s}-{names}-{method}"].groups["all"][metric].mean))
                    for k, s in enumerate(SIZES)
                    if f"u{s}-{names}-{method}" in summaries and summaries[f"u{s}-{names}-{method}"].result.per_case
                ]
                if len(points) > 1:
                    path = " ".join(f"{a:.1f},{b:.1f}" for a, b in points)
                    out.append(f'<polyline points="{path}" fill="none" stroke="{color}" stroke-width="1.5"{dash}/>')
                if points and metric == PRIMARY:
                    a, b = points[-1]
                    out.append(f'<text x="{a + 6:.1f}" y="{b + 4:.1f}" fill="{color}">{method}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


# Writing ------------------------------------------------------------------------------


def rounded(value: object) -> object:
    if isinstance(value, float):
        if math.isinf(value):
            return "censored"
        return None if math.isnan(value) else round(value, DIGITS)
    return value


def interval_record(value: Interval | None) -> list | None:
    return None if value is None else [rounded(value.mean), rounded(value.low), rounded(value.high)]


def difference_record(d: Difference, group: str = "all") -> dict:
    return {
        "id": d.comparison.id,
        "family": d.comparison.family,
        "group": group,
        "question": d.comparison.question,
        "a": d.comparison.a,
        "b": d.comparison.b,
        "metric": d.comparison.metric,
        "diff": rounded(d.interval.mean),
        "low": rounded(d.interval.low),
        "high": rounded(d.interval.high),
        "n": d.interval.n,
        "won": d.won,
        "lost": d.lost,
        "tied": d.tied,
        "p_one_sided": rounded(d.p_one_sided),
        "p_holm": rounded(d.p_holm),
        "reject": d.reject,
    }


def write_csv(path: Path, rows: Sequence[Mapping]) -> None:
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: rounded(v) for k, v in r.items()} for r in rows)


def spec_fields(spec: CellSpec) -> dict:
    return {"cell": spec.name, "role": spec.role, "names": spec.names, "size": spec.size, "method": spec.method}


def write(report: Report, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    summaries = {n: summarize(report, r) for n, r in report.results.items()}
    order = cell_order(report.results)
    registered = [n for n in order if report.results[n].spec.registered]
    exploratory = [n for n in order if not report.results[n].spec.registered]
    secondary = [d for d in report.diffs if d.comparison.family == "secondary"]
    sections = [
        ("passes", "Passes scored", passes_table(report)),
        ("confirmatory", "Confirmatory: H1–H3 at U5000", confirmatory_table(report, summaries)),
        ("main-results", "Main results by size and name condition", main_table(report, summaries)),
        ("cells", "Every registered cell", cells_table(report, summaries, registered)),
        ("secondary", "Secondary: the comparisons at U1000 and U10000, on CR@20, and the mechanisms",
         comparison_table([d for d in secondary if not d.comparison.id.startswith("M")])),
        ("mechanisms", "Secondary: static mechanism replications at U5000",
         comparison_table([d for d in secondary if d.comparison.id.startswith("M")])),
        ("hit-cr-gap", "Secondary: Hit@10 against CR@10", gap_table(report, summaries)),
        ("stability", "Secondary: agent stability", stability_table(report)),
        ("cost", "Secondary: cost per case (frontier in `frontier/`)", cost_table(report, summaries)),
        ("per-ecosystem", "Confirmatory differences by ecosystem", per_ecosystem_table(report)),
        ("n50", "Exploratory (entry 6): L5 N = 50 at U5000 and U10000, real names",
         cells_table(report, summaries, exploratory)
         + "\n" + comparison_table([d for d in report.diffs if d.comparison.family == "exploratory"])),
        ("change-memory", f"Exploratory: change memory (last target merge before {MEMORY_CUTOFF})", memory_table(report)),
        ("reviewed", "Exploratory: reviewed labels against WideSWE labels", reviewed_table(report)),
        ("misses", "Exploratory: misses", misses_table(report)),
        ("owner-shortcut", "Exploratory (item 17): the owner shortcut", owner_tables(report, summaries)),
        ("set-quality", "Exploratory (item 17): set quality", set_quality_table(report, summaries)),
        ("none-group", "Exploratory (item 17): the `none` visibility group", none_table(report, summaries)),
        ("s1", "Sensitivity S1 (off by default)", s1_section(report)),
    ]
    tables = out / "tables"
    tables.mkdir(exist_ok=True)
    header = [
        "# Held-out test results",
        "",
        f"Generated by `scripts/test_report.py` at commit `{report.code['commit']}`"
        + (" with uncommitted changes" if report.code["dirty"] else "")
        + f"; registration `{report.registered}` (`{REGISTRATION}`). "
        f"{len(report.ecosystem)} test cases in {len(set(report.ecosystem.values()))} ecosystems. "
        f"Every interval is a 95% percentile bootstrap over test ecosystems ({N_BOOT} resamples, seed {SEED}). "
        "An agent cell's per-case values are means over its accepted passes (addendum item 15); "
        "`bm25f-deps-random`'s are means over its draws.",
        "",
    ]
    body = []
    for slug, title, text in sections:
        report.tables[slug] = text
        (tables / f"{slug}.md").write_text(f"## {title}\n\n{text}", encoding="utf-8")
        body += [f"## {title}", "", text]
    (out / "report.md").write_text("\n".join(header + body), encoding="utf-8")

    figures = out / "figures"
    figures.mkdir(exist_ok=True)
    (figures / "forest.svg").write_text(forest_svg(report), encoding="utf-8")
    (figures / "hit-vs-cr.svg").write_text(hit_cr_svg(summaries), encoding="utf-8")

    cell_rows, case_rows, pass_rows, search_rows, miss_rows = [], [], [], [], []
    for name in order:
        s = summaries[name]
        r = s.result
        for group in GROUPS:
            for key, value in s.groups[group].items():
                cell_rows.append({**spec_fields(r.spec), "group": group, "metric": key, "mean": value.mean,
                                  "low": value.low, "high": value.high, "n": value.n})
            above = s.above_last[group]
            cell_rows.append({**spec_fields(r.spec), "group": group, "metric": f"{ABOVE_LAST}:median",
                              "mean": above["median"] if not above.get("median_censored") else math.inf,
                              "n": above["n"], "censored": above["censored"]})
            for kind in FIRST_SEARCH:
                if r.spec.agent:
                    cell_rows.append({**spec_fields(r.spec), "group": group, "metric": f"first-search:{kind}",
                                      "mean": float(s.first_search[group][kind])})
        visibility = report.cases[r.spec.names].visibility
        for case_id, values in r.per_case.items():
            case_rows.append({"cell": name, "case_id": case_id, "ecosystem": report.ecosystem[case_id],
                              "visibility": visibility[case_id], **values, **{f"cost:{k}": v for k, v in r.costs.get(case_id, {}).items()}})
        for label, part in zip(r.sources, r.per_source, strict=True):
            if r.spec.agent:
                for case_id, values in part.items():
                    pass_rows.append({"cell": name, "pass": label, "case_id": case_id, **{m: values[m] for m in METRICS}})
        search_rows += [{"cell": name, "pass": p, "case_id": c, "first_search": k} for c, p, k in r.first_search]
        miss_rows += [{"cell": name, "ecosystem": report.ecosystem[m["case_id"]],
                       "visibility": visibility[m["case_id"]], **m} for m in r.misses]
    write_csv(out / "cells.csv", cell_rows)
    write_csv(out / "per_case.csv", case_rows)
    write_csv(out / "per_pass.csv", pass_rows)
    write_csv(out / "first_search.csv", search_rows)
    write_csv(out / "misses.csv", miss_rows)
    write_csv(out / "audits.csv", [a.row() for a in report.audits])

    diff_rows = [difference_record(d) for d in report.diffs]
    for c in CONFIRMATORY:
        a = report.results.get(c.a)
        if a is not None and a.per_case:
            ids = group_ids(report, a, "none")
            d = compare(c, report.results, report.ecosystem, ids=ids) if ids else None
            if d is not None:
                diff_rows.append(difference_record(d, "none"))
    if report.s1:
        diff_rows += [difference_record(d, "s1") for d in report.s1["diffs"]]
    write_csv(out / "comparisons.csv", diff_rows)

    frontier = None
    if report.costs is not None:
        rows = frontier_rows(report.results, report.ecosystem, report.costs)
        selection.write_frontier(out / "frontier", rows, rows, PRIMARY, selection.COST_TOLERANCE)
        frontier = str(out / "frontier")

    record = {
        "registration": report.registered,
        "code": report.code,
        "cases": len(report.ecosystem),
        "ecosystems": len(set(report.ecosystem.values())),
        "choices": CHOICES,
        "notes": report.notes,
        "skipped": report.skipped,
        "passes": [a.row() for a in report.audits],
        "cells": {
            n: {
                **spec_fields(summaries[n].result.spec),
                "sources": summaries[n].result.sources,
                "notes": summaries[n].result.notes,
                "groups": {
                    g: {k: interval_record(v) for k, v in summaries[n].groups[g].items()}
                    | {"n": len(group_ids(report, summaries[n].result, g)), f"{ABOVE_LAST}:median": summaries[n].above_last[g]}
                    for g in GROUPS
                },
                "first_search": {g: dict(summaries[n].first_search[g]) for g in GROUPS},
                "costs": cost_means(summaries[n].result),
                "misses": miss_summary(summaries[n].result) if summaries[n].result.per_case else None,
            }
            for n in order
        },
        "comparisons": diff_rows,
        "references": [
            {**r, "random": interval_record(r["random"]), "bm25f": interval_record(r["bm25f"])}
            for r in reference_rows(report)
        ],
        "frontier": frontier,
    }
    (out / "results.json").write_text(json.dumps(clean(record), indent=1) + "\n", encoding="utf-8")


def clean(value: object) -> object:
    """JSON-safe and rounded: censored values become ``"censored"``, NaN becomes null."""
    if isinstance(value, Mapping):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [clean(v) for v in value]
    return rounded(value)
