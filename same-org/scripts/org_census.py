"""Count each org's public repos and how many are active.

Active means not archived, not a fork, not disabled, and pushed within `--active-days` of
`--as-of`. Writes one JSONL row per repo (`repos/<org>.jsonl`) and a summary table.

    python3 scripts/org_census.py --orgs apache microsoft ... --out ~/so/census --as-of 2026-11-09
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402

KEEP = (
    "name", "full_name", "archived", "fork", "disabled", "is_template", "pushed_at", "created_at",
    "size", "description", "topics", "language", "stargazers_count", "open_issues_count",
    "default_branch", "has_issues", "mirror_url", "visibility",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--as-of", default="2026-11-09")
    ap.add_argument("--active-days", type=int, nargs="+", default=[180, 365])
    ap.add_argument("--list-max", type=int, default=20000,
                    help="skip the full listing for orgs with more public repos than this")
    ap.add_argument("--cache", default="~/so-cache")
    a = ap.parse_args()

    gh = GitHub(a.cache)
    out = Path(a.out).expanduser()
    (out / "repos").mkdir(parents=True, exist_ok=True)
    as_of = datetime.fromisoformat(a.as_of).replace(tzinfo=timezone.utc)
    rows = []
    for org in a.orgs:
        status, meta = gh.rest(f"/orgs/{org}", kind="org")
        if status != 200:
            status, meta = gh.rest(f"/users/{org}", kind="org")
        if status != 200 or not meta:
            print(f"{org}: not found ({status})", file=sys.stderr)
            continue
        row = {"org": org, "type": meta.get("type"), "public_repos": meta.get("public_repos")}
        if (meta.get("public_repos") or 0) <= a.list_max:
            kind = "orgs" if meta.get("type") == "Organization" else "users"
            repos = [
                {k: r.get(k) for k in KEEP}
                for r in gh.rest_pages(f"/{kind}/{org}/repos?type=all&sort=full_name", kind="repos")
            ]
            with open(out / "repos" / f"{org}.jsonl", "w") as f:
                for r in repos:
                    f.write(json.dumps(r) + "\n")
            live = [r for r in repos if not (r["archived"] or r["fork"] or r["disabled"])]
            row["listed"] = len(repos)
            row["archived"] = sum(1 for r in repos if r["archived"])
            row["forks"] = sum(1 for r in repos if r["fork"])
            for d in a.active_days:
                cut = as_of - timedelta(days=d)
                row[f"active_{d}d"] = sum(
                    1 for r in live
                    if r["pushed_at"] and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) >= cut
                )
            row["no_description"] = sum(1 for r in live if not (r["description"] or "").strip())
            row["empty"] = sum(1 for r in live if (r["size"] or 0) == 0)
        rows.append(row)
        print(json.dumps(row), flush=True)

    with open(out / "summary.json", "w") as f:
        json.dump({"as_of": a.as_of, "rows": rows, "spend": gh.spend.as_dict()}, f, indent=1)
    print(json.dumps(gh.spend.as_dict()), file=sys.stderr)


if __name__ == "__main__":
    main()
