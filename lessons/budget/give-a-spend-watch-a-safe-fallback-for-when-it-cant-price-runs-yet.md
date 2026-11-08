# Give a spend watch a safe fallback for when it can't price runs yet

**Experiment:** repo-discovery held-out test (EXP-13), dev lists after the test · **Added:** 2026-11-08 · **Source:** store `internal/test-run/handoff.md` (dev lists since 2026-11-08 07:35 UTC: cap check; resolved at 09:57:42)

**What happened.**
- **The watch had nothing to price from.** The dev queue's 5-minute spend watch priced tokens at a rate taken from main runs that ended `ok` or `error` with usage. The first dev cases all ended at the turn budget, and the CLI reports usage only for runs that finish (see [per-batch stops](set-per-batch-stops-and-log-spend-per-case.md)). So from 07:37 to 09:57 UTC, the watch couldn't price.
- **The fallback was too high.** Until it could price, the watch bounded spend at $0.60 a case. At 73 cases that was $43.80. Once priced, the total was $19.75, about $0.26 a case.
- **The bound would have stopped real work.** At $0.60 a case, the $200 dev cap would have stopped the running cell at about 330 cases and refused the last two lists. True spend at that point would have been about $86.

**What it cost.** Nothing in the end, because a priced line appeared at 09:57. But the run was one decision away from a false stop, and the coordinator had to watch it for two hours.

**Next time.**
- Seed the watch with a rate from comparable earlier runs, such as the test passes' pooled rate, or price runs at the turn cap from the token counts they still record. Mark each line priced that way as estimated.
- State the fallback as a multiple of a known rate, not a fixed per-case figure.
- In the smoke test, check that the watch prices a run that ends at the turn cap.
