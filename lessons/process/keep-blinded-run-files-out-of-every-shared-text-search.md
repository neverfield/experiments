# Keep blinded run files out of every shared text search

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-09 · **Source:** [PREREGISTRATION.md](../../repo-discovery/PREREGISTRATION.md) §7, addendum to entry 7, item 10

**What happened.**
- **Test files sat in the shared store.** Copies of test-run traces, among them the withdrawn 2026-11-01 `u50-real-c1-L2` passes, were in the Project's agent store under `internal/test-run/`, which every agent can read. Dev predictions sat under `internal/selection/predictions/`.
- **Store-wide searches reached them three times.**
  - A cloud worker's `grep` printed lines from U50 test traces and three lines of prediction files.
  - On 2026-11-09, a writing worker's search printed about 16 lines from 6 trace files of five test cases: tool calls with their patterns and results, and README excerpts.
  - Minutes earlier, a search for an agent's own ID ran over the same folder. It was stopped before its output was read.
- None of the searches opened a prediction or a score. The runs they touched are withdrawn.

**What it cost.** Each read had to be recorded, with a check that it couldn't influence an accepted pass, before any score was read. The printed case IDs name their target repositories, so they had to be kept out of the public record.

**Next time.**
- Keep blinded files outside the shared store, or in one folder that every store search excludes, for example `rg --glob '!internal/test-run/**'`.
- Write the exclusion into the store's agent instructions before the first test file lands there.
- Find files by name before searching their contents.
