"""Score a hand-check of `sample_review.py`'s sheet: precision per label method, with Wilson
95% intervals, pooled over orgs and per org.

`verdicts.json` maps each sampled case ID to {"v", "kind", "unsure", "why"}, as defined in
`REVIEW.md`:

  same     every target repo belongs to one piece of work
  partial  at least two target repos belong to one piece of work, plus spurious ones
  not      fewer than two target repos belong to one piece of work

Strict precision counts `same`; lenient counts `same` and `partial`. Kinds are tallied per cell.
The script stops if the verdicts and the sample's case IDs differ. `--second` takes other
raters' verdicts on a subset and reports agreement and Cohen's kappa against the main file.

    python3 scripts/score_review.py --review ~/so/review-a ~/so/review-b \
        --second ~/so/review-a/verdicts-b.json --out ~/so/scores.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

VERDICTS = ("same", "partial", "not")


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - h) / d, 3), round((c + h) / d, 3)]


def cell(entries: list) -> dict:
    """Entries are verdict dicts ({"v", "kind", "unsure"}) or bare verdict strings."""
    es = [e if isinstance(e, dict) else {"v": e} for e in entries]
    vs = [e["v"] for e in es]
    n = len(vs)
    s = sum(v == "same" for v in vs)
    p = sum(v == "partial" for v in vs)
    u = sum(e["v"] == "same" and e.get("kind") != "sweep" for e in es)
    return {
        "n": n, "same": s, "partial": p, "not": n - s - p,
        "strict": round(s / n, 3) if n else None, "strict_ci": wilson(s, n),
        "lenient": round((s + p) / n, 3) if n else None, "lenient_ci": wilson(s + p, n),
        "same_not_sweep": round(u / n, 3) if n else None, "same_not_sweep_ci": wilson(u, n),
        "unsure": sum(bool(e.get("unsure")) for e in es),
        "kinds_same": dict(Counter(e.get("kind", "?") for e in es if e["v"] == "same")),
        "kinds_not": dict(Counter(e.get("kind", "?") for e in es if e["v"] == "not")),
    }


def agreement(a: dict, b: dict) -> dict:
    """Two raters' verdicts on the cases both judged."""
    both = sorted(a.keys() & b.keys())
    if not both:
        return {"n": 0}
    va, vb = [a[k]["v"] for k in both], [b[k]["v"] for k in both]
    n = len(both)
    po = sum(x == y for x, y in zip(va, vb)) / n
    ca, cb = Counter(va), Counter(vb)
    pe = sum(ca[v] * cb[v] for v in VERDICTS) / (n * n)
    same_a = [x == "same" for x in va]
    same_b = [x == "same" for x in vb]
    return {"n": n, "agree": round(po, 3),
            "kappa": round((po - pe) / (1 - pe), 3) if pe < 1 else None,
            "agree_same_vs_rest": round(sum(x == y for x, y in zip(same_a, same_b)) / n, 3),
            "disagreements": [k for k, x, y in zip(both, va, vb) if x != y]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", nargs="+", required=True,
                    help="directories, each with sample.json and verdicts.json; block IDs must "
                         "be distinct across them")
    ap.add_argument("--second", nargs="*",
                    help="other raters' verdict files on a subset, for agreement against the main one")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sample = {"case_ids": [], "blocks": {}, "cell_pool": {}}
    raw: dict = {}
    for r in a.review:
        d = Path(r).expanduser()
        s = json.loads((d / "sample.json").read_text())
        v = json.loads((d / "verdicts.json").read_text())
        keys = set(s["blocks"]) if s.get("blocks") else set(s["case_ids"])
        missing, extra = keys - v.keys(), v.keys() - keys
        if missing or extra:
            raise SystemExit(f"{d}: verdicts don't match the sample: {len(missing)} missing, "
                             f"{len(extra)} extra, e.g. {sorted(missing | extra)[:3]}")
        if keys & raw.keys():
            raise SystemExit(f"{d}: block IDs repeat across review directories")
        raw.update(v)
        sample["case_ids"] += s["case_ids"]
        sample["blocks"].update(s.get("blocks") or {c: [c] for c in s["case_ids"]})
        sample["cell_pool"].update(s.get("cell_pool", {}))
    blocks = sample["blocks"]
    verdicts = {cid: raw[b] for b, cids in blocks.items() for cid in cids}
    ids = set(sample["case_ids"])
    missing, extra = ids - verdicts.keys(), verdicts.keys() - ids
    if missing or extra:
        raise SystemExit(f"verdicts don't match the sample: {len(missing)} missing, "
                         f"{len(extra)} extra, e.g. {sorted(missing | extra)[:3]}")
    bad = [k for k, v in verdicts.items() if v["v"] not in VERDICTS]
    if bad:
        raise SystemExit(f"unknown verdicts on {bad[:3]}")

    by_method, by_org_method, by_org = defaultdict(list), defaultdict(list), defaultdict(list)
    for cid in sample["case_ids"]:
        org, method = cid.split(":")[:2]
        v = verdicts[cid]
        by_method[method].append(v)
        by_org_method[f"{org}|{method}"].append(v)
        by_org[org].append(v)
    out = {
        "cases": len(ids), "blocks": len(raw),
        "by_method": {m: cell(v) for m, v in sorted(by_method.items())},
        "by_org": {o: cell(v) for o, v in sorted(by_org.items())},
        "by_org_method": {k: cell(v) for k, v in sorted(by_org_method.items())},
        "cell_pool": sample.get("cell_pool", {}),
    }
    for second in a.second or []:
        b = json.loads(Path(second).expanduser().read_text())
        out.setdefault("agreement", {})[Path(second).name] = agreement(raw, b)
    Path(a.out).expanduser().write_text(json.dumps(out, indent=1))
    for m, c in out["by_method"].items():
        print(f"{m:13s} n={c['n']:3d} strict={c['strict']} {c['strict_ci']} "
              f"lenient={c['lenient']} {c['lenient_ci']}")


if __name__ == "__main__":
    main()
