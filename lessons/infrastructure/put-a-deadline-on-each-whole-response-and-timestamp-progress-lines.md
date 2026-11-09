# Put a deadline on each whole response, and timestamp progress lines

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** `same-org/same_org/gh.py` (`read_body`); store `docs/same-org-feasibility.md` (Fetch cost)

**What happened.** The apache hub expansion stopped at batch 376 of 441 for at least 11 minutes. Meanwhile microsoft, on the same token, kept going. The process had one socket open and a thread blocked in `poll`. `urlopen(timeout=120)` bounds each socket read, not the response, so a body that trickles in never times out. The stall was noticed late, because the progress line prints every 25 batches with no time on it. Two 401 lines near the end looked like the cause but weren't.

**What it cost.** At least 11 minutes of apache's expansion and a manual kill and rerun. The cache replayed the 378 finished batches in seconds.

**Next time.** In an HTTP client for long fetches, read the body in chunks against a deadline for the whole request, and treat a miss as a retryable timeout. Check the remaining `Content-Length` after the loop, because `read(amt)` returns short instead of raising on a cut-off body. Put a timestamp on every progress line, and check a long job against its own last line, not a neighbour's.
