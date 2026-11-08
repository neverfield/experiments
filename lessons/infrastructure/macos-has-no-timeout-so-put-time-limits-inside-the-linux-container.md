# macOS has no `timeout`, so put time limits inside the Linux container

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-08 · **Source:** store `internal/test-run/post-fix-run-audit.md` (reruns-g, cell 1: audit container)

**What happened.** The test host was a macOS laptop running a Docker Linux runner. An audit wrapper on the host bounded its container with `timeout`, as [running ad-hoc scripts under a timeout](run-ad-hoc-scripts-under-a-timeout-and-check-for-strays.md) advises. macOS doesn't ship GNU coreutils, so it has no `timeout` command. At 2026-11-08 00:21:35 UTC, the wrapper failed before `docker run` and started no container. The next try, 10 s later, ran.

**What it cost.** Little this time: one failed try, during a running test cell. A wrapper written the other way round, with the command running and only the limit missing, would have run with no time limit at all.

**Next time.**
- On a macOS host, put the time limit inside the container, which has GNU `timeout`: `docker run … timeout 60 python3 …`. Or use `docker run --stop-timeout` together with `docker stop`.
- Check `command -v timeout` before writing a host-side wrapper.
- Test every host-side wrapper on the host's own OS, not only on a Linux VM.
