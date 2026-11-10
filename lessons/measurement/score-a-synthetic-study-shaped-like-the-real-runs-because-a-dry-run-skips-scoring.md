# Score a synthetic study shaped like the real runs, because a dry run skips the scoring path

**Experiment:** repo-discovery held-out test (EXP-13), scoring · **Added:** 2026-11-10 · **Source:** store `internal/scoring-freeze/heldout-score-683880b/record.md` (Attempt 2: why the dry run passed and scoring didn't); `repo-discovery/PREREGISTRATION.md`, addendum item 22; [PR #42](https://github.com/neverfield/experiments/pull/42)

**What happened.**
- **Every check before scoring passed.** The frozen scoring code at `683880b` passed its 467 tests and scored a synthetic study end to end. Its final dry runs on the real inputs reported 0 problems.
- **Real scoring stopped anyway.** It stopped 41 s in, at a check that needs the data: `_rate` found an agent pass with no finished first run to take a rate per token from.
- **The dry run never reached that check.** It reads run lists, `run.env` stamps and file names, then returns before `build()`, so it never prices a run.
- **The bound audit didn't ask the question.** It reads every trace, but checks timeouts, provider errors and tool calls, not whether any first run finished.
- **The synthetic study had the wrong mix.** It gave every case a first run that ended `ok` with usage. In the real runs, all 59 first runs of 5 of the 38 agent passes stopped at the turn budget, and runs that stop record no usage. 8 more passes had exactly 1 finished first run.
- **A blind count would have caught it.** One count of first-run statuses found the 5 passes, reading no prediction or score. Nothing ran it before scoring.

**What it cost.**
- Two failed scoring attempts on the frozen commit.
- A change to frozen scoring code after scoring had started (item 22, a recorded deviation), plus a second freeze at `ae33125` with its own review, tests and merge.
- About ten hours from the first attempt (06:13 UTC) to the scored report (16:36 UTC).

**Next time.**
- **Count what the code branches on.** Before freezing, take blind counts from the real runs of every field the scoring code branches on, such as run status and whether usage is empty.
- **Cover every combination.** Build the synthetic study so it covers each combination, including a pass whose every run stops.
- **Move data stops into the dry run.** Put every stop that blind fields can decide into the dry run, so it fails where scoring would.
- **Give every pricing function a fallback.** Register one for when it has nothing to price from ([seen first in the spend watch](../budget/give-a-spend-watch-a-safe-fallback-for-when-it-cant-price-runs-yet.md)). Related: [keep dev copies of every raw log an analysis may parse](keep-dev-copies-of-every-raw-log-an-analysis-may-parse.md).
