# Keep dev copies of every raw log an analysis may parse, outside the blinded area

**Experiment:** repo-discovery held-out test analysis · **Added:** 2026-11-09 · **Source:** `repo-discovery/TEST_ANALYSIS.md`, open choice 4 (branch `cursor/test-scoring-freeze-0263`)

**What happened.** The addendum's item 17 was declared after the test runs. It added a first-search diagnostic that reads each case's raw `events.jsonl` and needs the CLI's tool-call names (`grepToolCall`, `globToolCall`, `mcpToolCall`). The scoring code had to be frozen blind. No dev `events.jsonl` was kept in the repo or the store: the dev traces stayed in each runner's cache. The only real event logs within reach were the blinded test traces. So the parser was tested only on synthetic events written from the registered text and the stream parser's `<kind>ToolCall` convention, and confirming the names became an open choice before freezing.

**What it cost.** One exploratory analysis depends on a format nobody checked against real output. A wrong name would put every run in "no search call", with nothing to flag it. Checking means finding a runner that still has dev traces.

**Next time.** Before the test run starts, copy a few dev cases' complete raw outputs into the store with checksums. For each method, include the event stream, the trace summary, the server log, the predictions and `run.env`. Then any analysis declared later can be tested on real formats without opening a test file.
