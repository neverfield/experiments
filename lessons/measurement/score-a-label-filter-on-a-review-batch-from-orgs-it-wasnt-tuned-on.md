# Score a label filter on a review batch from orgs it wasn't tuned on

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Sweep flag); `same-org/scripts/analyze.py` (`sweep_like`, `same_title`)

**What happened.** A title rule flagged "sweeps", one mechanical edit pushed to several repos, so they could be dropped from the case counts. Its first version flagged a change when all its PRs had one title or every title read as maintenance. Tuned on hand-check batch A (grafana and hashicorp), it scored precision 0.84 and recall 0.88 there. On batch B (k8s and dotnet) it fell to 0.41 and 0.58, and on batch C (elastic and openshift) to 0.36 precision. Identical titles meant a sweep in grafana and hashicorp, but mostly a mirror (one fix copied to sibling repos) or a coordinated change in the other orgs. Version 2 moved identical titles to a separate flag and was refit on A and B, then committed before batch C's verdicts were read. On C it scored 0.80 and 0.80, with only 5 sweeps.

**What it cost.** One more tuning round and a rescore. The first draft's "not sweep-like" counts came from version 1 and had to be redone. A split inside batch A would not have caught this, because the failure was a difference between orgs.

**Next time.** Fit any heuristic filter on hand labels from some orgs, commit it, and score it on a batch from other orgs before using its counts. Report every version's held-out score, and count what the filter drops with the hand-checked rate of the cases it keeps, not with the flag alone.
