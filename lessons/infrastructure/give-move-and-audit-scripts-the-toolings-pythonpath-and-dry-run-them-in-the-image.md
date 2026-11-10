# Give move and audit scripts the tooling's PYTHONPATH, and dry-run them in the image

**Experiment:** repo-discovery held-out test (EXP-13) · **Added:** 2026-11-08 · **Source:** store `internal/test-run/post-fix-run-audit.md` (list 10's audit containers; reruns-f cell 3, moved aside); store `internal/test-run/handoff.md` (`.local/ops/` move scripts; dev lists' spend watch)

**What happened.** On the test host, each container needed the coordinator's approval and had to be read-only and short. Three times a helper failed to import the repo's code:
- **An audit container** (`rd-aud-wk10`, 2026-11-07 10:23 UTC) exited before reading any data. Its script imported `spend.py`, which needs a module from the repo's `scripts/`.
- **The move-aside container** for the two failed hidden-name passes (`rd-move-g`, 16:18) exited before moving anything. It ran `spend.py` without `-e PYTHONPATH=/work/repo-discovery/src:/work/repo-discovery`, which the tooling scripts pass.
- **The dev queue's spend watch** failed once on `ModuleNotFoundError`, because it ran before the entrypoint's editable install had finished.

**What it cost.** Two failed containers on the test host, each followed by a second approval and a rerun. The audit container and its rerun ran while a test cell was running. The failed runs read and moved no data.

**Next time.**
- Run every helper that imports the repo with the same `PYTHONPATH` that the tooling passes, or install the package in the image.
- Keep audit scripts to the standard library where you can.
- Dry-run each new script in the same image, against a scratch volume, before the slot it's needed in. See [dry-running a driver against a scratch root](dry-run-a-driver-against-a-scratch-root-because-its-redirects-still-write.md).
