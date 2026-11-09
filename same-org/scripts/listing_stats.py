"""Summarise org listings written by org_census.py, offline: active counts, descriptions,
name-prefix concentration and size spread among active repos.

    python3 scripts/listing_stats.py --census ~/so/census --orgs apache microsoft google hashicorp
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.orgs import load_census  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", required=True)
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--as-of", default="2026-11-09")
    ap.add_argument("--active-days", type=int, default=365)
    a = ap.parse_args()
    cut = datetime.fromisoformat(a.as_of).replace(tzinfo=timezone.utc) - timedelta(
        days=a.active_days)
    out = {}
    for org in a.orgs:
        rows = list(load_census(a.census, org).values())
        act = [
            r for r in rows
            if not (r["archived"] or r["fork"] or r["disabled"]) and r["pushed_at"]
            and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) >= cut
        ]
        first = Counter(re.split(r"[-_.]", r["name"].lower())[0] for r in act)
        sizes = sorted(r["size"] or 0 for r in act)

        def q(p: float, s=sizes) -> int:
            return s[min(len(s) - 1, int(p * len(s)))] if s else 0

        out[org] = {
            "listed": len(rows),
            f"active_{a.active_days}d": len(act),
            "active_no_description": round(sum(1 for r in act if not (r["description"] or "").strip())
                                           / max(1, len(act)), 3),
            "active_with_topics": round(sum(1 for r in act if r["topics"]) / max(1, len(act)), 3),
            "top_name_prefixes": first.most_common(6),
            "top6_prefix_share": round(sum(c for _, c in first.most_common(6)) / max(1, len(act)), 3),
            "size_kb_p10_p50_p90": [q(0.1), q(0.5), q(0.9)],
            "languages_top5": Counter(r["language"] for r in act).most_common(5),
            "issues_enabled": round(sum(1 for r in act if r["has_issues"]) / max(1, len(act)), 3),
        }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
