# Check that a raised spend cap reaches every queue through its launcher

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-08 · **Source:** store `internal/test-run/handoff.md` (cap variants; reruns-g launch); [PREREGISTRATION.md](../../repo-discovery/PREREGISTRATION.md) §7, addendum to entry 7, item 6

**What happened.**
- **Where the cap came from.** The queue read its spend cap from `CAP` in its environment, which `go.sh` passed into the container, and used $800 when `CAP` wasn't set.
- **Who launched the lists.** Gated lists were launched by a long-running weekend launcher. It had started before the cap was raised, so each list it launched ran under whatever cap its environment held at that start.
- **No record of the cap.** The queue's spend line didn't print the cap. Nobody read the launcher's environment, because it also held the API key.

**What it cost.** When $925 was approved, the raise couldn't reach the gated lists. The three reruns waiting in the gate were moved out, and all five remaining reruns were launched by hand. No log records the cap in force for the three gated lists that had already run. The evidence says `CAP` was unset, so they ran under the $800 default. That cost nothing only because every one of their cells started with spend plus the $20 margin below $789.

**Next time.**
- Have the queue print the cap it enforces in every spend line and in `run.env`.
- Pass a cap change through a file that each launch reads, and that the tools hash covers. Don't rely on the environment of a long-lived process.
- Dry-run a cap change end to end before a real launch depends on it.
