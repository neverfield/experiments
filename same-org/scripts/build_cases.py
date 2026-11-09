"""Group an org's merged PRs into candidate cases, one grouping per label method.

Methods (a case is a set of merged, non-bot PRs in the org's own non-fork repos):

  issue-close  PRs that close the same in-org issue (closing keyword or linked in the sidebar).
  issue-ref    PRs that reference the same in-org issue in any way (timeline cross-references).
  pr-link      Connected components of PR-to-PR references across repos, ports and reverts
               excluded. `pr-link-dep` keeps only "depends on" and "companion" edges.
  key          PRs whose titles carry the same ticket key (FLINK-123, OCPBUGS-45, KEP-4381).
  branch       PRs by one author from the same non-generic branch name, merged within 30 days.

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
from same_org.refs import (  # noqa: E402
    extract_keys,
    extract_refs,
    is_bot,
    is_generic_branch,
)

PORT_TITLE = re.compile(
    r"^\s*(?:\[[^\]]*(?:backport|cherry|release-|\d+\.\d+)[^\]]*\]|backport|cherry-?pick|"
    r"revert\b|\[revert|automated cherry pick|.*\(backport\b|.*\bbackport (?:of|to)\b)",
    re.I,
)
META_TITLE = re.compile(r"\b(?:meta|epic|tracking|umbrella|roadmap|tracker|placeholder)\b", re.I)
EXCLUDED_CTX = {"port", "revert", "supersedes"}


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

    org = a.org.lower()
    d = Path(a.mined).expanduser() / a.org
    prs_raw = load_jsonl_gz(d / "prs.jsonl.gz")
    hubs = {h["key"]: h for h in load_jsonl_gz(d / "hubs.jsonl.gz")} if (
        d / "hubs.jsonl.gz").exists() else {}
    census = Path(a.census).expanduser() / "repos" / f"{a.org}.jsonl"
    repos = {}
    if census.exists():
        for line in open(census):
            r = json.loads(line)
            repos[r["full_name"].lower()] = r

    def own_repo(name: str) -> bool:
        n = name.lower()
        if not n.startswith(org + "/"):
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
    groups: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    edge_ctx: dict[str, Counter] = defaultdict(Counter)

    # issue-close and issue-ref
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
            groups["issue-ref"][hk].add(k)
            if ev["__typename"] == "ConnectedEvent" or ev.get("willCloseTarget"):
                groups["issue-close"][hk].add(k)
    for k, p in window.items():
        if not usable(p):
            continue
        repo = p["repository"]["nameWithOwner"]
        for n in (p.get("closingIssuesReferences") or {}).get("nodes") or []:
            hk = pr_key(n["repository"]["nameWithOwner"], n["number"])
            if hubs.get(hk, {}).get("__typename") == "Issue" and own_repo(hk.split("#")[0]):
                groups["issue-close"][hk].add(k)
                groups["issue-ref"][hk].add(k)
        for r in extract_refs(f"{p['title']}\n{p['body']}", repo):
            h = hubs.get(r.target)
            if not h or r.owner.lower() != org or not own_repo(r.target.split("#")[0]):
                continue
            if h.get("__typename") == "Issue" and r.context not in EXCLUDED_CTX:
                groups["issue-ref"][r.target].add(k)
                if r.closes:
                    groups["issue-close"][r.target].add(k)

    # pr-link
    uf_all, uf_dep = UF(), UF()
    for k, p in window.items():
        if not usable(p):
            continue
        repo = p["repository"]["nameWithOwner"]
        for r in extract_refs(f"{p['title']}\n{p['body']}", repo):
            h = hubs.get(r.target)
            if not h or h.get("__typename") != "PullRequest" or not h.get("merged"):
                continue
            if r.target.split("#")[0] == repo.lower() or r.target not in prs:
                continue
            if not usable(prs[r.target]):
                continue
            edge_ctx["pr-link"][r.context] += 1
            if r.context in EXCLUDED_CTX:
                continue
            uf_all.union(k, r.target)
            if r.context in ("depends", "companion"):
                uf_dep.union(k, r.target)
    for name, uf in (("pr-link", uf_all), ("pr-link-dep", uf_dep)):
        for x in list(uf.p):
            groups[name][f"{name}:{uf.find(x)}"].add(x)

    # key
    key_prs: dict[str, set[str]] = defaultdict(set)
    for k, p in window.items():
        if usable(p):
            for key in extract_keys(p["title"]):
                key_prs[key].add(k)
    prefix_n = Counter(key.split("-")[0] for key in key_prs)
    for key, ks in key_prs.items():
        if prefix_n[key.split("-")[0]] >= a.key_min_numbers:
            groups["key"][key] = ks

    # branch
    by_branch: dict[tuple[str, str], set[str]] = defaultdict(set)
    for k, p in window.items():
        if usable(p) and not is_generic_branch(p.get("headRefName")):
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
    for method, gs in groups.items():
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
            }
            if hub:
                created = ts(hub.get("createdAt"))
                row["hub"] = {
                    "url": hub.get("url"), "title": hub.get("title"),
                    "createdAt": hub.get("createdAt"), "repo": gid.split("#")[0],
                    "labels": [n["name"] for n in (hub.get("labels") or {}).get("nodes", [])],
                    "body_chars": len(hub.get("body") or ""),
                    "timeline_total": hub["timelineItems"]["totalCount"],
                    "pre_work": bool(created and first_pr and created < first_pr),
                    "meta_title": bool(META_TITLE.search(hub.get("title") or "")),
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

    usable_window = [k for k, p in window.items() if usable(p)]
    in_multi = set()
    for r in rows:
        if r["n_targets"] >= 2:
            in_multi.update(r["prs"])
    out = {
        "org": a.org,
        "window_prs": len(window),
        "window_prs_usable": len(usable_window),
        "window_prs_bot": sum(1 for p in window.values()
                              if is_bot((p.get("author") or {}).get("login"),
                                        (p.get("author") or {}).get("__typename"))),
        "window_repos_with_merged_pr": len({k.split("#")[0] for k in usable_window}),
        "window_prs_in_any_multi_repo_case": len(in_multi & set(usable_window)),
        "pr_link_edge_contexts": dict(edge_ctx["pr-link"]),
        "key_prefixes": dict(prefix_n.most_common(15)),
        "methods": summary,
    }
    (d / "case_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
