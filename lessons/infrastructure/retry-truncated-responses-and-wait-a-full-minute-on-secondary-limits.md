# Retry truncated responses, and wait a full minute on a secondary rate limit

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** `same-org/same_org/gh.py` (`_do`); store `docs/same-org-feasibility.md` (Fetch cost)

**What happened.** Two failures in the GitHub client showed up only under the full mine, not in the smoke test.
- **Truncated body.** After 9 minutes the first three-month mine died on `http.client.IncompleteRead`, a mid-body connection drop. The retry handler caught `URLError` and timeouts but not `http.client.HTTPException`.
- **Short waits.** GitHub's secondary limit returns 403 or 429, often without `Retry-After`. The client then waited 5 s and retried, and each early retry kept the token blocked. The logs showed runs of 5 s waits between almost no progress.

**What it cost.** A restart of all 8 org mines. The cache kept finished pages, so only the 9 minutes of in-flight work and a slower first quarter-hour were lost.

**Next time.** In an API client for long fetches, retry `http.client.HTTPException`, `ConnectionError` and timeouts with backoff, and treat a GraphQL 200 with errors and no data as transient. On a 403 or 429 with no `Retry-After` or reset header, wait 60 s. Count retries and waits in the spend file, and make every page a cache entry written atomically, so a restart costs only work in flight.

**Seen again:** same-org feasibility, 2026-11-09. One k8s hub batch of 50 issues returned 502 on every retry, which is likely a few kubernetes issues with very long timelines, and the whole expansion died after 30 minutes at batch 51 of 94. Retrying the same batch can't help with a query that is too heavy. `expand_hubs.py` now splits a failing batch in half down to single items, records items that still fail, and fails the step only above 0.5% of items. The first version of the split stalled for 20 minutes, because the GraphQL wrapper's 5 retries each ran the HTTP layer's 4, so one doomed query cost about 15 minutes before it split. Callers that can split a query now set `max_5xx_retries=0`, which costs two calls and 8 s. The cache served all finished batches on each rerun. Retries stacked across layers multiply, so count them end to end.
