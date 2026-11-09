"""Resolve every in-org issue/PR that the mined PRs reference, with its cross-reference timeline.

For each referenced item it fetches the type (issue or PR), title, body, dates and author, and,
for issues, every PR anywhere in GitHub that cross-referenced or connected to it, with its
repository and merge state. That lets a hub's label include PRs merged outside the mining window.

    python3 scripts/expand_hubs.py --org grafana --mined ~/so/mined
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402
from same_org.refs import extract_refs  # noqa: E402

PR_FIELDS = """number title createdAt mergedAt merged url
  author { login __typename } repository { nameWithOwner }
  headRefName baseRefName changedFiles"""

ITEM = f"""
  __typename
  ... on Issue {{
    number title body createdAt closedAt state url
    author {{ login __typename }}
    labels(first: 20) {{ nodes {{ name }} }}
    timelineItems(itemTypes: [CROSS_REFERENCED_EVENT, CONNECTED_EVENT], first: 100) {{
      totalCount
      nodes {{
        __typename
        ... on CrossReferencedEvent {{
          createdAt willCloseTarget
          source {{ __typename ... on PullRequest {{ {PR_FIELDS} }} }}
        }}
        ... on ConnectedEvent {{
          createdAt
          subject {{ __typename ... on PullRequest {{ {PR_FIELDS} }} }}
        }}
      }}
    }}
  }}
  ... on PullRequest {{ {PR_FIELDS} body }}
"""


def batch_query(items: list[tuple[str, str, int]]) -> str:
    parts = []
    for i, (owner, name, num) in enumerate(items):
        parts.append(
            f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
            f"{{ issueOrPullRequest(number: {num}) {{ {ITEM} }} }}"
        )
    return "query { " + "\n".join(parts) + " }"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    ap.add_argument("--batch", type=int, default=20)
    a = ap.parse_args()

    d = Path(a.mined).expanduser() / a.org
    prs = [json.loads(line) for line in gzip.open(d / "prs.jsonl.gz", "rt")]
    org = a.org.lower()
    wanted: Counter[str] = Counter()
    for pr in prs:
        repo = pr["repository"]["nameWithOwner"]
        for r in extract_refs(f"{pr['title']}\n{pr['body']}", repo):
            if r.owner.lower() == org:
                wanted[r.target] += 1
        for n in (pr.get("closingIssuesReferences") or {}).get("nodes") or []:
            if n["repository"]["nameWithOwner"].lower().startswith(org + "/"):
                wanted[f"{n['repository']['nameWithOwner'].lower()}#{n['number']}"] += 1
    mined_urls = {p["url"].lower() for p in prs}
    targets = sorted(wanted)
    print(f"[expand] {a.org}: {len(prs)} PRs reference {len(targets)} in-org items",
          file=sys.stderr)

    gh = GitHub(a.cache)
    out_rows = []
    missing = errors = 0
    for i in range(0, len(targets), a.batch):
        chunk = targets[i : i + a.batch]
        items = []
        for t in chunk:
            rn, num = t.rsplit("#", 1)
            owner, name = rn.split("/", 1)
            items.append((owner, name, int(num)))
        res = gh.graphql(batch_query(items), kind="hub_batch")
        data = res.get("data") or {}
        if not data and res.get("errors"):
            errors += len(chunk)
            continue
        for j, t in enumerate(chunk):
            node = (data.get(f"r{j}") or {}).get("issueOrPullRequest")
            if node is None:
                missing += 1
                out_rows.append({"key": t, "missing": True, "refs_from_window": wanted[t]})
                continue
            node["key"] = t
            node["refs_from_window"] = wanted[t]
            node["in_window"] = (node.get("url") or "").lower() in mined_urls
            out_rows.append(node)
        if (i // a.batch) % 25 == 0:
            print(f"[expand] {i + len(chunk)}/{len(targets)} spend={gh.spend.as_dict()}",
                  file=sys.stderr, flush=True)

    with gzip.open(d / "hubs.jsonl.gz", "wt") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    trunc = sum(
        1 for r in out_rows
        if r.get("__typename") == "Issue" and r["timelineItems"]["totalCount"] > 100
    )
    summary = {
        "org": a.org, "targets": len(targets), "resolved": len(out_rows) - missing,
        "missing": missing, "batch_errors": errors, "timeline_truncated": trunc,
        "types": Counter(r.get("__typename", "missing") for r in out_rows),
        "spend": gh.spend.as_dict(),
    }
    (d / "expand_spend.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    if errors:
        sys.exit(f"{errors} items lost to batch errors; rerun to top up")


if __name__ == "__main__":
    main()
