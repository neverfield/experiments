"""Score a hand-check of `sample_review.py`'s sheet: precision per label method, with Wilson
95% intervals, pooled over orgs and per org.

`verdicts.json` maps each sampled case ID to {"v": "same" | "partial" | "not", "why": "..."}:

  same     the PRs are parts of one change, and every target repo belongs to it
  partial  at least two target repos belong to one change, plus spurious ones
  not      the PRs aren't parts of one change (or fewer than two repos belong)

Strict precision counts `same`; lenient counts `same` and `partial`. The script stops if the
verdicts and the sample's case IDs differ.

    python3 scripts/score_review.py --review ~/so/review --out ~/so/review/scores.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
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


def cell(vs: list[str]) -> dict:
    n = len(vs)
    s = sum(v == "same" for v in vs)
    p = sum(v == "partial" for v in vs)
    return {
        "n": n, "same": s, "partial": p, "not": n - s - p,
        "strict": round(s / n, 3) if n else None, "strict_ci": wilson(s, n),
        "lenient": round((s + p) / n, 3) if n else None, "lenient_ci": wilson(s + p, n),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", required=True, help="directory with sample.json and verdicts.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    d = Path(a.review).expanduser()
    sample = json.loads((d / "sample.json").read_text())
    verdicts = json.loads((d / "verdicts.json").read_text())
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
        v = verdicts[cid]["v"]
        by_method[method].append(v)
        by_org_method[f"{org}|{method}"].append(v)
        by_org[org].append(v)
    out = {
        "cases": len(ids),
        "by_method": {m: cell(v) for m, v in sorted(by_method.items())},
        "by_org": {o: cell(v) for o, v in sorted(by_org.items())},
        "by_org_method": {k: cell(v) for k, v in sorted(by_org_method.items())},
        "cell_pool": sample.get("cell_pool", {}),
    }
    Path(a.out).expanduser().write_text(json.dumps(out, indent=1))
    for m, c in out["by_method"].items():
        print(f"{m:13s} n={c['n']:3d} strict={c['strict']} {c['strict_ci']} "
              f"lenient={c['lenient']} {c['lenient_ci']}")


if __name__ == "__main__":
    main()
