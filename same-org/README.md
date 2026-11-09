# same-org

Mining scripts for a feasibility check: can a repo-discovery benchmark be built from public GitHub data in which every candidate repo belongs to the targets' own org, with labels from real changes that touched more than one of its repos? Background: store `docs/study-question-review.md`, "Needs a new study". Findings: store `docs/same-org-feasibility.md`.

Standard library only (Python 3.11+). Every GitHub response is cached under `~/so-cache`, keyed on a hash of the full request, so reruns are free. Mined data is third-party content and stays out of this repo; write it to the Project store.

An "org" argument is a GitHub owner, or a group from `same_org/orgs.py` (`k8s` is kubernetes plus kubernetes-sigs). A group is searched with one OR'd query and scored as one candidate pool.

| Script | What it does | Cost |
|---|---|---|
| `org_census.py` | Public-repo count per org, then the full repo listing: archived, forks, active in 180 and 365 days | 1 request per org, plus 1 per 100 repos |
| `listing_stats.py` | Offline summary of listings: descriptions, topics, name-prefix concentration, sizes | none |
| `mine_prs.py` | Every merged PR in an org over a window, through GraphQL search, cut into `--chunk-days` pieces and split so each query stays under search's 1,000-result cap. Records expected against fetched counts | about 1 GraphQL point per 100 PRs; wall time binds (below) |
| `expand_hubs.py` | Resolves the in-org issues and PRs that usable PRs (not forks, bots or backports) reference, except port, revert and supersedes references, with each issue's cross-reference timeline. A batch that keeps failing is split down to single items; items that still fail are recorded, and the step fails above `--max-error-share` | about 1 GraphQL point per 50 items |
| `build_cases.py` | Groups PRs into cases by seven label methods (below), keeping each link's contexts and each PR-to-PR edge | none |
| `analyze.py` | Per method: multi-repo cases, target counts, span, single-repo rate, pre-work request rate, whether requests name targets, a names-only BM25 ranker over the org's active repos. Per method combination: distinct changes (cases joined where they share a PR), with title flags for sweeps (`sweep_like`) and for one title across every PR (`same_title`) | none |
| `sample_review.py` | Seeded sample of multi-repo cases per org and method, rendered as a review sheet of shuffled blocks that hide the method, one per distinct change (`sheet.md`, `sample.json`). `--combos` also samples joined changes per method combination, and `--methods` with no names samples only those. `--parts` splits it for parallel raters; `--overlap` writes a subset for a second rater. How to judge: `REVIEW.md` | only PRs missing from the mined data |
| `score_review.py` | Precision per method, pooled and per org, strict and lenient, with Wilson 95% intervals and kinds, from `verdicts.json` keyed on block IDs; agreement and kappa against `--second` raters; each title flag against the raters' kinds, per review directory | none |
| `report_tables.py` | Prints the report's tables from the outputs above, with `cochange.py`'s table when given `--cochange` | none |
| `doc_profile.py` | README, docs and manifest bytes per repo from one git-tree request each, for an org's multi-repo targets and two control pools (other active repos; other repos that merged a PR in the window), with each feature's AUC | 1 REST request per repo |
| `clone_cost.py` | Times a depth-1, blobless, sparse git clone of the README, docs and manifests per repo | no API quota |
| `cochange.py` | For changes after a split date, how much of each target set the earlier cases already hold: every pair seen, any pair seen, and the recall of a co-change lookup seeded with one target | none |

Label methods, from strictest to loosest:

| Method | A case is |
|---|---|
| `issue-close` | PRs that close one issue (closing keyword, sidebar link) |
| `issue-strong` | PRs linked to one issue by closing, "part of", "depends on", companion or follow-up phrasing |
| `issue-ref` | PRs that reference one issue in any way except port, revert or supersedes, timeline references included |
| `pr-link-dep` | Connected PRs across repos, through "depends on" or companion references only |
| `pr-link` | Connected PRs across repos, through any reference except port, revert or supersedes |
| `key` | PRs whose titles carry one JIRA-style key |
| `branch` | One author's PRs from one non-generic branch name, merged within 30 days |

```bash
cd same-org
python3 -m unittest discover -s tests
python3 scripts/org_census.py --orgs grafana kubernetes kubernetes-sigs --out ~/so/census
python3 scripts/mine_prs.py --org grafana --since 2026-06-01 --until 2026-08-31 --out ~/so/mined --workers 2
python3 scripts/expand_hubs.py --org grafana --mined ~/so/mined --workers 4
python3 scripts/build_cases.py --org grafana --mined ~/so/mined --census ~/so/census
python3 scripts/analyze.py --orgs grafana k8s --mined ~/so/mined --census ~/so/census --out ~/so/analysis.json
python3 scripts/sample_review.py --orgs grafana k8s --mined ~/so/mined --out ~/so/review --per-cell 6 --parts 4 --overlap 40
# hand-check each part into ~/so/review/verdicts.json, per REVIEW.md, and the overlap into verdicts-b.json
python3 scripts/score_review.py --review ~/so/review --second ~/so/review/verdicts-b.json --out ~/so/review/scores.json
python3 scripts/doc_profile.py --org grafana --mined ~/so/mined --census ~/so/census --out ~/so/docs/grafana.jsonl
python3 scripts/clone_cost.py --repos-file ~/so/docs/grafana.jsonl --limit 30 --out ~/so/clone-cost.jsonl
python3 scripts/cochange.py --orgs grafana k8s --mined ~/so/mined --combo explicit --split 2026-08-01 --out ~/so/cochange.json
python3 scripts/report_tables.py --orgs grafana k8s --mined ~/so/mined --analysis ~/so/analysis.json \
    --docs ~/so/docs --scores ~/so/review/scores.json --cochange ~/so/cochange.json > ~/so/tables.md
```

The GitHub token comes from `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`. On a 401 the client re-reads it every minute, for up to `SAME_ORG_MAX_AUTH_WAIT_MIN` minutes (default 30). A paginated listing raises on any failed page rather than returning a partial list. Network errors and truncated bodies are retried with backoff, as is a body still arriving after `SAME_ORG_REQUEST_DEADLINE_S` seconds (default 300), and a secondary-limit 403 or 429 without `Retry-After` waits 60 s. Every call's points, wall time, retries and waits go to each script's spend summary.

**Throughput.** GitHub's secondary limit caps server time per minute, so a token gets about 20 to 40 search responses a minute (about 2,000 PRs with bodies) however many workers run. Points are rarely the limit. Run the orgs in parallel with a total of about 8 to 10 workers, and plan on about an hour per 100,000 PRs.
