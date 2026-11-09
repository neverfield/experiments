# Project API mining from the limit that binds, not the documented quota

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Fetch cost); `same-org/scripts/mine_prs.py` docstring

**What happened.** A GraphQL search page of 100 merged PRs with bodies costs 1 point, so the 5,000-point hourly quota suggests 500,000 PRs an hour. But each page takes about 5.7 s of GitHub's server time, and GitHub's secondary limit caps server time per minute. On a one-month grafana slice, 4 workers fetched about 27 pages a minute. Raising the total to 10 workers across orgs didn't help: throughput stayed at 20–40 responses a minute, and the extra workers drew 403s with no `Retry-After`. Points spent were under a tenth of the quota. The three-month mine of about 260,000 PRs over 8 orgs took about 2.5 hours, against minutes by the point count.

**What it cost.** A first plan sized from points, then a slower mine than planned. Microsoft and Apache alone, at about 150,000 PRs, take over an hour.

**Next time.** On a slice, log wall time per response and responses per minute at 1, 2 and 4 workers, and project from whichever limit binds. For GitHub search with bodies, budget about 2,000 PRs a minute per token, whatever the concurrency.
