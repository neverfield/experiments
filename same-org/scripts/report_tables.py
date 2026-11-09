"""Print the feasibility report's tables, in markdown, from the pipeline's outputs.

    python3 scripts/report_tables.py --orgs microsoft apache k8s --mined ~/so/mined \
        --analysis ~/so/analysis.json --docs ~/so/docs --scores ~/so/review/scores.json \
        --listing ~/so/listing-stats-8.json --months 3 > ~/so/tables.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

METHODS = ["issue-close", "issue-strong", "issue-ref", "pr-link-dep", "pr-link", "key", "branch"]


def jload(p: Path) -> dict | None:
    return json.loads(p.read_text()) if p.exists() else None


def f(x, d=2) -> str:
    if x is None:
        return "–"
    if isinstance(x, float):
        return f"{x:.{d}f}"
    return f"{x:,}" if isinstance(x, int) else str(x)


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(f(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--analysis", required=True)
    ap.add_argument("--docs")
    ap.add_argument("--scores")
    ap.add_argument("--listing")
    ap.add_argument("--months", type=float, default=3.0)
    a = ap.parse_args()
    mined = Path(a.mined).expanduser()
    an = json.loads(Path(a.analysis).expanduser().read_text())
    listing = jload(Path(a.listing).expanduser()) if a.listing else {}
    orgs = [o for o in a.orgs if o in an]
    per_year = 12 / a.months
    out = []

    rows = []
    for o in orgs:
        cs = jload(mined / o / "case_summary.json") or {}
        ms = jload(mined / o / "mine_spend.json") or {}
        lst = (listing or {}).get(o, {})
        usable, total = cs.get("window_prs_usable"), cs.get("window_prs")
        rows.append([o, lst.get("listed"), an[o]["active_pool"], ms.get("expected"), ms.get("fetched"),
                     usable, round(cs.get("window_prs_bot", 0) / total, 2) if total else None,
                     cs.get("window_repos_with_merged_pr"),
                     round(cs.get("window_prs_in_any_multi_repo_case", 0) / usable, 3) if usable else None])
    out.append("### Orgs and PRs\n\n" + table(
        ["Org", "Listed", "Active pool", "PRs expected", "PRs fetched", "Usable PRs", "Bot share",
         "Repos with a merged PR", "Usable PRs in a multi-repo case"], rows))

    rows = []
    for o in orgs:
        m = an[o]["methods"]
        rows.append([o] + [m.get(k, {}).get("multi_kept", 0) for k in METHODS]
                    + [an[o]["changes"][c]["changes"] for c in ("strict", "links", "all")])
    out.append(f"### Multi-repo cases in {a.months:g} months (2 to 12 targets)\n\n" + table(
        ["Org"] + METHODS + ["Changes: strict", "links", "all"], rows))

    rows = []
    for o in orgs:
        ch = an[o]["changes"]
        for c in ("strict", "links", "explicit"):
            x = ch[c]
            top = x.get("top_target_set") or []
            rows.append([o, c, x["changes"], round(x["changes"] * per_year), x["t2"], x["t3"],
                         x["t4plus"], x["distinct_targets"], x["with_issue"], x["with_pre_work_issue"],
                         x.get("opened_within_2min"), x.get("sweep_like"), x.get("not_sweep_like"),
                         x.get("same_title"),
                         f'{x.get("top_target_set_share")} ({" + ".join(t.split("/")[1] for t in top)})'])
    out.append("### Distinct changes, sizes and request issues\n\n" + table(
        ["Org", "Combo", "Changes", "Per year", "2 targets", "3", "4+", "Distinct targets",
         "With a linked issue", "With a pre-work issue", "PRs opened within 2 min",
         "Sweep-like", "Not sweep-like", "Same title", "Top target set share"], rows))

    scores = json.loads(Path(a.scores).expanduser().read_text()) if a.scores else {}
    checked = (scores.get("by_method_unflagged") or {}).get("change-explicit")
    rows = []
    for size in (50, 100, 250, 500, 1000, 2000, 3000):
        big = [o for o in orgs if an[o]["active_pool"] >= size]
        xs = [an[o]["changes"]["explicit"] for o in big]
        n = sum(x["not_sweep_like"] for x in xs) * per_year
        rows.append([f"{size:,}", ", ".join(big) or "–", round(n),
                     round(sum(x.get("not_sweep_pre_work", 0) for x in xs) * per_year),
                     round(sum(x.get("not_sweep_t4plus", 0) for x in xs) * per_year)]
                    + ([f'{round(n * checked["same_not_sweep"]):,} ('
                        f'{round(n * checked["same_not_sweep_ci"][0]):,}–'
                        f'{round(n * checked["same_not_sweep_ci"][1]):,})'] if checked else []))
    out.append("### Explicit-link changes that aren't sweep-like, a year, by pool size\n\nAn org's "
               "changes can be scored at any pool size up to its active pool, by subsampling its "
               "other repos."
               + (f" Expected to pass the hand-check: changes a year times the share of unflagged "
                  f"`change-explicit` blocks rated `same` and not `sweep` "
                  f"({checked['same_not_sweep']}, n = {checked['n']}), with its 95% interval."
                  if checked else "") + "\n\n" + table(
        ["Pool size", "Orgs with a pool this large", "Changes a year", "With a pre-work issue",
         "4+ targets"] + (["Expected to pass the hand-check"] if checked else []), rows))

    rows = []
    for o in orgs:
        m = an[o]["methods"]
        usable = (jload(mined / o / "case_summary.json") or {}).get("window_prs_usable") or 0
        work = []
        for c in ("strict", "links"):
            x = an[o]["changes"][c]
            lone = usable - x.get("prs_in_changes", 0)
            work.append(round(lone / (lone + x["changes"]), 3) if lone + x["changes"] else None)
        rows.append([o] + [m.get(k, {}).get("single_rate") for k in ("issue-close", "issue-strong", "issue-ref")]
                    + [m.get(k, {}).get("cases") for k in ("issue-close", "issue-strong", "issue-ref")]
                    + work)
    out.append("### Single-repo rate\n\nIssue columns: share of issue-linked cases with one target "
               "repo. Work columns: lone PRs over lone PRs plus distinct changes, counting each "
               "PR outside a change as one piece of single-repo work.\n\n" + table(
        ["Org", "issue-close", "issue-strong", "issue-ref", "Cases: close", "strong", "ref",
         "Work: strict", "Work: links"], rows))

    rows = []
    for o in orgs:
        for src, x in (("links changes", an[o]["changes"]["links"]),
                       ("issue-strong", an[o]["methods"].get("issue-strong", {})),
                       ("issue-ref", an[o]["methods"].get("issue-ref", {}))):
            v = x.get("visibility", {})
            n = x.get("pre_work_multi_requests", 0)
            rows.append([o, src, n, v.get("all", 0), v.get("some", 0), v.get("none", 0),
                         x.get("names_cr@10"), x.get("names_cr@50"), x.get("names_last_rank_median"),
                         x.get("names+desc_cr@10"), x.get("names+desc_cr@50"), an[o]["active_pool"]])
    out.append("### Pre-work requests: do they name the targets, and how far do names get a ranker\n\n"
               + table(["Org", "Source", "Requests", "Name all", "Some", "None", "Names CR@10",
                        "CR@50", "Median last rank", "Names+desc CR@10", "CR@50", "Pool"], rows))

    rows = []
    for o in orgs:
        m = an[o]["methods"]
        lst = (listing or {}).get(o, {})
        rows.append([o, lst.get("active_no_description"), lst.get("top6_prefix_share"),
                     ", ".join(f"{p} {c}" for p, c in lst.get("top_name_prefixes", [])[:3])]
                    + [m.get(k, {}).get("multi_shared_prefix") for k in ("pr-link", "branch", "issue-ref")]
                    + [m.get(k, {}).get("multi_one_author") for k in ("pr-link", "branch")]
                    + [str(m.get("pr-link", {}).get("multi_span_days_p50_p90"))])
    out.append("### Names and metadata\n\n" + table(
        ["Org", "No description", "Top-6 prefix share", "Top prefixes", "Shared prefix: pr-link",
         "branch", "issue-ref", "One author: pr-link", "branch", "pr-link span p50, p90 (days)"], rows))

    if a.docs:
        rows = []
        for o in orgs:
            d = jload(Path(a.docs).expanduser() / f"{o}.summary.json")
            if not d:
                continue
            au, md = d["auc_target_vs"], d["median"]
            rows.append([o, d["n"]["target"], d["n"]["active"], d["n"]["busy"],
                         md["docs_bytes"]["target"], md["docs_bytes"]["active"], md["docs_bytes"]["busy"],
                         au["docs_bytes"]["active"], au["docs_bytes"]["busy"],
                         au["manifests"]["active"], au["size_kb"]["active"], au["size_kb"]["busy"],
                         d["truncated"]])
        out.append("### Doc volume: targets against the org's other repos\n\n" + table(
            ["Org", "Targets", "Active", "Busy", "Docs bytes p50: target", "active", "busy",
             "AUC docs: vs active", "vs busy", "AUC manifests vs active", "AUC size vs active",
             "vs busy", "Truncated trees"], rows))

    rows = []
    for o in orgs:
        ms = jload(mined / o / "mine_spend.json") or {}
        es = jload(mined / o / "expand_spend.json") or {}
        sp, se = ms.get("spend", {}), es.get("spend", {})
        rows.append([o, ms.get("fetched"), sp.get("graphql_points", 0) + sp.get("cache_hits", 0),
                     ms.get("wall_s"), sp.get("waits_s"), es.get("targets"),
                     se.get("graphql_points"), round(se.get("request_s", 0) + se.get("waits_s", 0)),
                     es.get("timeline_truncated")])
    out.append("### Mining cost\n\n" + table(
        ["Org", "PRs", "Search pages", "Mine wall s", "Waits s", "Hub items", "Hub points",
         "Hub s", "Timelines truncated"], rows))

    if a.scores:
        s = json.loads(Path(a.scores).expanduser().read_text())
        rows = [[m, c["n"], c["same"], c["partial"], c["not"], c["strict"], str(c["strict_ci"]),
                 c["lenient"], str(c["lenient_ci"]), c.get("same_not_sweep"),
                 str(c.get("same_not_sweep_ci")), c["unsure"],
                 ", ".join(f"{k} {v}" for k, v in sorted(c["kinds_same"].items(), key=lambda x: -x[1]))]
                for m, c in s["by_method"].items()]
        out.append("### Precision by label method (hand-check)\n\n" + table(
            ["Method", "n", "Same", "Partial", "Not", "Strict", "95% CI", "Lenient", "95% CI",
             "Same, not a sweep", "95% CI", "Unsure", "Kinds among same"], rows))
        if s.get("sweep_flag"):
            rows = [[name, Path(r).name, c.get("flag_kind", 0), c.get("flag_other", 0),
                     c.get("noflag_kind", 0), c.get("noflag_other", 0), c["precision"], c["recall"]]
                    for key, name in (("sweep_flag_v1", "sweep-like v1"),
                                      ("sweep_flag", "sweep-like v2"),
                                      ("same_title_flag", "same title"))
                    for r, c in (s.get(key) or {}).items()]
            out.append("### Title flags against the raters' kinds, per review batch\n\nSweep-like "
                       "flags count `sweep` as the kind; same title counts `mirror` or `sweep`. "
                       "Version 1 was tuned on batch A, version 2 on batches A and B.\n\n"
                       + table(["Flag", "Batch", "Flag, kind", "Flag, other", "No flag, kind",
                                "No flag, other", "Precision", "Recall"], rows))
            rows = [[m, c["n"], c["kept"], c["strict"], str(c["strict_ci"]), c["same_not_sweep"],
                     str(c["same_not_sweep_ci"])] for m, c in s["by_method_unflagged"].items()]
            out.append("### Precision after dropping sweep-like blocks\n\n" + table(
                ["Method", "n kept", "Share kept", "Strict", "95% CI", "Same, not a sweep",
                 "95% CI"], rows))
        rows = [[o, c["n"], c["strict"], str(c["strict_ci"]), c["lenient"], c.get("same_not_sweep")]
                for o, c in s["by_org"].items()]
        out.append("### Precision by org\n\n" + table(
            ["Org", "n", "Strict", "95% CI", "Lenient", "Same, not a sweep"], rows))
        for name, ag in (s.get("agreement") or {}).items():
            out.append(f"Agreement with `{name}`: n={ag['n']}, agree={ag.get('agree')}, "
                       f"kappa={ag.get('kappa')}, same-vs-rest agree={ag.get('agree_same_vs_rest')}")
    print("\n\n".join(out))


if __name__ == "__main__":
    main()
