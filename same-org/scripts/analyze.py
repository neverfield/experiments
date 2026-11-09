"""Per-org tables for the feasibility report: case counts, target counts, request text, and
how far repo names alone get a ranker inside the org.

For issue-hub cases the request is the hub issue's title and body. "Pre-work" means the issue
was opened before the first linked PR. A request "names" a target when the target's repo name
appears in it as a whole token sequence (case-insensitive), with or without the owner.

The names-only ranker is BM25 over each candidate's name tokens (owner dropped), against the
request's tokens. The pool is every active, non-fork repo of the org from the census, plus the
case's targets. `names+desc` adds GitHub's description to each candidate.

    python3 scripts/analyze.py --orgs grafana hashicorp --mined ~/so/mined --census ~/so/census \
        --out ~/so/analysis.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.refs import clean  # noqa: E402

STOP = set(
    "a an and are as at be but by for from has have if in into is it its of on or that the "
    "this to was were will with we you i our not no can should would could when what which "
    "there their them they then than so do does did done also any all some more most use used "
    "using via per new add adds added support update updates fix fixes fixed issue issues pr "
    "please thanks thank hi hello see e g eg ie etc".split()
)


def tokens(s: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s or "")
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 1 and t not in STOP
            and not t.isdigit()]


class BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avg = sum(len(v) for v in docs.values()) / max(1, len(docs))
        df = Counter()
        for v in docs.values():
            df.update(set(v))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = {k: Counter(v) for k, v in docs.items()}

    def rank(self, query: list[str], rng: random.Random) -> list[str]:
        q = set(query)
        scores = {}
        for k, tf in self.tf.items():
            dl = len(self.docs[k])
            s = 0.0
            for t in q & tf.keys():
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
            scores[k] = s
        keys = list(scores)
        rng.shuffle(keys)
        return sorted(keys, key=lambda k: -scores[k])


def names_in(text: str, repo: str) -> bool:
    name = repo.split("/", 1)[1]
    return bool(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text, re.I))


def load(p: Path) -> list[dict]:
    with gzip.open(p, "rt") as f:
        return [json.loads(line) for line in f]


def active_pool(census: Path, org: str, as_of: datetime, days: int) -> dict[str, dict]:
    pool = {}
    for line in open(census / "repos" / f"{org}.jsonl"):
        r = json.loads(line)
        if r["archived"] or r["fork"] or r["disabled"] or not r["pushed_at"]:
            continue
        if datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) < as_of - timedelta(days=days):
            continue
        pool[r["full_name"].lower()] = r
    return pool


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--as-of", default="2026-11-09")
    ap.add_argument("--active-days", type=int, default=365)
    ap.add_argument("--max-targets", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    as_of = datetime.fromisoformat(a.as_of).replace(tzinfo=timezone.utc)
    census = Path(a.census).expanduser()
    result = {}
    for org in a.orgs:
        d = Path(a.mined).expanduser() / org
        cases = load(d / "cases.jsonl.gz")
        hubs = {h["key"]: h for h in load(d / "hubs.jsonl.gz")}
        pool = active_pool(census, org, as_of, a.active_days)
        all_repos = {}
        for line in open(census / "repos" / f"{org}.jsonl"):
            r = json.loads(line)
            all_repos[r["full_name"].lower()] = r
        rng = random.Random(a.seed)
        org_out = {"active_pool": len(pool), "methods": {}}
        for method in sorted({c["method"] for c in cases}):
            cs = [c for c in cases if c["method"] == method]
            multi = [c for c in cs if 2 <= c["n_targets"] <= a.max_targets]
            m = {
                "cases": len(cs),
                "single": sum(1 for c in cs if c["n_targets"] == 1),
                "t2": sum(1 for c in cs if c["n_targets"] == 2),
                "t3": sum(1 for c in cs if c["n_targets"] == 3),
                "t4plus": sum(1 for c in cs if c["n_targets"] >= 4),
                "over_max": sum(1 for c in cs if c["n_targets"] > a.max_targets),
                "distinct_targets_multi": len({t for c in multi for t in c["targets"]}),
                "targets_inactive_or_missing": sum(
                    1 for c in multi for t in c["targets"] if t not in pool),
            }
            m["single_rate"] = round(m["single"] / len(cs), 3) if cs else None
            if method.startswith("issue"):
                for label, group in (("all", cs), ("multi", multi)):
                    hs = [c["hub"] for c in group if c.get("hub")]
                    if not hs:
                        continue
                    m[f"{label}_pre_work"] = round(sum(h["pre_work"] for h in hs) / len(hs), 3)
                    m[f"{label}_meta_title"] = round(sum(h["meta_title"] for h in hs) / len(hs), 3)
                    m[f"{label}_hub_repo_is_target"] = round(
                        sum(1 for c in group if c["hub"]["repo"] in c["targets"]) / len(group), 3)
                    words = sorted(len(tokens(clean(hubs[c["group"]].get("body") or "")))
                                   for c in group)
                    m[f"{label}_body_words_median"] = words[len(words) // 2]
                    m[f"{label}_body_under_20_words"] = round(
                        sum(1 for w in words if w < 20) / len(words), 3)
                vis = Counter()
                ranks = {"names": [], "names+desc": []}
                docs_n = {k: tokens(k.split("/", 1)[1]) for k in pool}
                docs_d = {k: tokens(k.split("/", 1)[1] + " " + (pool[k].get("description") or ""))
                          for k in pool}
                for c in multi:
                    if not c["hub"]["pre_work"]:
                        continue
                    h = hubs[c["group"]]
                    text = f"{h.get('title') or ''}\n{clean(h.get('body') or '')}"
                    hit = [names_in(text, t) for t in c["targets"]]
                    vis["all" if all(hit) else "some" if any(hit) else "none"] += 1
                    for label, docs in (("names", docs_n), ("names+desc", docs_d)):
                        dd = dict(docs)
                        for t in c["targets"]:
                            if t not in dd:
                                r = all_repos.get(t, {})
                                extra = r.get("description") or "" if label == "names+desc" else ""
                                dd[t] = tokens(t.split("/", 1)[1] + " " + extra)
                        order = BM25(dd).rank(tokens(text), rng)
                        pos = {k: i for i, k in enumerate(order)}
                        ranks[label].append(max(pos[t] for t in c["targets"]) + 1)
                m["pre_work_multi_requests"] = sum(vis.values())
                m["visibility"] = dict(vis)
                for label, rs in ranks.items():
                    if rs:
                        n = len(rs)
                        m[f"{label}_cr@10"] = round(sum(r <= 10 for r in rs) / n, 3)
                        m[f"{label}_cr@50"] = round(sum(r <= 50 for r in rs) / n, 3)
                        m[f"{label}_last_rank_median"] = sorted(rs)[n // 2]
                        m[f"{label}_pool_median"] = len(pool)
            org_out["methods"][method] = m
        result[org] = org_out
    Path(a.out).expanduser().write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
