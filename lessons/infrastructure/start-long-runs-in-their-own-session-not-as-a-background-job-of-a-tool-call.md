# Start long runs in their own session, not as a background job of a tool call

**Experiment:** repo-discovery held-out test (EXP-13), scoring · **Added:** 2026-11-10 · **Source:** store `internal/scoring-freeze/heldout-score-683880b/record.md` (Attempt 1: infrastructure failure, output lost); `repo-discovery/PREREGISTRATION.md`, addendum item 22

**What happened.**
- **The wrapper died with its shell.** The first real scoring attempt's wrapper was started with `&`, as a background job of an agent's shell tool call. When the call returned, about 25 s in, the wrapper died with it and took the attached `docker run` output stream along.
- **The container's log went with it.** The container ran on and exited 1 by itself. `docker/run.sh` always passes `--rm`, so the container's log was deleted when it exited.
- **The cause was never seen.** The scorer's error message is lost. The wrapper died before writing the exit code, and only Docker's event log recorded it.
- **The fix worked.** Attempt 2 ran the wrapper under `nohup` in its own session (`setsid`), named the container, and kept a second copy of its output with `docker logs -f`. That copy printed the error in full. The scored run at `ae33125` ran the same way.

**What it cost.**
- One blind scoring attempt on the frozen commit, counted as an infrastructure failure.
- Its cause can only be inferred ("most likely the same check"), and the run record needed a section on what the cause wasn't.

**Next time.**
- **Detach anything that must outlive the tool call.** Use `nohup` and `setsid`, or tmux, with stdin from `/dev/null`, output to files, and the wrapper writing its own exit code.
- **Keep a log that doesn't depend on the launching shell.** Name the container, and either copy its log to a file with `docker logs -f` or drop `--rm` for runs whose log you need.
- **Test the wrapper first.** Before the real run, start it, end the call, and check from a new call that it's still running.
- **This is a different failure from a VM pause.** Holding the turn open ([hold the turn open](hold-the-turn-open-while-background-runs-go.md)) doesn't keep a background job alive once its own call returns.
