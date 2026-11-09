# Probe every data source from the run VM before designing around it

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Blocked sources); store `internal/same-org-feasibility/handoff.md` (Findings, 3)

**What happened.** The natural label and request sources for a same-org benchmark live off GitHub: Apache's and Red Hat's JIRA (the request text behind apache and openshift PRs), GH Archive (cheap full-history PR events), OpenDev Gerrit (`Depends-On` links), Bugzilla, BigQuery and PyPI. One `curl -s -o /dev/null -w '%{http_code}'` per host, about a minute in all, showed that from the Cloud Agent VM only `api.github.com`, `github.com`, `raw.githubusercontent.com`, `codeload.github.com` and `storage.googleapis.com` answer. Every other host returned 000.

**What it saved.** The design never depended on JIRA bodies or GH Archive. Mining went through GitHub search and GraphQL, and request text came from GitHub issues only. The report says which parts (JIRA request text, full-history mining) need a machine with open egress.

**Next time.** Before designing, list every host the label method, request text and fetches need, probe each from the VM that will run the job, and write the blocked ones into the plan with what they rule out. Probe again on a fresh VM before a long run.
