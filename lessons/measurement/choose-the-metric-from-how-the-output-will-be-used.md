# Choose the metric from how the output will be used

**Experiment:** repo-discovery, study-question review · **Added:** 2026-11-09 · **Source:** store `docs/study-question-review.md` (Verdict; Part 1; Needs a new study, 2); store `docs/repo-discovery-study.plan.md` §1 and §2; store `docs/repo-discovery-study-full.plan.md` §3; store `docs/selection-step.md` (Frozen picks); `repo-discovery/src/repo_discovery/rankers/cursor_agent.py` (the prompt)

**What happened.** The plan chose CompleteRecall@10 because finding one repository of a change is much less useful than finding all of them (plan §1). That prices a miss. It doesn't price a false positive or the size of the set, and no plan wrote down how the output would be used; the full plan's "Who acts on the result" (§3) maps outcomes to what to build, not to what each error costs. The use is a software factory that opens a branch and an agent in every repository it predicts.
- Every case has two or three targets: 107 WideSWE tasks have 2 and 13 have 3 (plan §2). There are no single-target cases, and the agent prompt says a change "often spans more than one repository".
- With two or three targets, CR@10 counts a case as solved with seven or eight wrong repositories in the list.
- The frozen agent picks score 0.97–1.00 CR@10 at every size from U50 to U10000 on dev (`selection-step.md`, Frozen picks), so agent methods differ by zero to three cases.

**What it cost.** The primary metric sits at its ceiling for every method worth choosing between, and it can't say how many repositories a factory must open, or whether a method can say "just this one". Set metrics (CR@|G|, CR@3, CR@5, non-targets above the last target) are now exploratory extras from the saved rankings. Set output with single-target cases needs a new study.

**Next time.** Before choosing the metric, write a short decision analysis of the real use:
- what is done with each predicted item, and what a miss and a false positive each cost there;
- how many targets real requests have, single targets included, and whether the cases and the prompt match that mix;
- a metric that prices both errors (exact set, set F1, or expected cost at those prices), reported beside the recall metric.

Then check on a pilot that the leading methods aren't already at its ceiling ([lesson](choose-cells-where-methods-can-still-differ.md)).
