# Probe a benchmark for shortcuts before building methods on it

**Experiment:** repo-discovery, study-question review · **Added:** 2026-11-09 · **Source:** store `docs/study-question-review.md` (Part 1; Part 4: The owner shortcut); store `docs/v5-memory-checks.md` (Results; Closed-book: memory is close to enough; What is left); store `docs/v5-cursor-agent.md` (What stands out); store `docs/packet-construction.md` (Target against decoy: the confound check)

**What happened.** V0 to V5 and a selection over 491 combinations were built and tuned on WideSWE before anyone asked how much of it a shortcut could solve. The probes came later, one report at a time. On the 61 dev cases:
- **Memory.** A closed-book agent, given only the candidates' names, scored CompleteRecall@10 0.93 at U1000 with real names, against 0.97 with packets (`v5-memory-checks.md`, Results).
- **A feature that isn't the request.** Doc bytes alone separate targets from decoys with an AUC of 0.84–0.85 from U250 to U10000 (`packet-construction.md`, Target against decoy). Ranking by them solves few cases, but `bm25f` leans on them.
- **An easy first stage.** Every case's targets share one owner. Within the true owner's repositories (median 45 at U1000), random order scores 0.05 and `bm25f` at L4 0.74 (`v5-memory-checks.md`, Closed-book). The agent's first grep of the candidate list includes an owner prefix in 80 of 122 runs at U250 and U1000 (`v5-cursor-agent.md`, What stands out).
- **The request.** 33 of 61 dev requests name a target repository verbatim (`v5-memory-checks.md`, What is left).

**What it cost.** The review found that the size axis mostly measures "find the owner, then pick two or three of its few dozen repositories", with memory doing much of the work under real names. The shortcuts became caveats instead of being designed out. The cheapest direct test, a collapsed-owner run at U5000 (about $50–55), is now an exploratory extra that needs approval.

**Next time.** Before building any method, run four probes on dev, and change the benchmark if one comes close to the method you expect to win:
- a closed-book model given only the candidates' names;
- a ranker on one feature that isn't the request (doc bytes, packet size), with its target-against-decoy AUC;
- an oracle for any easy first stage, such as the owner: score random order and the baseline within it;
- the share of requests that name a target.

These test the benchmark. The [memory controls](plan-memory-controls-for-llm-and-agent-methods.md) and [shortcut rankers and matched pools](make-sure-nothing-but-the-signal-separates-targets-from-distractors.md) then test each method on it.
