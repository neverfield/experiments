"""Measure what a packet fetch costs over git instead of the REST API.

For each repo: a depth-1, blobless, no-checkout clone (commit and trees only), then a sparse
checkout of the README, docs and manifest paths, which fetches just those blobs. Records wall
time and bytes on disk for each step. Git over github.com doesn't draw on the REST quota.

    python3 scripts/clone_cost.py --repos-file ~/so/smoke/docs/grafana.jsonl --limit 20 \
        --out ~/so/clone-cost.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

SPARSE = [
    "/README*", "/*/README*", "/*/*/README*", "/CONTRIBUTING*", "/CHANGELOG*", "/ARCHITECTURE*",
    "/doc/**", "/docs/**", "/documentation/**", "/wiki/**",
    "**/package.json", "**/go.mod", "**/Cargo.toml", "**/pom.xml", "**/build.gradle*",
    "**/pyproject.toml", "**/setup.py", "**/setup.cfg", "**/requirements*.txt", "**/*.csproj",
    "**/Chart.yaml", "**/composer.json", "**/Gemfile",
    "!**/node_modules/**", "!**/vendor/**", "!**/third_party/**",
]


def du(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def run(cmd: list[str], cwd: Path | None = None) -> tuple[float, int]:
    t0 = time.monotonic()
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    return time.monotonic() - t0, r.returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos-file", required=True,
                    help="JSONL with a `repo` field (doc_profile output) or one owner/name a line")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    names = []
    for line in open(Path(a.repos_file).expanduser()):
        line = line.strip()
        if line:
            names.append(json.loads(line)["repo"] if line.startswith("{") else line)
    names = names[: a.limit]
    rows = []
    for name in names:
        tmp = Path(tempfile.mkdtemp(prefix="clone-cost-"))
        dst = tmp / "r"
        url = f"https://github.com/{name}.git"
        t_clone, rc1 = run(["git", "clone", "--quiet", "--depth", "1", "--filter=blob:none",
                            "--no-checkout", url, str(dst)])
        row = {"repo": name, "clone_s": round(t_clone, 2), "clone_rc": rc1}
        if rc1 == 0:
            row["git_bytes_trees"] = du(dst / ".git")
            run(["git", "sparse-checkout", "init", "--no-cone"], cwd=dst)
            (dst / ".git" / "info" / "sparse-checkout").write_text("\n".join(SPARSE) + "\n")
            t_co, rc2 = run(["git", "checkout", "--quiet"], cwd=dst)
            row.update({"checkout_s": round(t_co, 2), "checkout_rc": rc2,
                        "git_bytes_total": du(dst / ".git"),
                        "files": sum(1 for f in dst.rglob("*") if f.is_file()
                                     and ".git" not in f.parts)})
        rows.append(row)
        print(json.dumps(row), flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    out = Path(a.out).expanduser()
    with open(out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    ok = [r for r in rows if r.get("checkout_rc") == 0]
    if ok:
        tot = sorted(r["clone_s"] + r["checkout_s"] for r in ok)
        print(json.dumps({"repos": len(rows), "ok": len(ok),
                          "seconds_p50": round(tot[len(tot) // 2], 2),
                          "seconds_mean": round(sum(tot) / len(tot), 2),
                          "seconds_max": round(tot[-1], 2),
                          "mb_mean": round(sum(r["git_bytes_total"] for r in ok) / len(ok) / 1e6, 2)}))


if __name__ == "__main__":
    main()
