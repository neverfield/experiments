# same-org

Mining scripts for a feasibility check: can a repo-discovery benchmark be built from public GitHub data in which every candidate repo belongs to the targets' own org, with labels from real changes that touched more than one of its repos? Background: store `docs/study-question-review.md`, "Needs a new study".

Standard library only (Python 3.11+). Every GitHub response is cached under `~/so-cache`, keyed on a hash of the full request, so reruns are free. Mined data is third-party content and stays out of this repo; write it to the Project store.

| Script | What it does | Cost |
|---|---|---|
| `org_census.py` | Public-repo count per org, then the full repo listing: archived, forks, active in 180 and 365 days | 1 request per org, plus 1 per 100 repos |
| `listing_stats.py` | Offline summary of listings: descriptions, topics, name-prefix concentration, sizes | none |
| `mine_prs.py` | Every merged PR in an org over a window, through GraphQL search, split so each query stays under search's 1,000-result cap | about 1 GraphQL call per 100 PRs |
| `expand_hubs.py` | Resolves every in-org issue or PR the mined PRs reference, with the issue's cross-reference timeline (so linked PRs outside the window count) | 1 GraphQL call per 20 items |
| `build_cases.py` | Groups PRs into cases by five label methods: `issue-close`, `issue-ref`, `pr-link` (and `pr-link-dep`), `key`, `branch` | none |
| `sample_review.py` | Seeded sample of multi-repo cases per org and method, rendered as a review sheet | 1 GraphQL call per 25 PRs |
| `analyze.py` | Target counts, single-repo rate, pre-work request rate, whether requests name targets, and a names-only BM25 ranker over the org's active repos | none |
| `doc_profile.py` | README, docs and manifest bytes per repo, from one git-tree request each | 2 requests per repo |

```bash
cd same-org
python3 -m unittest discover -s tests
python3 scripts/org_census.py --orgs grafana elastic --out ~/so/census
python3 scripts/mine_prs.py --org grafana --since 2026-06-01 --until 2026-08-31 --out ~/so/mined
python3 scripts/expand_hubs.py --org grafana --mined ~/so/mined
python3 scripts/build_cases.py --org grafana --mined ~/so/mined --census ~/so/census
python3 scripts/sample_review.py --orgs grafana --mined ~/so/mined --out ~/so/review
python3 scripts/analyze.py --orgs grafana --mined ~/so/mined --census ~/so/census --out ~/so/analysis.json
```

The GitHub token comes from `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`. On a 401 the client re-reads it every minute, for up to `SAME_ORG_MAX_AUTH_WAIT_MIN` minutes (default 30). A paginated listing raises on any failed page rather than returning a partial list.
