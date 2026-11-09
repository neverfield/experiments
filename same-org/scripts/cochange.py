"""How much of a change's target set an earlier co-change history already holds.

History is every multi-repo case of any label method (2 to 12 targets) whose first PR opened
before `--split`, minus cases that share a PR with the change being scored. Each change of
`--combo` whose first PR opened on or after the split, and isn't sweep-like, is scored:

- `all_pairs_seen`: every pair of its targets is a pair of targets of some history case;
- `any_pair_seen`: at least one pair is;
- `seed_recall`: seeded with one true target, the share of the other targets among the seed's
  history partners, averaged over seeds and then over changes;
- `partners_p50`: the median number of history partners a seed has (the candidates a
  co-change tool would return).

The window holds only months of history, so a real co-change index would hold more.

    python3 scripts/cochange.py --orgs grafana k8s --mined ~/so/mined --split 2026-08-01 \
        --out ~/so/cochange.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import COMBOS, changes, pr_meta, ts  # noqa: E402


def score(cases: list[dict], chs: list[dict], meta: dict, split) -> dict:
    hist = [c for c in cases if 2 <= c["n_targets"] <= 12 and c.get("first_created")
            and ts(c["first_created"]) < split]
    by_pair: dict[tuple, list[set]] = defaultdict(list)
    by_repo: dict[str, list[tuple[str, set]]] = defaultdict(list)
    for c in hist:
        prs = set(c["prs"])
        for a, b in combinations(sorted(set(c["targets"])), 2):
            by_pair[(a, b)].append(prs)
            by_repo[a].append((b, prs))
            by_repo[b].append((a, prs))
    rows = []
    for ch in chs:
        opened = [meta[p]["opened"] for p in ch["prs"] if p in meta]
        if ch["sweep_like"] or not opened or min(opened) < split:
            continue
        own = set(ch["prs"])
        seen = [any(not (s & own) for s in by_pair.get(pair, ()))
                for pair in combinations(ch["targets"], 2)]
        recalls, partners = [], []
        for seed in ch["targets"]:
            ps = {r for r, s in by_repo.get(seed, ()) if not (s & own)}
            others = set(ch["targets"]) - {seed}
            recalls.append(len(others & ps) / len(others))
            partners.append(len(ps))
        rows.append((all(seen), any(seen), statistics.mean(recalls), statistics.median(partners)))
    n = len(rows)
    return {"changes": n, "history_cases": len(hist),
            **({"all_pairs_seen": round(sum(r[0] for r in rows) / n, 3),
                "any_pair_seen": round(sum(r[1] for r in rows) / n, 3),
                "seed_recall": round(statistics.mean(r[2] for r in rows), 3),
                "partners_p50": statistics.median(r[3] for r in rows)} if n else {})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--combo", default="explicit", choices=sorted(COMBOS))
    ap.add_argument("--split", default="2026-08-01")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    split = ts(a.split + "T00:00:00Z")
    out = {"combo": a.combo, "split": a.split, "orgs": {}}
    for org in a.orgs:
        d = Path(a.mined).expanduser() / org
        cases = [json.loads(line) for line in gzip.open(d / "cases.jsonl.gz", "rt")]
        meta = pr_meta(d / "prs.jsonl.gz")
        out["orgs"][org] = score(cases, changes(cases, COMBOS[a.combo], 12, meta), meta, split)
        print(org, out["orgs"][org], file=sys.stderr)
    Path(a.out).expanduser().write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
