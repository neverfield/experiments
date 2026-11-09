"""Profile README, docs and manifests per repo from one git-tree request each, and measure how
well doc volume alone separates an org's multi-repo targets from its other repos.

Uses the same path rules as the repo-discovery packet builder (README up to 4 directories
deep, docs under doc/docs/documentation/wiki up to 5 deep or root guides, package manifests),
but reads sizes from the tree instead of fetching files. The default branch comes from the
census, so each repo costs one REST request. Trees over GitHub's 100,000-entry or 7 MB limit
come back truncated; those are flagged.

Roles: `target` (repos in the org's multi-repo cases), `active` (a seeded sample of the org's
other active repos) and `busy` (other repos that merged a usable PR in the mining window, an
activity-matched control). The summary gives each feature's AUC for target against each pool.

    python3 scripts/doc_profile.py --org grafana --mined ~/so/mined --census ~/so/census \
        --out ~/so/docs/grafana.jsonl
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402
from same_org.orgs import load_census  # noqa: E402
from same_org.refs import PORT_TITLE, is_bot  # noqa: E402

DOC_SUFFIX = r"(?:\.(?:md|markdown|mdx|rst|txt|adoc|asciidoc))"
README_RE = re.compile(rf"^(?:[^/]+/){{0,4}}README{DOC_SUFFIX}?$", re.I)
ROOT_README_RE = re.compile(rf"^README{DOC_SUFFIX}?$", re.I)
ROOT_GUIDE_RE = re.compile(
    rf"^(?:CONTRIBUTING|CHANGELOG|CHANGES|HISTORY|ARCHITECTURE|DESIGN|DEVELOPMENT|DEVELOPING|"
    rf"HACKING|GOVERNANCE|SECURITY|UPGRADING|MIGRATION|NEWS|FAQ|USAGE|INSTALL){DOC_SUFFIX}?$",
    re.I,
)
DOCS_DIR_RE = re.compile(
    rf"^(?:[^/]+/){{0,4}}(?:doc|docs|documentation|wiki)/(?:[^/]+/){{0,4}}[^/]+{DOC_SUFFIX}$",
    re.I,
)
MANIFESTS = {
    "package.json", "go.mod", "cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts",
    "composer.json", "pyproject.toml", "setup.py", "setup.cfg", "gemfile", "pipfile",
    "requirements.txt", "chart.yaml", "pubspec.yaml", "mix.exs", "project.clj", "build.sbt",
    "package.swift", "podfile", "csproj", "cmakelists.txt", "meson.build", "makefile",
}
SKIP_DIR_RE = re.compile(
    r"(?:^|/)(?:node_modules|vendor|third_party|dist|build|\.git|bower_components)/", re.I)
FEATURES = ["docs_bytes", "readme_root_bytes", "manifests", "paths", "size_kb"]


def profile(tree: list[dict]) -> dict:
    readme_root = docs_bytes = docs_files = manifests = paths = 0
    for e in tree:
        if e.get("type") != "blob":
            continue
        p = e["path"]
        paths += 1
        if SKIP_DIR_RE.search(p):
            continue
        size = int(e.get("size") or 0)
        base = p.rsplit("/", 1)[-1].lower()
        if ROOT_README_RE.match(p) and size <= 256_000:
            readme_root = max(readme_root, size)
        elif README_RE.match(p) or ROOT_GUIDE_RE.match(p) or DOCS_DIR_RE.match(p):
            if size <= 256_000:
                docs_bytes += size
                docs_files += 1
        if base in MANIFESTS or base.endswith(".csproj") or base.startswith("requirements"):
            if not re.search(r"(?:^|/)(?:test|tests|testdata|examples?|fixtures?)/", p, re.I):
                manifests += 1
    return {
        "readme_root_bytes": readme_root,
        "docs_bytes": docs_bytes + readme_root,
        "docs_files": docs_files,
        "manifests": manifests,
        "paths": paths,
    }


def auc(pos: list[float], neg: list[float]) -> float | None:
    """P(a random positive scores above a random negative), ties counted half."""
    if not pos or not neg:
        return None
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank_sum, i = 0.0, 0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        mid = (i + j + 1) / 2
        rank_sum += mid * sum(1 for k in range(i, j) if allv[k][1])
        i = j
    n1, n0 = len(pos), len(neg)
    return round((rank_sum - n1 * (n1 + 1) / 2) / (n1 * n0), 3)


def median(xs: list[float]) -> float | None:
    s = sorted(xs)
    return s[len(s) // 2] if s else None


def pick(a, repos: dict[str, dict]) -> list[tuple[str, str]]:
    rng = random.Random(a.seed)
    d = Path(a.mined).expanduser() / a.org
    cases = [json.loads(x) for x in gzip.open(d / "cases.jsonl.gz", "rt")]
    targets = sorted({t for c in cases if c["method"] in a.methods
                      and 2 <= c["n_targets"] <= a.max_targets for t in c["targets"]
                      if t in repos})
    if len(targets) > a.max_target_repos:
        targets = sorted(rng.sample(targets, a.max_target_repos))
    cut = datetime.fromisoformat(a.as_of).replace(tzinfo=timezone.utc) - timedelta(days=365)
    active = sorted(
        k for k, r in repos.items()
        if not (r["archived"] or r["fork"] or r["disabled"]) and r["pushed_at"]
        and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) >= cut
    )
    all_targets = {t for c in cases if c["n_targets"] >= 2 for t in c["targets"]}
    busy = set()
    for line in gzip.open(d / "prs.jsonl.gz", "rt"):
        p = json.loads(line)
        au = p.get("author") or {}
        if is_bot(au.get("login"), au.get("__typename")) or PORT_TITLE.search(p["title"] or ""):
            continue
        busy.add(p["repository"]["nameWithOwner"].lower())
    others = [k for k in active if k not in all_targets]
    busy_others = sorted(k for k in busy if k in repos and k not in all_targets
                         and not repos[k]["fork"])
    out = [(t, "target") for t in targets]
    out += [(k, "active") for k in rng.sample(others, min(a.n_random, len(others)))]
    out += [(k, "busy") for k in rng.sample(busy_others, min(a.n_random, len(busy_others)))]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--methods", nargs="+", default=["issue-strong", "pr-link-dep", "pr-link",
                                                      "branch"])
    ap.add_argument("--max-targets", type=int, default=12)
    ap.add_argument("--max-target-repos", type=int, default=150)
    ap.add_argument("--n-random", type=int, default=60)
    ap.add_argument("--as-of", default="2026-11-09")
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    a = ap.parse_args()

    repos = load_census(a.census, a.org)
    chosen = pick(a, repos)
    gh = GitHub(a.cache)
    rows = []
    for name, role in chosen:
        meta = repos[name]
        br = meta.get("default_branch") or "HEAD"
        st, tree = gh.rest(f"/repos/{meta['full_name']}/git/trees/{br}?recursive=1", kind="tree")
        row = {"repo": name, "role": role, "status": st, "size_kb": meta.get("size") or 0,
               "description": bool((meta.get("description") or "").strip())}
        if st == 200 and tree:
            row["truncated"] = bool(tree.get("truncated"))
            row.update(profile(tree.get("tree") or []))
        rows.append(row)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    ok = [r for r in rows if r["status"] == 200 and "docs_bytes" in r]
    by_role = {role: [r for r in ok if r["role"] == role] for role in ("target", "active", "busy")}
    summary = {"org": a.org, "methods": a.methods, "profiled": len(ok), "failed": len(rows) - len(ok),
               "truncated": sum(1 for r in ok if r.get("truncated")),
               "n": {k: len(v) for k, v in by_role.items()}, "median": {}, "auc_target_vs": {}}
    for f_ in FEATURES:
        summary["median"][f_] = {k: median([r[f_] for r in v]) for k, v in by_role.items()}
        summary["auc_target_vs"][f_] = {
            pool: auc([r[f_] for r in by_role["target"]], [r[f_] for r in by_role[pool]])
            for pool in ("active", "busy")
        }
    summary["spend"] = gh.spend.as_dict()
    out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
