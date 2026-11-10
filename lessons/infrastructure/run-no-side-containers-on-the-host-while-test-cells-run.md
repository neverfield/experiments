# Run no side containers on the run host while test cells run

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-08 · **Source:** store `internal/test-run/post-fix-run-audit.md` (reruns-f, cell 3; Diagnosis: cell 3 timeout); store `internal/test-run/handoff.md` (standing rule of 2026-11-07 07:00 UTC); [PREREGISTRATION.md](../../repo-discovery/PREREGISTRATION.md) §7, addendum to entry 7, item 8

**What happened.** A test cell's audit bound allowed 0 timeout cases. While the cell ran, the operating agent started 28 containers in 42 minutes on the same Docker engine and volume. Most were status reads and selftests. Two were 300 s tests of a new preflight that ran the harness with network access. The second covered the last minute of one case's setup and the first four minutes of its main run, and that case was the cell's only timeout. The load sampler missed all 28, because none of its windows fell between 06:19 and 06:47 UTC.

**What it cost.** A diagnosis, under a rule fixed before looking, of whether the timeout was an infrastructure failure. It was judged a method timeout, so the pass failed and was rerun: $18.22 for the failed pass, then $18.83 for the rerun. The overlap can't be ruled out as a cause. Docker's event history no longer lists every container that ran during earlier cells.

**Next time.**
- Test new tooling on another machine, or after the last cell ends.
- Before the first cell, write a rule into the run plan: nothing else runs on the host while a confirmatory cell runs or a launch is due. Allow one exception, a short read-only audit container per finished cell, with no network, the volume read-only, one CPU and under 60 s.
- Log each audit container's start and end beside the cell it overlapped.
- This is stricter than [taking timings on a quiet machine](pin-threads-and-time-on-a-quiet-machine.md), because a timeout bound turns extra load into a failed pass.
