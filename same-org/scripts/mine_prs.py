"""Fetch every merged PR in an org over a date window, via GraphQL search.

Search returns at most 1,000 results per query, so the window is split in halves until each
piece fits. Writes `<out>/<org>/prs.jsonl.gz` and `<out>/<org>/mine_spend.json`.

    python3 scripts/mine_prs.py --org grafana --since 2026-06-01 --until 2026-08-31 --out ~/so/mined
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402

COUNT_Q = """query($q: String!) { search(query: $q, type: ISSUE, first: 1) { issueCount } }"""

PAGE_Q = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 100, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number title body createdAt mergedAt url
        author { login __typename }
        repository { nameWithOwner isFork isArchived }
        headRefName baseRefName changedFiles additions deletions
        closingIssuesReferences(first: 10) { nodes { number repository { nameWithOwner } } }
      }
    }
  }
}
"""

FMT = "%Y-%m-%dT%H:%M:%SZ"


def q_for(org: str, a: datetime, b: datetime) -> str:
    return f"org:{org} is:pr is:merged merged:{a.strftime(FMT)}..{b.strftime(FMT)}"


def count(gh: GitHub, org: str, a: datetime, b: datetime) -> int:
    out = gh.graphql(COUNT_Q, {"q": q_for(org, a, b)}, kind="search_count")
    return out["data"]["search"]["issueCount"]


def ranges(gh: GitHub, org: str, a: datetime, b: datetime, cap: int = 1000):
    n = count(gh, org, a, b)
    if n <= cap or (b - a) <= timedelta(minutes=10):
        if n > cap:
            print(f"[mine] {org} {a}..{b}: {n} results exceed the cap", file=sys.stderr)
        yield a, b, n
        return
    mid = a + (b - a) / 2
    mid = mid.replace(microsecond=0)
    yield from ranges(gh, org, a, mid, cap)
    yield from ranges(gh, org, mid + timedelta(seconds=1), b, cap)


def fetch_range(gh: GitHub, org: str, a: datetime, b: datetime):
    after = None
    while True:
        out = gh.graphql(PAGE_Q, {"q": q_for(org, a, b), "after": after}, kind="search_page")
        if "data" not in out or out["data"] is None:
            raise RuntimeError(f"search failed: {json.dumps(out)[:300]}")
        s = out["data"]["search"]
        for n in s["nodes"]:
            if n:
                yield n
        if not s["pageInfo"]["hasNextPage"]:
            return
        after = s["pageInfo"]["endCursor"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--since", required=True, help="first merge day, YYYY-MM-DD (UTC)")
    ap.add_argument("--until", required=True, help="last merge day, inclusive")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    ap.add_argument("--count-only", action="store_true")
    a = ap.parse_args()

    gh = GitHub(a.cache)
    start = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(a.until).replace(tzinfo=timezone.utc) + timedelta(
        hours=23, minutes=59, seconds=59)
    if a.count_only:
        n = count(gh, a.org, start, end)
        print(json.dumps({"org": a.org, "since": a.since, "until": a.until, "merged_prs": n,
                          "spend": gh.spend.as_dict()}))
        return
    out = Path(a.out).expanduser() / a.org
    out.mkdir(parents=True, exist_ok=True)
    pieces = list(ranges(gh, a.org, start, end))
    expected = sum(n for _, _, n in pieces)
    seen: dict[str, dict] = {}
    for lo, hi, _ in pieces:
        for pr in fetch_range(gh, a.org, lo, hi):
            seen[pr["url"]] = pr
    tmp = out / "prs.jsonl.gz.tmp"
    with gzip.open(tmp, "wt") as f:
        for pr in seen.values():
            f.write(json.dumps(pr) + "\n")
    tmp.replace(out / "prs.jsonl.gz")
    summary = {
        "org": a.org, "since": a.since, "until": a.until, "pieces": len(pieces),
        "expected": expected, "fetched": len(seen), "spend": gh.spend.as_dict(),
    }
    (out / "mine_spend.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    if len(seen) < 0.98 * expected:
        sys.exit(f"fetched {len(seen)} of {expected} expected PRs; rerun to top up")


if __name__ == "__main__":
    main()
