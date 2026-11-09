"""Resolve every in-org issue/PR that the mined PRs reference, with its cross-reference timeline.

For each referenced item it fetches the type (issue or PR), title, body, dates and author, and,
for issues, every PR anywhere in GitHub that cross-referenced or connected to it, with its
repository and merge state. That lets a hub's label include PRs merged outside the mining window.

Only references that `build_cases.py` can use are resolved: those from non-bot, non-fork PRs
whose titles aren't backports or reverts, and not in a port, revert or supersedes context. A
batch of 50 items costs 1 GraphQL point (each item opens at most two connections).

    python3 scripts/expand_hubs.py --org grafana --mined ~/so/mined
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402
from same_org.orgs import in_owners, owners_of  # noqa: E402
from same_org.refs import EXCLUDED_CTX, PORT_TITLE, extract_refs, is_bot  # noqa: E402

ERROR: dict = {"error": True}

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


def usable_window_pr(pr: dict) -> bool:
    a = pr.get("author") or {}
    return not (
        pr["repository"].get("isFork")
        or is_bot(a.get("login"), a.get("__typename"))
        or PORT_TITLE.search(pr.get("title") or "")
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-error-share", type=float, default=0.005,
                    help="fail if more than this share of items still errors as single items")
    a = ap.parse_args()

    d = Path(a.mined).expanduser() / a.org
    prs = [json.loads(line) for line in gzip.open(d / "prs.jsonl.gz", "rt")]
    owners = owners_of(a.org)
    wanted: Counter[str] = Counter()
    usable = [pr for pr in prs if usable_window_pr(pr)]
    for pr in usable:
        repo = pr["repository"]["nameWithOwner"]
        for r in extract_refs(f"{pr['title']}\n{pr['body']}", repo):
            if r.owner.lower() in owners and r.context not in EXCLUDED_CTX:
                wanted[r.target] += 1
        for n in (pr.get("closingIssuesReferences") or {}).get("nodes") or []:
            if in_owners(n["repository"]["nameWithOwner"], owners):
                wanted[f"{n['repository']['nameWithOwner'].lower()}#{n['number']}"] += 1
    mined_urls = {p["url"].lower() for p in prs}
    targets = sorted(wanted)
    print(f"[expand] {a.org}: {len(usable)} of {len(prs)} PRs usable; they reference "
          f"{len(targets)} in-org items", file=sys.stderr)

    gh = GitHub(a.cache, max_5xx_retries=0)
    chunks = [targets[i : i + a.batch] for i in range(0, len(targets), a.batch)]

    def run(chunk: list[str]) -> dict[str, dict | None]:
        """Nodes by key. A batch that fails after retries (a 502 from an item with a huge
        timeline, say) is split in half and retried, down to single items marked `ERROR`."""
        items = []
        for t in chunk:
            rn, num = t.rsplit("#", 1)
            owner, name = rn.split("/", 1)
            items.append((owner, name, int(num)))
        try:
            res = gh.graphql(batch_query(items), kind="hub_batch")
        except RuntimeError:
            res = {}
        data = res.get("data") or {}
        if not data:
            if len(chunk) == 1:
                return {chunk[0]: ERROR}
            h = len(chunk) // 2
            return {**run(chunk[:h]), **run(chunk[h:])}
        return {t: (data.get(f"r{j}") or {}).get("issueOrPullRequest") for j, t in enumerate(chunk)}

    out_rows = []
    missing = errors = 0
    with ThreadPoolExecutor(a.workers) as ex:
        for done, got in enumerate(ex.map(run, chunks)):
            for t, node in got.items():
                if node is ERROR:
                    errors += 1
                    out_rows.append({"key": t, "missing": True, "error": True,
                                     "refs_from_window": wanted[t]})
                    continue
                if node is None:
                    missing += 1
                    out_rows.append({"key": t, "missing": True, "refs_from_window": wanted[t]})
                    continue
                node["key"] = t
                node["refs_from_window"] = wanted[t]
                node["in_window"] = (node.get("url") or "").lower() in mined_urls
                out_rows.append(node)
            if done % 25 == 0:
                print(f"[expand] {a.org} {done + 1}/{len(chunks)} batches "
                      f"spend={gh.spend.as_dict()}", file=sys.stderr, flush=True)

    with gzip.open(d / "hubs.jsonl.gz", "wt") as f:
        for r in out_rows:
            f.write(json.dumps(r) + "\n")
    trunc = sum(
        1 for r in out_rows
        if r.get("__typename") == "Issue" and r["timelineItems"]["totalCount"] > 100
    )
    summary = {
        "org": a.org, "window_prs": len(prs), "usable_prs": len(usable),
        "targets": len(targets), "resolved": len(out_rows) - missing,
        "missing": missing, "batch_errors": errors, "timeline_truncated": trunc,
        "types": Counter(r.get("__typename", "missing") for r in out_rows),
        "spend": gh.spend.as_dict(),
    }
    (d / "expand_spend.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    if errors > a.max_error_share * len(targets):
        sys.exit(f"{errors} items lost to errors, over {a.max_error_share:.1%} of "
                 f"{len(targets)}; rerun to top up")


if __name__ == "__main__":
    main()
