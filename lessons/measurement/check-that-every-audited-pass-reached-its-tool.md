# Check that every audited pass reached its tool, not only that it finished

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-08 · **Source:** store `internal/test-run/search-tool-outage.md` (summary; Test passes; Guards as built); [PREREGISTRATION.md](../../repo-discovery/PREREGISTRATION.md) §7, addendum to entry 7, item 1

**What happened.**
- **The audit checked the wrong things.** Each test pass was audited blind before it was accepted, for timeout and provider-error cases. Nothing checked that the agent's MCP tool worked.
- **The tool was missing.** In two windows from 2026-11-04 to 11-06, and in runs on 2026-11-01 later withdrawn for other reasons, the CLI started sessions without the MCP server in its tool registry. In the first window, it refused the agent's calls locally. In the second, the agent never saw the tool. The CLI version was pinned throughout.
- **The passes were accepted anyway.** In 6 of 32 accepted passes, the tool reached its server in 0 to 15 of 59 cases, and all 6 passed the audit. Comparing the CLI's MCP calls with the server's log, case by case, found them on 2026-11-07.

**What it cost.** The 6 passes ($57.08) were withdrawn and rerun. The reruns took seven runs and $109.46, because one cell then failed on a timeout and ran again, and they helped push test spend past its $800 cap. 13 runs already withdrawn for other reasons turned out to be broken too, which led to a recount of which runs counted as tries.

**Next time.**
- For every method that gives the agent a tool, put a per-case tool check in the audit bound. Allow no case in which the client made calls that the server never logged. Allow at most a small number of cases with no call at all, a limit fixed in advance from dev.
- Preflight the tool with one real case before each launch. Have the queue stop a cell when its last few finished cases log no server call.
- Replay a new bound over every earlier run, to check that it flags the broken runs and no working one.
- This adds to [logging what the agent got from each tool call](log-what-the-agent-got-from-each-tool-call-not-what-the-server-sent.md): compare the client's and the server's logs in the audit itself, not only in the export.
