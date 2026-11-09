"""Per-org tables for the feasibility report: case counts, target counts, request text, and
how far repo names alone get a ranker inside the org.

For issue-hub cases the request is the hub issue's title and body. "Pre-work" means the issue
was opened before the first linked PR. A request "names" a target when the target's repo name
appears in it as a whole token sequence (case-insensitive), with or without the owner.

The names-only ranker is BM25 over each candidate's name tokens (owner dropped), against the
request's tokens. The pool is every active, non-fork repo of the org from the census, plus the
case's targets. `names+desc` adds GitHub's description to each candidate. The pool is the census
as of `--as-of`, not as of each case's date.

"Shared prefix" means every target's name starts with the same token, after dropping a leading
token equal to the owner (`grafana-`, `opentelemetry-`): a name-prefix shortcut can find such
sets without reading the request.

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
from same_org.orgs import load_census, owners_of  # noqa: E402
from same_org.refs import clean  # noqa: E402

STOP = set(
    "a an and are as at be but by for from has have if in into is it its of on or that the "
    "this to was were will with we you i our not no can should would could when what which "
    "there their them they then than so do does did done also any all some more most use used "
    "using via per new add adds added support update updates fix fixes fixed issue issues pr "
    "please thanks thank hi hello see e g eg ie etc".split()
)
ISSUE_METHODS = ("issue-close", "issue-strong", "issue-ref")
COMBOS = {
    "strict": ("issue-strong", "pr-link-dep", "branch"),
    "links": ("issue-strong", "pr-link", "branch"),
    "explicit": ("issue-strong", "pr-link"),
    "all": ("issue-close", "issue-strong", "issue-ref", "pr-link", "pr-link-dep", "key", "branch"),
}
SWEEP_PREFIX = re.compile(r"^\W*(?:\[[^\]]*\]\s*)?(?:chore|ci|build|deps?|bump|revert|docs?)\b",
                          re.I)
SWEEP_WORDS = re.compile(
    r"\b(?:bump|dependabot|renovate|codeowners|licen[cs]e|copyright|github actions?|actions/|"
    r"\.github/workflows|ci workflows?|pre-commit|golangci|eslint|linter|linting|go ?1\.\d+\b|"
    r"node ?\d\d\b|toolchain|[np]?npm audit|yarn audit|cve-\d|vulnerab|sec ?vulns?|deps\b|"
    r"dependenc|security (?:fix|update|patch)|pin(?:ned|ning)? (?:to|actions|dependenc|versions?)|"
    r"unpin|shas?\b|(?:update|updating|upgrade) (?:the )?(?:go|node|module|modules|base image|image)\b|"
    r"changelogs?|release notes|version marker|post release|contributing|contributor guide|"
    r"build image)", re.I)


def sweep_like(titles: list[str]) -> bool:
    """A change whose PRs all carry one title, or all read as maintenance (conventional `chore`,
    `ci`, `build` or `deps` prefixes, dependency, toolchain, CI or license wording)."""
    ts_ = [t for t in titles if t]
    if len(ts_) < 2:
        return False
    if len({re.sub(r"[\W_]+", " ", t.lower()).strip() for t in ts_}) == 1:
        return True
    return all(SWEEP_PREFIX.search(t) or SWEEP_WORDS.search(t) for t in ts_)


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


def first_token(repo: str) -> str:
    owner, name = repo.lower().split("/", 1)
    parts = [p for p in re.split(r"[-_.]", name) if p]
    owner_toks = set(re.split(r"[-_.]", owner)) | {owner.replace("-", "")}
    if len(parts) > 1 and parts[0] in owner_toks:
        parts = parts[1:]
    return parts[0] if parts else name


def ts(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def changes(cases: list[dict], methods: tuple[str, ...], max_targets: int,
            meta: dict[str, dict]) -> list[dict]:
    """Distinct multi-repo changes: the methods' multi-repo cases joined wherever they share a
    PR. Each change lists the non-bot issue-strong hubs linked to any of its PRs (a single-repo
    issue case can still be the request for a multi-repo change), the seconds between its
    first and last PR being opened, and whether its titles look like a sweep (`meta` maps
    owner/repo#n to {"opened", "title"})."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    first: dict[str, datetime] = {}
    for c in cases:
        if c["method"] in methods and 2 <= c["n_targets"] <= max_targets:
            for p in c["prs"][1:]:
                parent[find(p)] = find(c["prs"][0])
            find(c["prs"][0])
    for c in cases:
        if c["method"] in methods and 2 <= c["n_targets"] <= max_targets and c.get("first_created"):
            r = find(c["prs"][0])
            t = ts(c["first_created"])
            first[r] = min(first.get(r, t), t)
    comps: dict[str, set[str]] = {}
    for p in list(parent):
        comps.setdefault(find(p), set()).add(p)
    reqs: dict[str, list[dict]] = {}
    for c in cases:
        if c["method"] == "issue-strong" and c.get("hub") and not c["hub"]["author_is_bot"]:
            for r in {find(p) for p in c["prs"] if p in parent}:
                reqs.setdefault(r, []).append(c)
    out = []
    for r, ps in comps.items():
        targets = sorted({p.split("#")[0] for p in ps})
        if not 2 <= len(targets) <= max_targets:
            continue
        pre = [c for c in reqs.get(r, []) if c["hub"]["createdAt"] and r in first
               and ts(c["hub"]["createdAt"]) < first[r]]
        pre.sort(key=lambda c: c["hub"]["createdAt"])
        ts_ = [meta[p]["opened"] for p in ps if p in meta]
        out.append({"targets": targets, "prs": sorted(ps), "has_issue": bool(reqs.get(r)),
                    "pre_work_issue": pre[0]["group"] if pre else None,
                    "opened_spread_s": (max(ts_) - min(ts_)).total_seconds() if ts_ else None,
                    "sweep_like": sweep_like([meta[p]["title"] for p in ps if p in meta])})
    return out


def pr_meta(path: Path) -> dict[str, dict]:
    out = {}
    for p in load(path):
        repo, _, n = p["url"].removeprefix("https://github.com/").partition("/pull/")
        out[f"{repo.lower()}#{n}"] = {"opened": ts(p["createdAt"]), "title": p.get("title") or ""}
    return out


def load(p: Path) -> list[dict]:
    with gzip.open(p, "rt") as f:
        return [json.loads(line) for line in f]


def active_pool(all_repos: dict[str, dict], as_of: datetime, days: int) -> dict[str, dict]:
    pool = {}
    for k, r in all_repos.items():
        if r["archived"] or r["fork"] or r["disabled"] or not r["pushed_at"]:
            continue
        if datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) < as_of - timedelta(days=days):
            continue
        pool[k] = r
    return pool


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orgs", nargs="+", required=True)
    ap.add_argument("--mined", required=True)
    ap.add_argument("--census", required=True)
    ap.add_argument("--as-of", default="2026-11-09")
    ap.add_argument("--active-days", type=int, default=365)
    ap.add_argument("--max-targets", type=int, default=12)
    ap.add_argument("--max-span-days", type=int, default=None,
                    help="also drop multi-repo cases whose PRs' merges span more days than this")
    ap.add_argument("--seed", type=int, default=20261109)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    as_of = datetime.fromisoformat(a.as_of).replace(tzinfo=timezone.utc)
    result = {}
    for org in a.orgs:
        d = Path(a.mined).expanduser() / org
        cases = load(d / "cases.jsonl.gz")
        hubs = {h["key"]: h for h in load(d / "hubs.jsonl.gz")}
        all_repos = load_census(a.census, org)
        pool = active_pool(all_repos, as_of, a.active_days)
        non_archived = sum(1 for r in all_repos.values() if not (r["archived"] or r["fork"]))
        rng = random.Random(a.seed)
        org_out = {"owners": list(owners_of(org)), "active_pool": len(pool),
                   "non_archived_non_fork": non_archived, "methods": {}}
        docs_n = {k: tokens(k.split("/", 1)[1]) for k in pool}
        docs_d = {k: tokens(k.split("/", 1)[1] + " " + (pool[k].get("description") or ""))
                  for k in pool}

        def score_requests(items: list[tuple[str, list[str]]]) -> dict:
            """Request = the hub issue's title and body. Visibility of target names in it, and
            the names-only BM25 ranker's CompleteRecall over the org's pool."""
            vis = Counter()
            ranks = {"names": [], "names+desc": []}
            for hub_key, targets in items:
                h = hubs[hub_key]
                text = f"{h.get('title') or ''}\n{clean(h.get('body') or '')}"
                hit = [names_in(text, t) for t in targets]
                vis["all" if all(hit) else "some" if any(hit) else "none"] += 1
                for label, docs in (("names", docs_n), ("names+desc", docs_d)):
                    dd = dict(docs)
                    for t in targets:
                        if t not in dd:
                            r = all_repos.get(t, {})
                            extra = (r.get("description") or "") if label == "names+desc" else ""
                            dd[t] = tokens(t.split("/", 1)[1] + " " + extra)
                    order = BM25(dd).rank(tokens(text), rng)
                    pos = {k: i for i, k in enumerate(order)}
                    ranks[label].append(max(pos[t] for t in targets) + 1)
            out = {"pre_work_multi_requests": sum(vis.values()), "visibility": dict(vis)}
            for label, rs in ranks.items():
                if rs:
                    n = len(rs)
                    out[f"{label}_cr@10"] = round(sum(r <= 10 for r in rs) / n, 3)
                    out[f"{label}_cr@50"] = round(sum(r <= 50 for r in rs) / n, 3)
                    out[f"{label}_last_rank_median"] = sorted(rs)[n // 2]
            return out

        for method in sorted({c["method"] for c in cases}):
            cs = [c for c in cases if c["method"] == method]
            multi = [c for c in cs if 2 <= c["n_targets"] <= a.max_targets
                     and (a.max_span_days is None or (c.get("span_days") or 0) <= a.max_span_days)]
            spans = sorted(c.get("span_days") or 0 for c in multi)
            m = {
                "cases": len(cs),
                "single": sum(1 for c in cs if c["n_targets"] == 1),
                "t2": sum(1 for c in cs if c["n_targets"] == 2),
                "t3": sum(1 for c in cs if c["n_targets"] == 3),
                "t4plus": sum(1 for c in cs if c["n_targets"] >= 4),
                "over_max": sum(1 for c in cs if c["n_targets"] > a.max_targets),
                "multi_kept": len(multi),
                "multi_span_days_p50_p90": [spans[len(spans) // 2], spans[int(0.9 * (len(spans) - 1))]]
                if spans else None,
                "multi_one_author": round(sum(1 for c in multi if c.get("authors") == 1)
                                          / len(multi), 3) if multi else None,
                "distinct_targets_multi": len({t for c in multi for t in c["targets"]}),
                "targets_inactive_or_missing": sum(
                    1 for c in multi for t in c["targets"] if t not in pool),
                "multi_shared_prefix": round(
                    sum(1 for c in multi if len({first_token(t) for t in c["targets"]}) == 1)
                    / len(multi), 3) if multi else None,
            }
            m["single_rate"] = round(m["single"] / len(cs), 3) if cs else None
            if method in ISSUE_METHODS:
                for label, group in (("all", cs), ("multi", multi)):
                    hs = [c["hub"] for c in group if c.get("hub")]
                    if not hs:
                        continue
                    m[f"{label}_pre_work"] = round(sum(h["pre_work"] for h in hs) / len(hs), 3)
                    m[f"{label}_meta_title"] = round(sum(h["meta_title"] for h in hs) / len(hs), 3)
                    m[f"{label}_bot_hub"] = round(
                        sum(h.get("author_is_bot", False) for h in hs) / len(hs), 3)
                    m[f"{label}_hub_repo_is_target"] = round(
                        sum(1 for c in group if c["hub"]["repo"] in c["targets"]) / len(group), 3)
                    words = sorted(len(tokens(clean(hubs[c["group"]].get("body") or "")))
                                   for c in group)
                    m[f"{label}_body_words_median"] = words[len(words) // 2]
                    m[f"{label}_body_under_20_words"] = round(
                        sum(1 for w in words if w < 20) / len(words), 3)
                m.update(score_requests(
                    [(c["group"], c["targets"]) for c in multi if c["hub"]["pre_work"]]))
            org_out["methods"][method] = m
        org_out["changes"] = {}
        meta = pr_meta(d / "prs.jsonl.gz")
        for name, methods in COMBOS.items():
            ch = changes(cases, methods, a.max_targets, meta)
            n = len(ch)
            sizes = Counter(min(len(c["targets"]), 4) for c in ch)
            pairs = Counter(tuple(c["targets"]) for c in ch)
            top = pairs.most_common(1)
            co = {
                "methods": list(methods), "changes": n,
                "t2": sizes[2], "t3": sizes[3], "t4plus": sizes[4],
                "opened_within_2min": round(sum(1 for c in ch if c["opened_spread_s"] is not None
                                                and c["opened_spread_s"] <= 120) / n, 3)
                if n else None,
                "top_target_set": list(top[0][0]) if top else None,
                "top_target_set_share": round(top[0][1] / n, 3) if top else None,
                "with_issue": round(sum(c["has_issue"] for c in ch) / n, 3) if n else None,
                "with_pre_work_issue": round(sum(bool(c["pre_work_issue"]) for c in ch) / n, 3)
                if n else None,
                "distinct_targets": len({t for c in ch for t in c["targets"]}),
                "prs_in_changes": sum(len(c["prs"]) for c in ch),
                "sweep_like": round(sum(c["sweep_like"] for c in ch) / n, 3) if n else None,
                "not_sweep_like": sum(not c["sweep_like"] for c in ch),
                "not_sweep_pre_work": sum(not c["sweep_like"] and bool(c["pre_work_issue"])
                                          for c in ch),
                "not_sweep_t4plus": sum(not c["sweep_like"] and len(c["targets"]) >= 4
                                        for c in ch),
            }
            co.update(score_requests(
                [(c["pre_work_issue"], c["targets"]) for c in ch if c["pre_work_issue"]]))
            org_out["changes"][name] = co
        result[org] = org_out
    Path(a.out).expanduser().write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
