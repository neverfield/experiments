# Hand-check the joined cases the benchmark will use, not only each link rule

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Label precision); `same-org/scripts/sample_review.py` (`--combos`)

**What happened.** Each label method (issue links, PR-to-PR links, shared branch names) was hand-checked on its own cases. A benchmark case is a change: the union of every method's cases that share a PR. The sampler also drew joined changes for each combination of methods, as if they were methods. Over 6 orgs, the links combination (issue, PR-to-PR and branch links) was the same piece of work in 0.75 of joined changes. Its weakest method alone scored 0.81. Only 0.44 of its joined changes were the same piece of work and not a sweep, against 0.81 for PR-to-PR links alone, because branch-name joins pulled maintenance sweeps into otherwise real changes. The explicit combination without branch names scored 0.86 and 0.81.

**What it saved.** The case counts would otherwise have used the links combination, read off its methods' precision at about 0.8, with almost half its changes sweeps.

**Next time.** When labels are joined from several rules, sample the joined unit the benchmark will score, method-blind, next to each rule's own cases. Pick the combination by the joined unit's precision on the kind of work the benchmark wants.
