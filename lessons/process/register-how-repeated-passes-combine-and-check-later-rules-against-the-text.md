# Register how repeated passes combine, and check each later rule against the registered text

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-09 · **Source:** [PREREGISTRATION.md](../../repo-discovery/PREREGISTRATION.md) §7, addendum to entry 7, items 15 and 16

**What happened.**
- **Pooling was set only in code.** The registration gave every agent cell 2 passes, and named "the pooled mean" only for its stability report. It didn't say how the confirmatory tests H1–H3 combine a cell's passes. The analysis script, committed about 5 hours after the registration, averages each case over the passes for every test.
- **A rerun rule conflicted with a run rule.** §5 said every test cell runs from one pushed commit. A later rerun entry let a cell's two passes come from different commits. It didn't call that a deviation, and 6 of the 17 cells ended up mixed, one of them feeding H3.
- A blind review found both 8 days later, and they were recorded as deviations before any score was read.

**What it cost.** Two deviations in the record. A reviewer can ask whether the pooling rule was chosen after the passes had run.

**Next time.**
- Commit the analysis script with the registration, and name its commit in the text.
- For each confirmatory test, say which runs feed it and how repeats combine: a pooled per-case mean, each pass separately, or the first pass only.
- When a later entry adds or changes a run rule, check it against every registered rule. Label any conflict as a deviation in that same entry.
