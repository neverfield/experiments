"""Profile README, docs and manifests for a set of repos from one git-tree request each.

Uses the same path rules as the repo-discovery packet builder (README up to 4 directories
deep, docs under doc/docs/documentation/wiki up to 5 deep or root guides, package manifests),
but reads sizes from the tree instead of fetching files, so the cost is one REST request per
repo. Trees over GitHub's 100,000-entry or 7 MB limit come back truncated; those are flagged.

    python3 scripts/doc_profile.py --repos-file targets.txt --out ~/so/docs/grafana.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from same_org.gh import GitHub  # noqa: E402

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


def profile(tree: list[dict]) -> dict:
    readme_root = readme_bytes = docs_bytes = docs_files = manifests = paths = 0
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
        if README_RE.match(p):
            readme_bytes += size
    return {
        "readme_root_bytes": readme_root,
        "docs_bytes": docs_bytes,
        "docs_files": docs_files,
        "manifests": manifests,
        "paths": paths,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-file", required=True, help="one owner/name per line, optional tab role")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default="~/so-cache")
    a = ap.parse_args()

    gh = GitHub(a.cache)
    rows = []
    for line in open(Path(a.repos_file).expanduser()):
        if not line.strip():
            continue
        name, _, role = line.strip().partition("\t")
        st, meta = gh.rest(f"/repos/{name}", kind="repo_meta")
        if st != 200 or not meta:
            rows.append({"repo": name, "role": role, "status": st})
            continue
        br = meta.get("default_branch") or "HEAD"
        st, tree = gh.rest(f"/repos/{name}/git/trees/{br}?recursive=1", kind="tree")
        if st != 200 or not tree:
            rows.append({"repo": name, "role": role, "status": st, "size_kb": meta.get("size")})
            continue
        row = {"repo": name, "role": role, "status": 200, "size_kb": meta.get("size"),
               "truncated": bool(tree.get("truncated")),
               "description": bool((meta.get("description") or "").strip()),
               "topics": len(meta.get("topics") or [])}
        row.update(profile(tree.get("tree") or []))
        rows.append(row)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(json.dumps({"repos": len(rows), "spend": gh.spend.as_dict()}))


if __name__ == "__main__":
    main()
