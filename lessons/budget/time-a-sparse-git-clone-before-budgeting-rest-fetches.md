# Time a sparse git clone before budgeting REST fetches for repo packets

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Fetch cost); `same-org/scripts/clone_cost.py`; store `docs/packet-construction.md` (Fetch levels)

**What happened.** The old study fetched repo packets over the REST API: 11.87 requests per repo at L3 and 29.83 at L4. At 5,000 requests an hour, one 1,000-repo universe at L4 takes about 6 hours, and all 3,111 active microsoft repos take about 19. A depth-1, blobless, no-checkout clone followed by a sparse checkout of the README, docs and manifest paths fetched the same kinds of files from 35 grafana repos in a median of 0.27 s each (max 1.5 s, about 0.4 MB). It uses no REST quota.

**What it saved.** Fetch cost stops limiting universe size. All 3,111 microsoft repos would take about 20 minutes over git at that rate, against about 19 hours over REST at L4. One snapshot per case also becomes affordable.

**Next time.** Before budgeting REST fetches for repo contents, time `git clone --depth 1 --filter=blob:none --no-checkout` plus a sparse checkout on a few dozen real repos. Use REST only for metadata git doesn't carry (topics, issues, stars). Clone at a pinned commit when cases need a snapshot date, and record clone failures as a count to gate on.
