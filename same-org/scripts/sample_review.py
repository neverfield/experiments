"""Draw a seeded sample of multi-repo cases per org and method, and render a review sheet.

The sheet shows, per case, the hub (if any) and each PR's repo, title, size and a body excerpt,
so a reviewer can judge whether the PRs are parts of one change. Verdicts go in a JSON file
that `score_review.py` reads; the sample's case IDs are written next to the sheet so the
verdicts can be checked against it.

    python3 scripts/sample_review.py --orgs grafana hashicorp --mined ~/so/mined \
        --per-cell 8 --seed 20261109 --out ~/so/review
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402
from same_org.refs import clean  # noqa: E402

BODY_Q = """number title body createdAt mergedAt changedFiles additions deletions
  author { login } repository { nameWithOwner } headRefName baseRefName"""


def squash(s: str | None, n: int) -> str:
    t = re.sub(r"\s+", " ", clean(s)).strip()
    return t[:n] + ("…" if len(t) > n else "")


def fetch_prs(gh: GitHub, keys: list[str]) -> dict[str, dict]:
    out = {}
    for i in range(0, len(keys), 25):
        chunk = keys[i : i + 25]
        parts = []
        for j, k in enumerate(chunk):
            rn, num = k.rsplit("#", 1)
            owner, name = rn.split("/", 1)
            parts.append(f"p{j}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
                         f"{{ pullRequest(number: {num}) {{ {BODY_Q} }} }}")
        res = gh.graphql("query { " + "\n".join(parts) + " }", kind="review_prs")
        data = res.get("data") or {}
        for j, k in enumerate(chunk):
            node = (data.get(f"p{j}") or {}).get("pullRequest")
            if node:
                out[k] = node
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--methods", nargs="+",
                    default=["issue-close", "issue-ref", "pr-link", "pr-link-dep", "key",
                             "branch"])
    ap.add_argument("--per-cell", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--max-targets", type=int, default=12,
                    help="skip cases with more target repos than this (reported separately)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    gh = GitHub(a.cache)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    sample = []
    hubs_by_org = {}
    for org in a.orgs:
        d = Path(a.mined).expanduser() / org
        cases = [json.loads(line) for line in gzip.open(d / "cases.jsonl.gz", "rt")]
        hubs_by_org[org] = {
            json.loads(line)["key"]: json.loads(line)
            for line in gzip.open(d / "hubs.jsonl.gz", "rt")
        }
        for m in a.methods:
            pool = sorted(
                (c for c in cases
                 if c["method"] == m and 2 <= c["n_targets"] <= a.max_targets),
                key=lambda c: c["case_id"],
            )
            sample.extend(rng.sample(pool, min(a.per_cell, len(pool))))

    need = sorted({k for c in sample for k in c["prs"]})
    pr_info = fetch_prs(gh, need)
    lines = []
    for c in sample:
        lines.append(f"## {c['case_id']}")
        lines.append(f"targets ({c['n_targets']}): {', '.join(c['targets'])}")
        h = c.get("hub")
        if h:
            hub = hubs_by_org[c["org"]].get(c["group"], {})
            lines.append(f"hub: {h['repo']} | {h['title']} | created {h['createdAt'][:10]} | "
                         f"labels {h['labels'][:6]} | pre_work={h['pre_work']}")
            lines.append(f"hub body: {squash(hub.get('body'), 500)}")
        for k in c["prs"][:15]:
            p = pr_info.get(k)
            if not p:
                lines.append(f"- {k}: (not fetched)")
                continue
            lines.append(
                f"- {k} [{(p.get('mergedAt') or '')[:10]}] {p['author']['login'] if p.get('author') else '?'}"
                f" br={p.get('headRefName')} files={p.get('changedFiles')}: {p['title']}"
            )
            lines.append(f"    {squash(p.get('body'), 350)}")
        if len(c["prs"]) > 15:
            lines.append(f"- … {len(c['prs']) - 15} more PRs")
        lines.append("")
    (out / "sheet.md").write_text("\n".join(lines))
    (out / "sample.json").write_text(json.dumps(
        {"seed": a.seed, "per_cell": a.per_cell, "case_ids": [c["case_id"] for c in sample]},
        indent=1))
    print(json.dumps({"sampled": len(sample), "prs_fetched": len(pr_info),
                      "spend": gh.spend.as_dict()}))


if __name__ == "__main__":
    main()
