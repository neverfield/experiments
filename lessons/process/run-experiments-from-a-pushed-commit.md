# Run experiments from a pushed commit, and record its SHA

**Experiment:** repo-discovery · **Added:** 2026-10-29 · **Source:** the Setup sections of store `docs/v0-keyword-pilot.md`, `docs/v2-dependency-graph.md`, `docs/v4-embeddings.md` and `docs/v5-cursor-agent.md`

**What happened.** The harness, V0, the agent ranker and the universes were stacked, unmerged PRs. So the V0 pilot and the V2, V4 and V5 dev runs each ran on a local branch that merged several PR branches, and none of those branches was pushed: `cursor/v0-pilot-integration-8661` (at `f706e47`), `cursor/v2-integration-local-43b4`, `cursor/v4-integration-3fcd` and `cursor/v5-dev-run-integration-41e1`. V4's branch also held code that was removed before merging.

**What it cost.** Nobody else can reach the exact code behind four reports. Each report argues that the merged code gives the same rankings, and readers have to take that on trust.

**Next time.** Merge infrastructure PRs before running on them, or push the integration branch. Put the commit SHA you ran in the report.

**Seen again:** 2026-10-29, the selection step (EXP-28, [PR #20](https://github.com/ForeverTheIntern/experiments/pull/20)). Its registry first recorded the U1000 memory checks under the commit that merged their PR (48b6fab), not the commit they ran from (80cb9ad). Take the SHA from the run's own log or cell header, not from the merge.

**Seen again:** 2026-11-09, same-org feasibility ([PR #41](https://github.com/neverfield/experiments/pull/41)). The eight-org mine ran on a branch that was pushed only at the end. Fixes landed while it ran: hub-batch bisection at `326f82e` and fail-fast 5xx at `02662eb`. Steps restarted on newer code than the mine had started on. Every commit is reachable now, but no single SHA produced the data. The report gives the range (`a393ba3` to `02662eb`) and names `c74286f` as the commit behind the tables. Push the branch before a long run, push each fix before restarting a step on it, and log the SHA at the start of each step.
