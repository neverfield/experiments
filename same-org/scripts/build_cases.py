"""Group an org's merged PRs into candidate cases, one grouping per label method.

Methods (a case is a set of merged, non-bot PRs in the org's own non-fork repos):

  issue-close   PRs that close the same in-org issue: a closing keyword, the sidebar link, or a
                timeline event that will close it.
  issue-strong  issue-close plus PRs whose text links the issue as "part of", "depends on",
                "companion" or "follow-up".
  issue-ref     PRs that reference the same in-org issue in any way but a port, revert or
                supersedes, including timeline cross-references from comments and commits.
  pr-link       Connected components of PR-to-PR references across repos, ports and reverts
                excluded. `pr-link-dep` keeps only "depends on" and "companion" edges.
  key           PRs whose titles carry the same ticket key (FLINK-123, OCPBUGS-45, KEP-4381).
  branch        PRs by one author from the same non-generic branch name, merged within 30 days.

A case's targets are the distinct repositories of its PRs. Writes `cases.jsonl.gz` and
`case_summary.json` next to the mined PRs.

    python3 scripts/build_cases.py --org grafana --mined ~/so/mined --census ~/so/census
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.orgs import in_owners, load_census, owners_of  # noqa: E402
from same_org.refs import (  # noqa: E402
    EXCLUDED_CTX,
    PORT_TITLE,
    extract_keys,
    extract_refs,
    is_bot,
    is_generic_branch,
)

META_TITLE = re.compile(r"\b(?:meta|epic|tracking|umbrella|roadmap|tracker|placeholder)\b", re.I)
STRONG_CTX = {"close", "partof", "depends", "companion", "followup"}
METHODS = ["issue-close", "issue-strong", "issue-ref", "pr-link", "pr-link-dep", "key", "branch"]


def ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def load_jsonl_gz(p: Path) -> list[dict]:
    with gzip.open(p, "rt") as f:
        return [json.loads(line) for line in f]


class UF:
    def __init__(self):
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def pr_key(repo: str, num: int) -> str:
    return f"{repo.lower()}#{num}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--key-min-numbers", type=int, default=5,
                    help="a key prefix counts only if this many distinct keys use it")
    ap.add_argument("--branch-days", type=int, default=30)
    a = ap.parse_args()

    owners = owners_of(a.org)
    d = Path(a.mined).expanduser() / a.org
    prs_raw = load_jsonl_gz(d / "prs.jsonl.gz")
    hubs = {h["key"]: h for h in load_jsonl_gz(d / "hubs.jsonl.gz")} if (
        d / "hubs.jsonl.gz").exists() else {}
    repos = load_census(a.census, a.org)

    def own_repo(name: str) -> bool:
        n = name.lower()
        if not in_owners(n, owners):
            return False
        r = repos.get(n)
        return not (r and r.get("fork"))

    # Every merged PR we know about: the window's, plus those met in hub timelines.
    prs: dict[str, dict] = {}
    for p in prs_raw:
        k = pr_key(p["repository"]["nameWithOwner"], p["number"])
        p["_window"] = True
        prs[k] = p
    for h in hubs.values():
        if h.get("__typename") == "PullRequest" and h.get("merged"):
            k = pr_key(h["repository"]["nameWithOwner"], h["number"])
            prs.setdefault(k, {**h, "_window": False})
        if h.get("__typename") != "Issue":
            continue
        for ev in h["timelineItems"]["nodes"]:
            src = ev.get("source") or ev.get("subject") or {}
            if src.get("__typename") == "PullRequest" and src.get("merged"):
                k = pr_key(src["repository"]["nameWithOwner"], src["number"])
                prs.setdefault(k, {**src, "_window": False})

    def usable(p: dict) -> bool:
        a_ = p.get("author") or {}
        return (
            own_repo(p["repository"]["nameWithOwner"])
            and not is_bot(a_.get("login"), a_.get("__typename"))
            and not PORT_TITLE.search(p.get("title") or "")
        )

    window = {k: p for k, p in prs.items() if p["_window"]}
    window_refs = {
        k: extract_refs(f"{p['title']}\n{p['body']}", p["repository"]["nameWithOwner"])
        for k, p in window.items() if usable(p)
    }
    groups: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    edge_ctx: dict[str, Counter] = defaultdict(Counter)

    # Issue hubs: collect every context in which each PR links each hub.
    link_ctx: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for hk, h in hubs.items():
        if h.get("__typename") != "Issue" or not own_repo(hk.split("#")[0]):
            continue
        for ev in h["timelineItems"]["nodes"]:
            src = ev.get("source") or ev.get("subject") or {}
            if src.get("__typename") != "PullRequest" or not src.get("merged"):
                continue
            k = pr_key(src["repository"]["nameWithOwner"], src["number"])
            if not usable(prs[k]):
                continue
            closes = ev["__typename"] == "ConnectedEvent" or ev.get("willCloseTarget")
            link_ctx[hk][k].add("close" if closes else "timeline")
    for k, refs in window_refs.items():
        p = window[k]
        for n in (p.get("closingIssuesReferences") or {}).get("nodes") or []:
            hk = pr_key(n["repository"]["nameWithOwner"], n["number"])
            if hubs.get(hk, {}).get("__typename") == "Issue" and own_repo(hk.split("#")[0]):
                link_ctx[hk][k].add("close")
        for r in refs:
            h = hubs.get(r.target)
            if not h or h.get("__typename") != "Issue" or not own_repo(r.target.split("#")[0]):
                continue
            link_ctx[r.target][k].add("close" if r.closes else r.context)
    for hk, members in link_ctx.items():
        for k, ctxs in members.items():
            if prs[k]["_window"] and ctxs <= EXCLUDED_CTX | {"timeline"} and ctxs & EXCLUDED_CTX:
                continue
            groups["issue-ref"][hk].add(k)
            if "close" in ctxs:
                groups["issue-close"][hk].add(k)
            if ctxs & STRONG_CTX:
                groups["issue-strong"][hk].add(k)

    # pr-link
    uf_all, uf_dep = UF(), UF()
    edges: list[tuple[str, str, str]] = []
    for k, refs in window_refs.items():
        repo = window[k]["repository"]["nameWithOwner"].lower()
        for r in refs:
            h = hubs.get(r.target)
            if not h or h.get("__typename") != "PullRequest" or not h.get("merged"):
                continue
            if r.target.split("#")[0] == repo or r.target not in prs:
                continue
            if not usable(prs[r.target]):
                continue
            edge_ctx["pr-link"][r.context] += 1
            if r.context in EXCLUDED_CTX:
                continue
            uf_all.union(k, r.target)
            edges.append((k, r.target, r.context))
            if r.context in ("depends", "companion"):
                uf_dep.union(k, r.target)
    case_edges: dict[str, list] = defaultdict(list)
    for name, uf in (("pr-link", uf_all), ("pr-link-dep", uf_dep)):
        for x in list(uf.p):
            groups[name][f"{name}:{uf.find(x)}"].add(x)
        for src, dst, ctx in edges:
            if name == "pr-link" or ctx in ("depends", "companion"):
                case_edges[f"{name}:{uf.find(src)}"].append([src, dst, ctx])

    # key
    key_prs: dict[str, set[str]] = defaultdict(set)
    for k in window_refs:
        for key in extract_keys(window[k]["title"]):
            key_prs[key].add(k)
    prefix_n = Counter(key.split("-")[0] for key in key_prs)
    for key, ks in key_prs.items():
        if prefix_n[key.split("-")[0]] >= a.key_min_numbers:
            groups["key"][key] = ks

    # branch
    by_branch: dict[tuple[str, str], set[str]] = defaultdict(set)
    for k in window_refs:
        p = window[k]
        if not is_generic_branch(p.get("headRefName")):
            by_branch[((p.get("author") or {}).get("login", ""), p["headRefName"])].add(k)
    for (login, br), ks in by_branch.items():
        repos_ = {x.split("#")[0] for x in ks}
        if len(repos_) < 2:
            continue
        times = sorted(ts(prs[x]["mergedAt"]) for x in ks)
        if times[-1] - times[0] <= timedelta(days=a.branch_days):
            groups["branch"][f"{login}:{br}"] = ks

    # Write cases.
    rows = []
    summary: dict[str, dict] = {}
    for method in METHODS:
        gs = groups.get(method, {})
        sizes = Counter()
        for gid, ks in gs.items():
            targets = sorted({x.split("#")[0] for x in ks})
            hub = hubs.get(gid) if method.startswith("issue") else None
            first_pr = min((ts(prs[x].get("createdAt")) for x in ks if prs[x].get("createdAt")),
                           default=None)
            row = {
                "case_id": f"{a.org}:{method}:{gid}",
                "org": a.org, "method": method, "group": gid,
                "targets": targets, "n_targets": len(targets),
                "prs": sorted(ks),
                "window_prs": sum(1 for x in ks if prs[x]["_window"]),
                "authors": len({(prs[x].get("author") or {}).get("login") for x in ks}),
            }
            merged = sorted(t for t in (ts(prs[x].get("mergedAt")) for x in ks) if t)
            row["span_days"] = (merged[-1] - merged[0]).days if merged else None
            row["first_merged"] = merged[0].isoformat() if merged else None
            if gid in case_edges:
                row["edges"] = case_edges[gid]
            if hub:
                created = ts(hub.get("createdAt"))
                row["link_ctx"] = {x: sorted(link_ctx[gid][x]) for x in sorted(ks)}
                row["hub"] = {
                    "url": hub.get("url"), "title": hub.get("title"),
                    "createdAt": hub.get("createdAt"), "repo": gid.split("#")[0],
                    "labels": [n["name"] for n in (hub.get("labels") or {}).get("nodes", [])],
                    "body_chars": len(hub.get("body") or ""),
                    "timeline_total": hub["timelineItems"]["totalCount"],
                    "pre_work": bool(created and first_pr and created < first_pr),
                    "meta_title": bool(META_TITLE.search(hub.get("title") or "")),
                    "author_is_bot": is_bot((hub.get("author") or {}).get("login"),
                                            (hub.get("author") or {}).get("__typename")),
                }
            rows.append(row)
            sizes[min(len(targets), 5)] += 1
        n = sum(sizes.values())
        summary[method] = {
            "cases": n,
            "by_targets": {("5+" if s == 5 else str(s)): c for s, c in sorted(sizes.items())},
            "single_repo_rate": round(sizes[1] / n, 3) if n else None,
            "multi_repo": n - sizes[1],
        }
    with gzip.open(d / "cases.jsonl.gz", "wt") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    # PR-level view: which usable window PRs sit in a multi-repo case, per method.
    usable_window = set(window_refs)
    in_multi: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r["n_targets"] >= 2:
            in_multi[r["method"]].update(set(r["prs"]) & usable_window)
    out = {
        "org": a.org,
        "owners": list(owners),
        "window_prs": len(window),
        "window_prs_usable": len(usable_window),
        "window_prs_bot": sum(1 for p in window.values()
                              if is_bot((p.get("author") or {}).get("login"),
                                        (p.get("author") or {}).get("__typename"))),
        "window_repos_with_merged_pr": len({k.split("#")[0] for k in usable_window}),
        "window_prs_in_multi_repo_case": {m: len(v) for m, v in sorted(in_multi.items())},
        "window_prs_in_any_multi_repo_case": len(set().union(*in_multi.values()))
        if in_multi else 0,
        "pr_link_edge_contexts": dict(edge_ctx["pr-link"]),
        "key_prefixes": dict(prefix_n.most_common(15)),
        "methods": summary,
    }
    (d / "case_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
