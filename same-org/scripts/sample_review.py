"""Draw a seeded sample of multi-repo cases per org and method, and render a review sheet.

The sheet shows, per case, the hub (if any) and each PR's repo, title, size and a body excerpt,
with the link wording that joined it, so a reviewer can judge whether the PRs are parts of one
change. Bodies come from the mined PRs and hubs; only PRs met in hub timelines are fetched.
Verdicts go in a JSON file that `score_review.py` reads; the sample's case IDs are written next
to the sheet so the verdicts can be checked against it.

    python3 scripts/sample_review.py --orgs grafana hashicorp --mined ~/so/mined \
        --per-cell 6 --seed 20261109 --out ~/so/review
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

METHODS = ["issue-close", "issue-strong", "issue-ref", "pr-link", "pr-link-dep", "key", "branch"]
BODY_Q = """number title body createdAt mergedAt changedFiles additions deletions
  author { login } repository { nameWithOwner } headRefName baseRefName"""


def squash(s: str | None, n: int) -> str:
    t = re.sub(r"\s+", " ", clean(s)).strip()
    return t[:n] + ("…" if len(t) > n else "")


def pr_key(repo: str, num: int) -> str:
    return f"{repo.lower()}#{num}"


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
    ap.add_argument("--methods", nargs="+", default=METHODS)
    ap.add_argument("--per-cell", type=int, default=6)
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--max-targets", type=int, default=12,
                    help="skip cases with more target repos than this (reported separately)")
    ap.add_argument("--max-prs-shown", type=int, default=12)
    ap.add_argument("--parts", type=int, default=1, help="also split the sheet for parallel raters")
    ap.add_argument("--overlap", type=int, default=0,
                    help="also write this many random blocks to sheet-overlap.md for a second rater")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    sample = []
    hubs_by_org: dict[str, dict] = {}
    known: dict[str, dict] = {}
    cell_pool = {}
    for org in a.orgs:
        d = Path(a.mined).expanduser() / org
        cases = [json.loads(line) for line in gzip.open(d / "cases.jsonl.gz", "rt")]
        hubs = [json.loads(line) for line in gzip.open(d / "hubs.jsonl.gz", "rt")]
        hubs_by_org[org] = {h["key"]: h for h in hubs}
        for h in hubs:
            if h.get("__typename") == "PullRequest":
                known[pr_key(h["repository"]["nameWithOwner"], h["number"])] = h
        for p in gzip.open(d / "prs.jsonl.gz", "rt"):
            p = json.loads(p)
            known[pr_key(p["repository"]["nameWithOwner"], p["number"])] = p
        for m in a.methods:
            pool = sorted(
                (c for c in cases
                 if c["method"] == m and 2 <= c["n_targets"] <= a.max_targets),
                key=lambda c: c["case_id"],
            )
            cell_pool[f"{org}|{m}"] = len(pool)
            sample.extend(rng.sample(pool, min(a.per_cell, len(pool))))

    shown = {k for c in sample for k in c["prs"][: a.max_prs_shown]}
    need = sorted(k for k in shown if k not in known)
    gh = GitHub(a.cache)
    pr_info = {**{k: known[k] for k in shown if k in known}, **fetch_prs(gh, need)}

    # One block per distinct (PRs, targets), shown under a shuffled ID that hides the method.
    groups: dict[tuple, list[dict]] = {}
    for c in sample:
        groups.setdefault((tuple(c["prs"]), tuple(c["targets"])), []).append(c)
    order = sorted(groups)
    random.Random(a.seed + 1).shuffle(order)
    blocks = {f"R{i + 1:03d}": groups[k] for i, k in enumerate(order)}

    def render(bid: str, cs: list[dict]) -> list[str]:
        c = next((x for x in cs if x.get("hub")), cs[0])
        lines = [f"## {bid}"]
        lines.append(f"targets ({c['n_targets']}): {', '.join(c['targets'])} | prs {len(c['prs'])}"
                     f" | span {c.get('span_days')} days | authors {c.get('authors')}")
        h = c.get("hub")
        if h:
            hub = hubs_by_org[c["org"]].get(c["group"], {})
            lines.append(f"hub: {h['repo']} | {h['title']} | created {h['createdAt'][:10]} | "
                         f"labels {h['labels'][:6]} | pre_work={h['pre_work']}")
            lines.append(f"hub body: {squash(hub.get('body'), 400)}")
        for e in next((x.get("edges") for x in cs if x.get("edges")), [])[:8]:
            lines.append(f"edge: {e[0]} -> {e[1]} ({e[2]})")
        for k in c["prs"][: a.max_prs_shown]:
            p = pr_info.get(k)
            ctx = (c.get("link_ctx") or {}).get(k)
            ctx_s = f" link={','.join(ctx)}" if ctx else ""
            if not p:
                lines.append(f"- {k}: (not fetched){ctx_s}")
                continue
            lines.append(
                f"- {k} [{(p.get('mergedAt') or '')[:10]}] "
                f"{(p.get('author') or {}).get('login', '?')} br={p.get('headRefName')} "
                f"files={p.get('changedFiles')}{ctx_s}: {p['title']}"
            )
            lines.append(f"    {squash(p.get('body'), 300)}")
        if len(c["prs"]) > a.max_prs_shown:
            lines.append(f"- … {len(c['prs']) - a.max_prs_shown} more PRs")
        lines.append("")
        return lines

    ids = list(blocks)
    parts = [ids[i:: a.parts] for i in range(a.parts)]
    files = {"sheet.md": ids}
    if a.parts > 1:
        files.update({f"sheet-part{i + 1}.md": p for i, p in enumerate(parts)})
    if a.overlap:
        files["sheet-overlap.md"] = sorted(random.Random(a.seed + 2).sample(ids, min(a.overlap, len(ids))))
    for name, bids in files.items():
        lines = [f"# Review sheet: {len(bids)} blocks, seed {a.seed}", ""]
        for bid in bids:
            lines += render(bid, blocks[bid])
        (out / name).write_text("\n".join(lines))
    (out / "sample.json").write_text(json.dumps(
        {"seed": a.seed, "per_cell": a.per_cell, "max_targets": a.max_targets,
         "cell_pool": cell_pool, "case_ids": [c["case_id"] for c in sample],
         "blocks": {b: [c["case_id"] for c in cs] for b, cs in blocks.items()},
         "files": files}, indent=1))
    print(json.dumps({"sampled": len(sample), "blocks": len(blocks), "prs_shown": len(shown),
                      "prs_fetched": len(need), "spend": gh.spend.as_dict()}))


if __name__ == "__main__":
    main()
