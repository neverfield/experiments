# Pilot the run budget and the sample's power before a large grid

**Experiment:** repo-discovery, study-question review · **Added:** 2026-11-09 · **Source:** store `docs/study-question-review.md` (Part 2, gaps 1 to 3; Other validity threats); store `docs/repo-discovery-study.plan.md` §4, §6 and §8; store `docs/repo-discovery-study-full.plan.md` §7 (Size); store `docs/v5-cursor-agent.md` (What stands out; Reliability); store `docs/v5-on-demand.md` (What the agent opens); store `docs/v5-index-use.md` (Against the noise floor); store `docs/selection-step.md` (The short version; How the table was built)

**What happened.** The lightweight plan (§8) dropped the full plan's power simulation, which had asked for 0.80 power at +10 points and about 180 to 220 test cases (full plan §7). The lightweight plan's §6 set a timeout and a tool-call limit per agent run, with no test of whether they would bind. The grid then grew to 491 combinations on 61 dev cases.
- **The budget always bound.** The agent made a median of 63 to 64 tool calls per case and ignored the turn budget in its prompt. The 20-round cap ended 120 of 122 V5 dev runs (`v5-cursor-agent.md`). At 50 opens, 52 of 61 real-name L5 cases at U1000 hit the cap first (`v5-on-demand.md`). Agent dollars are flat with size because of the cap (`selection-step.md`).
- **The sample couldn't separate the methods.** One case is 0.016. Two identical L4 agent runs at U1000 disagreed on 4 cases, 2 each way (`v5-index-use.md`). The search tool's leads over `c1` at U5000 and U10000 are +0.008 to +0.057, half a case to 3.5 cases, and no interval excludes zero (`selection-step.md`). Plan §4 called differences under about 10 points "can't tell", yet picks were decided by one to three cases.

**What it cost.** Every agent comparison is at one budget that always binds, which penalises patterns that need more rounds, such as L5's opens. The access-pattern and index-content picks rest on dev margins inside the noise, and the test run can't confirm them.

**Next time.** Before laying out the grid, pilot the two or three main methods on about 10 cases, twice each, at the planned caps:
- log which limit ended each run ([lesson](record-when-a-cap-binds-instead-of-raising-it.md)); if a cap ends most runs, make it a factor (for example half and double) or set it from where runs stop on their own;
- from the repeat's rescued and broken cases ([lesson](measure-run-to-run-noise-for-stochastic-methods.md)), work out the smallest difference the planned sample can detect;
- cut the grid to the contrasts that sample can resolve, or add cases, and preregister those contrasts.
