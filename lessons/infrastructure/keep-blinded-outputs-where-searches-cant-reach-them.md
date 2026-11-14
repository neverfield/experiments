# Keep blinded outputs where searches can't reach them, and test any exclusion glob

**Experiment:** repo-discovery held-out test analysis · **Added:** 2026-11-09 · **Source:** store `/cursor/stores/bc-c364fa0b-55a8-56e7-96c4-2b320bedf063/internal/incidental-read-tool-call-key-counts.md`

**What happened.** The held-out test traces sat in the same agent store as the study's notes, under `internal/test-run/`. While freezing the test analysis, a worker searched the whole store for dev examples of the CLI's tool-call names, with `rg ... -g '!internal/test-run/**' /cursor/stores/<id>/` to skip that folder. With an absolute search path, that glob excluded nothing: only `-g '!**/internal/test-run/**'`, or searching `.` from the store root, did, as a dummy tree showed afterwards. The search printed 30 lines of per-file tool-call counts from 21 cases' traces of a withdrawn test pass. No prediction, ranking, target or score was printed. Before the folder was declared off-limits, a `find` listing and five greps over the store had also reached it.

**What it cost.** An incidental-read record. One scoring choice, the first search's tool names, had to rest on another worker's dev key list alone, since nothing seen could inform it. The pass was withdrawn, so no scored output was exposed, but the same query with another pattern would have printed test predictions.

**Next time.** Keep blinded outputs out of any tree that analysis agents search: a separate store, or a folder they can't read. Beside blinded data, read files by exact path, with no store-wide `grep`, `rg`, `find` or glob. If a search must skip a folder, write the glob as `!**/<folder>/**` and test it first on a dummy tree with a planted file.
