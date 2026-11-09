# Keep the context of each link, so label rules can be varied without refetching

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** `same-org/scripts/build_cases.py`; store `docs/same-org-feasibility.md` (Label methods)

**What happened.** The first `build_cases.py` grouped PRs by the issue they referenced, after one filter on the reference's context ("fixes", "part of", "depends on", "port of"). Issue timelines also add every PR that cross-references the issue. Those were added without a context, so the filter never applied and `issue-ref` took every PR that mentioned a shared issue. The rewrite keeps a set of contexts per (issue, PR) link and a context per PR-to-PR edge, from bodies, closing references and timelines. One fetch now yields seven rules, from `issue-close` to `issue-ref` and from `pr-link-dep` to `pr-link`. On grafana's June slice they range from 1 to 80 multi-repo cases, and only 5 of `pr-link`'s 171 edges are `depends`.

**What it saved.** Every rule variant came from one fetch per org instead of a refetch. Hub expansion alone took 216 GraphQL points and 5 minutes for one grafana month. The hand-check could compare precision across rules on the same cases.

**Next time.** When labels come from links, store each link's raw evidence (source, phrase, closing flag, timeline or body) with the case, not just the rule's verdict. Then the rule becomes a filter applied at build time and can be chosen after the precision check.
