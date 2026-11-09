# Preregistration: complete-set repository discovery, held-out test

Status: **registered 2026-11-01.** The commit that adds this file to
`ForeverTheIntern/experiments`, and its timestamp, are the registration. Every script
that touches a test case requires `--registered <that commit>` and checks that the
checkout descends from it (`repo_discovery.split.check_registered`). Nothing below may
change once a test case has been read, except as a dated entry in §7. **The registration
is commit `76882feff7c84eb5fafea3cd404bebc5b109411f` (2026-10-31T23:45:38-07:00).**
Commit `8844fc5`, 35 seconds earlier, added the unedited draft by mistake. The commit
after the registration adds only this paragraph. No test case was read in between.

When this was written, no test case had been run, scored or inspected. The test split (59
cases, 30 ecosystems) was verified unreadable inside the agent sandbox during the dev
study. The corpus rebuild below read the test cases' repository lists and commits, which
it needs to fetch their packets, but not their requests, and scored nothing.

## 1. Question

Given a pre-change natural-language request and a universe of N candidate repositories,
does a method put **every** repository the change required within its top K? Methods
were developed and frozen on the 61 dev cases (11 ecosystems). This registration fixes how
the frozen methods are evaluated once on the 59 held-out test cases (30 ecosystems).

## 2. Data

- **Cases:** WideSWE release 120 at commit `1ed82442bfde7d7ca25d3fab69e074d318c2b783`, split by ecosystem with seed `20261028` (`splits/wideswe-release120.json`).
- **Universes:** nested U50 ⊂ U250 ⊂ U1000 ⊂ U5000 ⊂ U10000 per case, composed from the committed layers (`scripts/universe/manifests/`), rebuilt on 2026-10-31 and 2026-11-01.
  - 19 snapshots couldn't be fetched (deleted or force-pushed repositories) and have no evidence. They leave 0 rows without evidence at U50 and U250, 82 at U1000, 316 at U5000 and 319 at U10000, out of 1.2M rows over 120 cases; at U10000 that is 167 dev rows and 152 test rows.
  - No gold repository lacks evidence. These rows stay in their universes, as candidates with empty packets.
- **Fetch levels:** L0 names; L2 README; L3 README and manifests; L4 full packet; L5 names, plus packets opened on demand (`fetch_levels.py`).
- **Hidden names:** every size is anonymized from **one new salt**, in one build (`anonymize_corpus.py` at U10000, smaller tiers nested with `anon_nested_tiers.py`). The dev salts are lost. The salt check on dev found agent results unchanged across salts, within the same-salt repeat (+0.02).
- **Gold labels (primary):** WideSWE's `included_in_task` targets at their base commits.
  - Reviewed labels (`scripts/labels/`) are a preregistered sensitivity analysis. If two-reviewer adjudication of the test cases finishes before submission, the paper reports both and states which is primary here: WideSWE's.

## 3. Frozen methods (the selection step, EXP-28)

Picks come from the dev selection table. The primary pick assumes one fetched and indexed
universe serves many queries, so only per-query costs count. The secondary pick is the
winner among methods with no up-front fetch. Agent: Cursor's `cursor-agent` CLI, model
`composer-2.5`, 300 s and 20 tool turns per case, one follow-up turn, each case in its own
namespaces.

| Size | Names | Primary | Secondary |
|---|---|---|---|
| U50 | real | agent, L2 packets | `hybrid-rrf` at L0 (deviation 1) |
| U50 | hidden | agent, L2 packets | `name-match` |
| U250 | real | agent, L3 packets | agent, L5, N = 10 |
| U250 | hidden | agent, L2 packets | `bm25f-open50` |
| U1000 | real | agent, L3 packets | agent, L5, N = 50 |
| U1000 | hidden | agent, L4 packets | agent, L5, N = 50 |
| U5000 | real | agent, L4 + `search_repos` (hybrid) | agent, L5, N = 20 |
| U5000 | hidden | agent, L4 + `search_repos` (`bm25f`) | agent, L5, N = 50 |
| U10000 | real | agent, L4 + `search_repos` (`bm25f`) | agent, L5, N = 20 |
| U10000 | hidden | agent, L4 + `search_repos` (`bm25f`) | agent, L5, N = 20 |

That's 17 agent cells. Search-tool cells read each case's prebuilt index into memory
before the agent starts.

**Baselines and controls, all static, run at every size and both name conditions:**
- `random` and `name-match`;
- `bm25f` at L4; `bm25-cards`; `dense-cards`; `hybrid-rrf`;
- `bm25f-deps` and `bm25f-deps-random` (5 draws);
- `contract-joins` and `bm25f-contract-text`;
- `bm25f-open<N>` for N in {0, 5, 10, 20, 50};
- the equal-budget scripted explorers `scripted-search` and `scripted-open<N>` for N in {5, 10, 20, 50}.

## 4. Metrics and analysis

- **Primary metric:** CompleteRecall@10 (every gold repository in the top 10), the metric the picks were frozen on.
- **Key secondary:** CompleteRecall@20, the design's investigation budget. Also Hit@10, RequiredRecall@10 and LastRequiredRank. LastRequiredRank is censored at 101.
- **Intervals:** 95% percentile bootstrap resampling test ecosystems (2,000 resamples, seed 0). Paired differences are per case on the same resamples. Every comparison also reports cases won and lost.

### Confirmatory hypotheses (one family, Holm-adjusted at α = 0.05, one-sided)

- **H1.** At U5000, the primary pick beats `bm25f` at L4 on CR@10, under real names and under hidden names (2 tests).
- **H2.** At U5000, the primary pick beats `scripted-search` on CR@10, real and hidden (2 tests).
- **H3.** At U5000, the agent at L5 with budget N beats `scripted-open<N>` at the same N, using the secondary pick's N, real and hidden (2 tests).

A test is a paired bootstrap of the CR@10 difference. The one-sided p is the share of
resamples with a difference ≤ 0.

### Secondary analyses (reported with intervals, no confirmatory claim)

- The same comparisons at U1000 and U10000, and on CR@20.
- Static mechanism replications at U5000: `hybrid-rrf` vs `bm25f`; `dense-cards` vs `bm25-cards` (same text); `bm25f-deps` vs `bm25f-deps-random`; `contract-joins` vs `bm25f-contract-text`.
- Hit@10 against CR@10 for every method: the "one target is easy, all are hard" gap.
- The cost frontier on test, with the dev selection's rules and 10% tolerance.
- **Agent stability:** 2 passes for every agent cell. Report each pass, the pooled mean, and pass-2 minus pass-1 per cell.

### Exploratory (labelled as such)

- **Change memory:** agent cells split by whether the case's last target merge precedes 2026-03-01, composer-2.5's reported knowledge cutoff (`scripts/model_cutoffs.py`). Test has 25 cases before and 34 after.
- Reviewed labels against WideSWE labels.
- Per-case error analysis of misses.

## 5. Run rules

- Every test cell runs from one pushed commit, named in the results.
- **Provider errors** (not timeouts, not the turn budget) are rerun whole once, automatically (`rerun_provider_errors`). A case that still errors is scored as written and listed. Timeouts and turn-budget stops stay as written.
- Sessions refused before their first turn are retried up to 3 times (15, 60 and 180 s pauses).
- The agent runs at most 4 cases at once, and at most 2 search-tool streams at once.
- **Spend:** test agent spend is capped at **$650** in total, with a stop before any batch that would cross it. This allows 2 passes at the dev per-case rates (about $214 a pass) plus a 50% margin. If the cap would bind, pass 2 is cut for the secondary picks first, then for the primary picks at U50 and U250. The cut is reported.
- No method, prompt, budget or K changes after the first test case is read.

## 6. Deviations from the dev setup, known before the test run

1. **U50 real-name secondary:** the dev pick was the hybrid over LLM-written name cards (0.70). There's no OpenAI key, so its listed alternate, `hybrid-rrf` at L0 (0.69, one case behind), runs instead.
2. **CLI version:** `cursor-agent` 2026.10.22 replaces the version the dev runs used. The model is the same, `composer-2.5`.
3. **Corpus rebuilt** from the committed layers (§2). Gate passed before registration: `bm25f` at U5000, real names, dev reproduces CR@10 0.443 [0.231, 0.660] and Hit@10 0.770, matching the V0 pilot (0.44 [0.23, 0.66]; 0.77).
4. **New hidden-name salt** for all sizes (§2).
5. **Harness fixes:** pre-turn retry, provider-error rerun, run-purpose key, per-run namespaces, warmed indexes ([PRs #22](https://github.com/ForeverTheIntern/experiments/pull/22), [#24](https://github.com/ForeverTheIntern/experiments/pull/24), [#32](https://github.com/ForeverTheIntern/experiments/pull/32)).
6. **Runner:** a Docker Linux container on a laptop (`docker/run.sh`) instead of cloud VMs. Latency isn't comparable to dev and is reported only as a within-test comparison.

## 7. Deviations after registration

1. **2026-11-01, corpus copy carried macOS metadata files; 15 agent cells withdrawn and rerun whole.**
   - **Cause.** The corpus was extracted on the macOS host and streamed into the Linux runner's volume with macOS `tar`. That tar adds AppleDouble `._<name>` entries for files carrying extended attributes, and the files first copied out of a container carried one. So the volume's corpus held 307,719 `._*` files in packets (4,613 in sidecars, 681 in the L3 copy), and the hidden-name build copied them.
   - **What it touched.** The files hold Docker ownership metadata, no repository or case content, but packets must hold only repository files and `paths.txt`.
   - **Withdrawn.** Every test agent cell run in the volume before the fix: pass 1 of the real-name L3, L5 and search-tool cells, every hidden-name cell, and the partial passes 2. 977 cases, $173.87. They are kept under `runs/withdrawn-appledouble/`, and none is scored.
   - **Kept.** `u50-real-c1-L2`, both passes. The L2 copies held no `._*` file.
   - **Fix.** All `._*` files were deleted from the volume's corpus and levels; its file count then equals the host corpus's (1,871,832). The hidden-name build was redone from the clean host corpus with the **same salt**.
   - **Rerun.** Every withdrawn cell is rerun whole, both passes, on code that descends from the registration. Spend stays under the $650 cap, which counts the withdrawn runs.
   - **Static rankers** ran on the host's clean corpus and are unaffected. The rebuild gate (`bm25f` 0.443 at U5000 on dev) was measured there too.
2. **2026-11-01, infrastructure changes after registration, none to any method:**
   - prebuilt indexes are keyed by repository and snapshot instead of absolute path, so they can be built on the host ([PR #35](https://github.com/ForeverTheIntern/experiments/pull/35));
   - `anonymize_corpus.py --resume` restarts a build that ran out of memory;
   - agent cells run in a Docker VM limited to about 8 GB, with at most 2 to 3 cells at once.
3. **2026-11-01, a weak H2 control, noticed after registration, so not a deviation.** On dev, `scripted-search` scores CR@10 0.295 at U5000 with real names, below `bm25f` (0.443). H2 stays as registered; the paper reports this dev number beside it and treats H1 as the stronger test.
4. **2026-11-04, the rest of the test run stays on the laptop's Docker Linux runner, with two checks before every cell.**
   - Every test agent cell still to run, including the reruns of entry 1, runs on the runner of deviation 6 (`docker/run.sh`, volume `rd-data`) on the macOS laptop, from a pushed commit that descends from the registration.
   - `cursor-agent` is pinned to 2026.10.22, the version in deviation 2. The model, the per-case budgets and the run rules of §5 are unchanged.
   - Before every agent cell, the runner's `cursor-agent --version` must read 2026.10.22, and the corpus, levels and hidden-name build that the cell reads must hold no `._*` file (entry 1). A cell that fails either check doesn't start.
5. **2026-11-04, the test spend cap rises from $650 to $800.**
   - At dev per-case rates, the registered agent passes still to run cost about $420. With the $173.87 of the withdrawn runs and about $7 for the kept `u50-real-c1-L2` passes, $650 left about 12% for rates above dev, so the cap could force the pass-2 cut of §5. $800 leaves about 47%.
   - The change is inference-neutral and decided on cost alone. The cap only decides whether pass 2 runs: no method, case, prompt, per-case budget, K or analysis changes. The cut rule of §5 still applies at $800.
6. **2026-11-04, exploratory additions, none confirmatory.** None of these enters H1–H3 or the secondary analyses of §4, and no pick in §3 changes. They're reported under the Exploratory heading of §4.
   - **L5 N = 50 at U5000 and U10000 with real names, on test, 2 passes each.** The dev selection froze N = 20 for both on an exact tie broken on cost. These cells run only after every registered cell has both passes, so although they count toward the cap (about $49 at dev rates), they can't cause a pass-2 cut of a registered cell.
   - **A second dev pass of the three one-pass `c2` picks:** U5000 real `hybrid-rrf`, U10000 real `bm25f` and U10000 hidden `bm25f`. It runs on dev cases only and is outside the test cap (about $49 at dev rates). The hidden-name pass uses the same dev salt as its first pass, and the search indexes are rebuilt under the digests of [PR #35](https://github.com/ForeverTheIntern/experiments/pull/35). It's reported beside the frozen one-pass numbers; the picks and the selection table stay frozen.
   - **The timing pass and warm replay,** on the laptop runner after the test run. This is the selection step's timing pass (`c1` L4, L5 N = 5 and `c2` `bm25f`, real names, U250 to U10000, dev cases) and the $0 warm replay of U10000's real-name L5 + search. Every timing cell carries `purpose = "timing"` (`Cell.purpose`, [PR #32](https://github.com/ForeverTheIntern/experiments/pull/32)), which keeps it out of quality numbers and frontiers. Its latency is the laptop's, as in deviation 6, so it isn't compared with dev-run latency.
7. **2026-11-04, a revoked API key, an unpushed start commit and a concurrency check; 22 test passes withdrawn and rerun whole.** The audit read only commits, timestamps, exit codes, error messages, trace status fields and case counts, and no prediction or score.
   - **Revoked key.** From 19:21 UTC on 2026-11-01, the API key in the queues' environment was rejected ("The provided API key is invalid"), so every case started after that failed before opening a session. The harness retried and reran each case as §5 says and then wrote its fallback ranking, so nothing stopped the queue. 697 cases failed this way, with 0 tokens: every case of 10 passes, and part of 4 more (pass 1 of `u5000-hidden-c2-bm25f-L4`, `u10000-real-c2-bm25f-L4` and `u10000-hidden-c2-bm25f-L4`, and pass 2 of `u5000-real-c2-hybrid-L4`). The model was never reached, so these aren't §5's provider errors, and all 14 passes are withdrawn.
   - **Unpushed commit.** Pass 1 of `u250-real-c1-L3`, `u250-real-l5-n10` and `u5000-real-c2-hybrid-L4` started at 11:30 UTC on 2026-11-01 from `45f673c`, before it was pushed, in a tree with uncommitted edits the harness doesn't import. The harness code matches later commits', but §5 requires a pushed commit, so the three passes are withdrawn.
   - **Concurrency.** The other passes ran with 4 to 6 cells at once, more than entry 2's 2 to 3; each cell kept §5's limits. Before any score was read, this rule was fixed: a pass's timeout rate and provider-error rate, in cases, must each be within the range of the same cell's dev runs in the selection table, or at most 1.5 × their pooled rate where that is non-zero. 10 of the 15 passes met it. 5 didn't and are withdrawn: pass 1 of `u50-hidden-c1-L2` (1 provider error; dev 0), `u1000-hidden-l5-n50` (2 timeouts; dev 0) and `u5000-hidden-l5-n50` (1 timeout; dev 0), and pass 2 of `u5000-real-l5-n20` (3 provider errors in 59 cases; dev at most 1 in 61) and `u10000-real-l5-n20` (2; the same).
   - **Kept.** 10 passes, all run from the pushed `f85b205`: pass 1 of `u250-hidden-c1-L2`, `u1000-real-c1-L3`, `u1000-hidden-c1-L4`, `u1000-real-l5-n50`, `u5000-real-l5-n20` and `u10000-real-l5-n20`, and pass 2 of `u250-real-c1-L3`, `u250-real-l5-n10`, `u1000-real-c1-L3` and `u1000-real-l5-n50`. `u50-real-c1-L2` stays kept under entry 1. Their run times aren't comparable, so no latency is reported from them; the timing pass of entry 6 covers latency.
   - **Withdrawn.** The 22 passes are kept under `runs/withdrawn-invalid-key/`, `runs/withdrawn-unpushed-commit/` and `runs/withdrawn-concurrency/`, and none is scored. Their spend counts toward the cap, which stands at $402.23 spent, including entry 1's runs.
   - **Rerun.** Each of the 22 passes is rerun whole from `c4b458f`, one cell at a time. The 7 passes of the four U5000 cells, which feed H1–H3, run first. The other 15 follow by estimated cost, cheapest first, with a cell's pass 1 before its pass 2. A pass starts only if its duration estimated from earlier passes, plus 25%, ends before the host's run window closes; one that doesn't fit waits for the next window. A pass stopped before it ends, for any reason, is moved aside and rerun whole. A cell's two passes can come from different commits and hosts, and the results name both. At the test passes' own rates the reruns cost about $240, for a total of about $640, or about $690 with entry 6's N = 50 cells. If a rerun would cross $800, the run stops before any pass-2 cut, and the cut is recorded here first.
   - **Runner.** Replacing entry 4's "on the macOS laptop", the remaining cells run on the Docker Linux runner of deviation 6 (`docker/run.sh`, volume `rd-data`) on a host Andrew provides, with `cursor-agent` 2026.10.22 (entry 4). Each pass's `run.env` names its host, commit, image and CLI version, and a pass never resumes on another host. If the volume moves to a new host, it's copied whole. Before any cell runs there, its checksums must match the source's, and the corpus must hold 1,871,832 packet files and no `._*` file (entry 1). The timing pass and warm replay of entry 6 run on one host, which their run metadata names.
   - **Checks added before every cell,** beyond entry 4's: a $0 `cursor-agent models` with the run's key must list `composer-2.5`, and the CLI's background update check points at a closed local port, so no update can install mid-run. A trace whose error says the key was rejected stops its cell and the queue, and so does a pass that ends without a prediction and a trace for all 59 cases.
   - **Also.** The volume held 189 more AppleDouble `._*` files outside everything a cell reads: 2 at its root and 187 under its caches. They were listed and deleted.

### Addendum to entry 7, 2026-11-08: the reruns, recorded before any test pass is scored

Entry 7's reruns ran from 2026-11-04 20:33 to 2026-11-08 05:43 UTC. This addendum records every way they departed from entry 7 and §5, and the conditions they ran under. Item 14 also records how entry 6's L5 N = 50 test passes were to run, set before they ran, and how they ran. Andrew answered the open decisions on 2026-11-08 at 23:56 UTC, before any score was read. He also set a standing rule: bias toward the decision that keeps the experiment's integrity and academic rigor. His answers are in items 2, 3, 6 and 13. Items 15 to 21 were added on 2026-11-09, before any test score was read. Items 15, 16 and 18 record three deviations from the registration's text: how H1–H3 combine a cell's passes, cells whose passes ran from different commits, and entry 7's bound for withdrawing a pass. Item 17 declares exploratory analyses, and item 19 changes one of its definitions. Item 20 records which static runs are scored, and how `merge_dates` is built. Item 21 reruns the embedding cells with an empty vector store and scores those reruns. The addendum was written from the run's blind audit records: commits, queue and launch logs, `run.env` stamps, exit codes, case and attempt counts, trace status fields, per-case tool-call counts and timestamps. No prediction, ranking, metric or score of a test pass was opened to write it. Entry 7's text above is unchanged; where the two differ, this addendum governs.

**Result.** All 34 registered test passes (17 agent cells × 2) are accepted: 31 on their first counted try and 3 on their second (item 2). Each accepted pass has 59 predictions and 59 traces, 0 timeout cases and 0 provider-error cases (item 4). Each of the 22 passes whose method gives the agent an MCP tool meets the tool bound (item 1). Every accepted rerun ran from `c4b458f` with `cursor-agent` 2026.10.22-27dcf5f, and entry 7's 22 ran in runner image `sha256:9fd01807…c48906`. The other 10 accepted passes are those kept from 2026-11-01 under entry 7, all run from the pushed `f85b205`. The 2 `u50-real-c1-L2` passes kept under entry 1 recorded no commit. By the worktree's reflog, pass 1 ran on the pushed `15ec4ed`, and pass 2 ran on `45f673c` before it was pushed. Both were withdrawn unread and rerun whole on 2026-11-09 (item 13). Test spend was **$862.41** when entry 7's reruns ended, above entry 5's $800 cap (item 6). It was **$921.70** after entry 6's N = 50 passes (item 14) and item 13's reruns.

1. **The MCP tool didn't reach its server in 6 accepted passes, in all or most of their cases; a tool bound was added.**
   - **What happened.** In some cases the CLI started without the `repo-discovery` MCP server in its tool registry. From 2026-11-04 20:48 to about 2026-11-05 01:10 UTC, the agent called `search_repos` or `open_repo`, and the CLI refused every call locally, so the server logged none. In a second window, starting between 2026-11-05 08:28 and 16:40 UTC and ending between 2026-11-06 18:49 and 23:56 UTC, the agent found no such tool and never called it. The CLI binary was pinned and identical throughout, which rules it out; the cause isn't confirmed. Entry 7's bound counted only timeouts and provider errors, so all 6 passes had passed it. The failure was found on 2026-11-07, before 06:40 UTC, by comparing, per case, the MCP calls in the CLI's event log with the calls in the server's log.
   - **The 6 passes:** p1 and p2 `u5000-hidden-l5-n50`, p2 `u5000-real-l5-n20`, and p1 and p2 `u5000-real-c2-hybrid-L4`, all from queue reruns-a in the first window (p2 hybrid's server logged calls in 15 of 59 cases, the others' in none); and p2 `u10000-hidden-c2-bm25f-L4`, from reruns-c in the second. They were moved aside unread to `runs/withdrawn-tool/` on 2026-11-07 at 07:26 UTC and rerun whole. Their $57.08 stays in test spend.
   - **Withdrawn runs that also fail the tool bound: 13.** 4 ran in the second window: the withdrawn U10000 runs of reruns-b, reruns-c and reruns-e. The other 9 ran on 2026-11-01 and were already withdrawn under entry 7. Among them are 4 revoked-key passes, whose cases after the key was rejected never opened a session. The other 5 are the 4 concurrency passes with a tool and the unpushed-commit p1 `u5000-real-c2-hybrid-L4`, and in 3 of these 5 the failure began mid-cell. In the one read with the filter of item 10, withdrawn-concurrency p1 `u5000-hidden-l5-n50`, the CLI refused the agent's calls as in the first window. So the failure wasn't confined to the two windows. The sources don't say when on 2026-11-01 it began. Every pass kept from 2026-11-01 whose method gives a tool reached it in all 59 cases.
   - **The tool bound.** Adopted on 2026-11-07 at about 06:40 UTC, before any score was read. It applies to every pass of a method that gives the agent an MCP tool, beside the bound of item 4:
     - (a) 0 cases in which the CLI recorded MCP calls and the server logged none;
     - (b) at most 2 of 59 cases with no MCP call at all.
     - (b) isn't 0 because two working passes from 2026-11-01, withdrawn under entry 1, had 1 and 2 cases in which the agent made no call, and the CLI and server logs agree on them. Replayed over all 79 test and withdrawn passes on the volume, the bound flags exactly the 19 broken ones. Every accepted tool pass has a server-logged call in all 59 cases, so it meets the strict form too.
   - **Guards, installed 2026-11-07 07:26:22 UTC, from list 10 on:**
     - the queue stops a cell, as an infrastructure failure, when its 3 most recently finished cases have no server-logged call;
     - after each cell, it checks the tool bound and logs a WARN if it fails;
     - before each launch, a tool preflight runs one real-name U250 dev case for each tool the list uses, and refuses the launch unless the server logs a call that the CLI reports `ok`.
     - The preflight shows that the tool reaches its server, not that the cell's own method and index work; there are no dev search indexes at the test sizes. Its cases are dev spend, outside the test total.
   - **The dev picks are unaffected.** All 73 dev passes picked in §3 whose method gives a tool used it in all 61 cases. Every dev run predates 2026-11-01, but since the failure also hit runs that day, the date alone doesn't clear them. For 67 of them the server's own log shows the calls. For the 6 EXP-19 `c2` picks on `d292f80`, the export holds only the CLI's call counts, so a refused-call failure like the first window's isn't ruled out for them; their dev traces would settle it.
   - **Not yet tested:** the harness passes the CLI no `--approve-mcps`. If the service changed when a headless session's MCP servers need approval, that would explain every broken run. It's to be tested on dev cases only, after the test run.

2. **Infrastructure-failure reruns, and the recount of tries.**
   - **The recount.** A try counts only if the pass ran to its end with its MCP tool reached (or with no tool) and was audited against its bound. These don't count: a withdrawal under entry 1 (AppleDouble files) or entry 7 (revoked key, unpushed commit, concurrency), a pass stopped before its end, and a pass that fails the tool bound. Each of these is an infrastructure failure, and the pass is rerun whole as entry 7 says. The coordinator proposed this on 2026-11-07 at about 07:00 UTC. On 2026-11-07 at 16:14 UTC, Andrew approved both hidden-name reruns below, as the coordinator relayed, and the run took that as acceptance of the recount. Andrew confirmed the recount explicitly on 2026-11-08 at 23:56 UTC. No score had been read at either time.
   - **What it replaced.** Before the outage was known, the run had fixed two "last run" rules: p1 `u10000-hidden-c2-bm25f-L4` would get no third run (2026-11-06 04:30 UTC), and p2 `u10000-real-c2-bm25f-L4` no fourth (2026-11-07 03:40 UTC). Their earlier runs in reruns-b, reruns-c and reruns-e never reached the tool, so under the recount they aren't tries.
     - p2 real-name's counted tries are reruns-f (3 timeout cases and 1 provider-error case) and then list 10, which passed.
     - p1 hidden's first counted try is reruns-f's cell 3 (1 timeout case). p2 hidden's tool-broken reruns-c pass doesn't count, so its first counted try is list 12a (1 timeout case).
     - Both hidden cells were rerun once more, in queue reruns-g, and both passed.
   - **Cell 3's timeout** was judged under a rule the coordinator fixed before the case was examined. It counts as an infrastructure failure only if (a) time outside the agent's turns counted against the 300 s limit and the case's setup took more than twice the cell's median, and (b) with median setup the run would have ended under 300 s. Neither held: setup took 116.6 s against a median of 105.0 s, and setup isn't on the 300 s clock. So it's a method timeout, and the pass failed as it stood. List 12a's timeout case wasn't examined; the pass failed on it as it stood.
   - **Counts.** 31 passes are accepted on their first counted try, among them item 13's two `u50-real-c1-L2` reruns. 3 are accepted on their second: p2 `u10000-real-c2-bm25f-L4` (list 10), and p1 and p2 `u10000-hidden-c2-bm25f-L4` (reruns-g). Item 12 lists each pass's tries and withdrawn copies. Every withdrawn copy stays under `runs/withdrawn-*/`, counts toward test spend, and is never scored.

3. **Rerunning a pass until it has 0 timeouts selects the runs that are accepted.** Every accepted pass has 0 timeout cases, because a pass with any was withdrawn and rerun whole. Under §5 alone, timeout cases would have been scored as written. So each accepted pass is conditioned on every case's main run ending within 300 s, and a cell that needed more runs went through that filter more times. Such a cell is more likely than a first-try cell to have been accepted on a run in which the provider or the agent happened to be fast. The recount (item 2) allowed the extra runs of the two hidden cells.
   - The 3 failed counted tries are all U10000 `c2-bm25f-L4` passes, which enter §4's secondary analyses, not H1–H3.
   - Runs withdrawn for other reasons also held timeouts, and their reruns went through the same filter. 8 of the passes run on 2026-11-01 after entry 1's fix had 1 to 12 timeout cases each, among them 4 U5000 passes that feed H1–H3; the AppleDouble copies weren't counted. And 4 U10000 runs in reruns-b, reruns-c and reruns-e that never reached the tool had 1 to 28 each.
   - The withdrawn copies are never scored, so the size of the effect can't be measured blind.
   - **How it's reported.** Andrew decided this on 2026-11-08 at 23:56 UTC, before any score was read. The write-up states the selection effect as a limitation, beside item 12's per-pass table of tries. It makes no adjustment or sensitivity analysis for it.

4. **The audit bound for rerun passes.** On 2026-11-04 at 20:28 UTC, before any rerun started, Andrew asked that every rerun pass meet the rule entry 7 applied to the passes it kept, with the dev-run mapping extended to the rerun cells by the same rule, before it's scored. For every rerun cell but one, that's 0 timeout cases and 0 provider-error cases. `u1000-hidden-c1-L4` allows 29 provider-error cases. Entry 7 applied the rule because cells had run 4 to 6 at once; the reruns ran one cell at a time, and the bound still withdrew any pass with a timeout case (item 3).
   - **Provider-error case,** defined by Andrew on 2026-11-04 at 21:18 UTC and clarified at 21:26 UTC, before any rerun was audited: a case whose run was rerun whole after a provider error (`provider_error_rerun`), or whose final `status` or `follow_up_status` is `error`. It replaces the definition behind entry 7's counts, for every pass. Under it, entry 7's pass 2 of `u10000-real-l5-n20` has 1 provider-error case, not 2. That's still above its dev bound, so no keep or withdrawal of entry 7 changes.
   - **Logged and not counted:** pre-turn retries, where a session was refused or stalled before its first turn and was retried as §5 says, and non-provider fallbacks, where a case wrote its fallback ranking after `turn_budget`, or after a follow-up that timed out or hit its turn limit. Item 12 gives them per accepted pass: 4 pre-turn retries in 4 passes, and 19 non-provider fallbacks in 13 passes. Item 9 covers the one run that took 3 attempts.
   - **The timeout bound stayed at 0** when pass 2 of `u10000-real-c2-bm25f-L4` failed on 1 timeout case in reruns-e. The coordinator decided this once that pass had ended, since every pass accepted until then had met it.
   - **A pass that fails its bound** isn't rerun by the queue; the coordinator and Andrew decide. Every such pass was withdrawn unread and rerun whole.

5. **Queues, start rules and stops.** The 7 passes of the four U5000 cells that feed H1–H3 ran first, as entry 7 says; 5 of them failed the tool bound and were rerun last (item 1). Entry 7's start rule, an estimated duration plus 25% that must end before the host's run window closes, was used only by the first queue. Each later queue's start rule was set from observed durations before its launch, except reruns-b's, which had none and a hard stop instead. Two passes were stopped by hand, and as entry 7 says, each was moved aside and rerun whole. reruns-c's provider errors may have come from other use of the Cursor account, though that isn't confirmed. So from reruns-e on, the launch steps asked Andrew to pause other uses of the account before each launch he made. Whether the account had other use during a pass can only be checked on the account side, and the agent sessions operating the run used the same account throughout.

   | Queue | Launched (UTC) | Start rule | Passes | Outcome |
   |---|---|---|---|---|
   | reruns-a | 11-04 20:33 | estimate × 1.25, window to 11-05 11:50 | entry 7's 22 | 18 ran and passed the bound of item 4; 5 of them later failed the tool bound (item 1). The 4 U10000 `c2-bm25f-L4` passes were skipped, needing 16.0 to 16.5 h with 3.36 h left. |
   | reruns-b | 11-05 16:21 | none (`MARGIN=0`), hard stop at 22:00 | p1 U10000 hidden | Stopped by hand at 20:50, when Andrew needed the laptop, with 46 of 59 cases. Withdrawn. |
   | reruns-c | 11-05 22:30 | observed pace × 1.1 (`MARGIN=0.44`) | p1 U10000 hidden, p2 U10000 hidden, p1 U10000 real | p1 hidden failed (15 timeout cases). p2 hidden passed, and was later withdrawn for the tool. p1 real-name was stopped by hand at 11-06 07:20, after provider errors and, from 06:13, a timeout in every case. |
   | reruns-d | not launched | | | Cancelled at 11-06 07:19, after the provider errors. |
   | reruns-e | 11-06 15:28 | longest observed pass × 1.1, 3.08 h (`MARGIN=0.233`) | p2 U10000 real, then p1 | p2 real-name failed (1 timeout case). p1 was skipped by the start rule. |
   | reruns-f | 11-06 23:41 | 3.08 h (`MARGIN=0.2403`) | p2 U10000 real, p1 U10000 real, p1 U10000 hidden | p2 real-name failed (3 timeout cases, 1 provider-error case). p1 real-name was accepted. p1 hidden (cell 3) failed (1 timeout case). |
   | list 10 | 11-07 07:27 | 3.08 h (`MARGIN=0.2329`) | p2 U10000 real | Accepted. |
   | list 12a | 11-07 09:51 | 3.08 h (`MARGIN=0.2403`) | p2 U10000 hidden | Failed (1 timeout case). |
   | list 12b | 11-07 12:30 | 3.08 h (`MARGIN=0.5256`) | p1 and p2 U5000 real hybrid | Both accepted. |
   | reruns-g | 11-07 23:15, by hand | 3.08 h for the hidden cells (`MARGIN=0.2403`) | p1 and p2 U5000 hidden L5, p2 U5000 real L5, then p1 and p2 U10000 hidden | All 5 accepted. |

   Lists 10, 12a and 12b were launched by a weekend launcher on the laptop, a long-running process that launched audited lists from a gate directory in name order until 2026-11-09 04:00 UTC. It ran each list through a one-turn preflight and the tool preflight (item 1), and refused any list that named a withdrawn pass's output.

6. **The spend cap rose from $800 to $925 for the last rerun queue only. Entry 6's N = 50 passes ran at $935 (item 14), and the `u50-real-c1-L2` reruns at $950 (item 13).**
   - Entry 7 said that if a rerun would cross $800, the run stops before any pass-2 cut, and the cut is recorded here first. Instead, the cap was raised and the run went on; no pass-2 cut was made. The tool reruns of item 1 and the hidden-name reruns of item 2 pushed the projection over $800.
   - The coordinator asked Andrew for $875 on 2026-11-07 at about 07:00 UTC. At 13:09 UTC the request changed to $925, to cover both hidden-name reruns with room for one more pass. Andrew approved it at 16:14 UTC. No queue ran under a cap of $875.
   - $925 applied only to queue reruns-g. Andrew launched it by hand at 23:15:46 UTC with `CAP=925 MARGIN=0.2403`, as its launch log records. Under $800, none of its five passes could have started: a cell starts only while spend + $20 is within the cap, and the first needed $805.22. Spend crossed $800 during its second pass.
   - The cap reaches a queue only through the environment of whatever launches it: `go.sh` passes `CAP` into the container, and `queue.sh` uses $800 when it isn't set. The weekend launcher was started before any raise, and its environment wasn't read. No log records the cap in force for lists 10, 12a and 12b. The evidence says `CAP` was unset, so `queue.sh` used its $800 default. Every one of their cells started with spend + $20 below $789. The 3 U5000 L5 reruns were held out of the gate and run in reruns-g so that they would run under the raised cap.
   - No method, case, prompt, per-case budget, K or analysis changed, and no score had been read. Unlike entry 5's raise, this one isn't clearly inference-neutral. It let the two hidden-name cells run again after a failed counted try, which adds to item 3's selection effect.
   - **Andrew's decision.** On 2026-11-08 at 23:56 UTC, before any score was read, Andrew accepted the raise as a recorded deviation, made after the fact. Scoring is unchanged.
   - **$950 for the `u50-real-c1-L2` reruns.** The coordinator raised the test cap to $950 under Andrew's budget delegation, so the two reruns of item 13 could run. Entry 5 put the two original passes at about $7, and the reruns cost $11.85.
   - **Spend.** $402.23 at entry 7, $613.84 when reruns-a ended, $785.22 when list 12b ended, and **$862.41** when reruns-g ended. Then $909.85 when entry 6's N = 50 passes ended (item 14), and **$921.70** when item 13's reruns ended. Entry 7 had projected about $240 for the reruns, for a total of about $640; the difference is the runs withdrawn during the reruns and their reruns. The total is `spend.py` over `runs/test` and every `runs/withdrawn-*` directory, plus $3.26 untraced. `spend.py` counts a rerun case's first attempt twice, so the total errs high. Two queues' running totals left out a withdrawn directory created after they started, by up to $15.09, but every start check still held on the true total. Not in the total: the one-turn preflights, about $0.006 a launch, and the tool preflights' dev cases, about $0.29 in all.
   - **Entry 6's L5 N = 50 test passes** ran after entry 7's reruns. Entry 6 put them at about $49 at dev rates, and they cost $47.44. At the default $800 cap, `queue.sh` would have refused them. The coordinator raised the cap to $935 for them under Andrew's budget delegation, and item 14 records how they ran.

7. **Hosts and tooling.**
   - **Host.** Every rerun pass ran on the macOS laptop's Docker Linux runner (`docker/run.sh`, volume `rd-data`), as entry 4 had it; that laptop is the host Andrew provided under entry 7. Its `run.env` names it `Andrews-MBP/Darwin-arm64` in reruns-a, `Andrews-MacBook-Pro/Darwin-arm64` in reruns-b, and `andrews-macbook-pro-1/Darwin-arm64` from reruns-c on. That's one machine, with 15 CPUs, whose hostname changed. The Docker engine and volume stayed the same, so the volume was never moved or copied. The 12 passes kept from 2026-11-01 ran on the same laptop and have no `run.env`; 2 of them are now withdrawn (item 13). No test pass ran anywhere else. A cloud Linux VM was set up on 2026-11-04 and dropped the same day, before entry 7 was written, because its network blocked the Cursor API. It ran no agent call and no test case.
   - **The laptop's use.** The co-host sampler sees only containers, not the laptop's own applications. Andrew's use of the laptop was logged for several withdrawn passes, but not for every pass.
   - **Tools hash.** Each queue stamps `tools=` in `run.env`. It's a hash over every file in the git-ignored `.local/run/` directory, which holds the queue scripts, the launch lists and the audit scripts, excluding `selftest/`. It changes whenever a list is added or moved, not only when a script changes. During the reruns, the scripts the queue runs changed only for the tool guards of item 1. The host-side launcher `go.sh` and an audit script were saved on 2026-11-04 after reruns-a had launched.

     | Queue | Tools hash | Passes accepted |
     |---|---|---|
     | reruns-a | `07a1bb69cc339dc7` | 13 |
     | reruns-b | `13ac2bb41c9b50f1` | 0 |
     | reruns-c | `47582c511adc2542` | 0 |
     | reruns-e | `23af0b03606f9b36` | 0 |
     | reruns-f | `8e82081bec14826c` | 1 |
     | list 10, the first with the tool guards | `0f18e450fb5020f9` | 1 |
     | list 12a | `975f1545a2589700` | 0 |
     | list 12b | `6c96053a46a231d6` | 2 |
     | reruns-g | `b67f0981f84a757b` | 5 |
     | `u50-c1-rerun` (item 13) | `67989c6537139021` | 2 |

   - **Checks beyond entry 7's:**
     - a co-host load sampler in every queue, which reads other containers' CPU for 2 minutes at each cell's start and every 30 minutes, logs a WARN above 1 core and stops the cell above 2 (none stopped);
     - from reruns-e on, a one-turn preflight before each launch;
     - from list 10 on, the tool guards of item 1.
   - **After reruns-g,** the tooling was changed for entry 6's dev lists, which changed the hash to `34e29067c97e585b` and then `ce167db78053b33c`. No test cell ran under either. Entry 6's N = 50 test passes ran under `88f1163beb4e464a` (item 14), and item 13's reruns under `67989c6537139021`.

8. **Containers on the run host.**
   - **Another project's containers** (`readiness-aud`) ran on the same Docker engine throughout and were left alone. In reruns-a, three cell-start samples read above 1 core (1.03 to 1.94 cores) and were logged as WARNs; none reached the 2-core stop. One of those passes is accepted (p2 `u1000-hidden-l5-n50`, at 1.03 cores); the other two were later withdrawn for the tool. Every sample from reruns-c on read 0.00 cores.
   - **The operating agents' own containers.** Until 2026-11-07 07:00 UTC, no rule kept them off the host, and short read-only checks and move-aside containers ran during test cells; Docker's event history no longer lists all of them. During reruns-f's cell 3 (p1 `u10000-hidden-c2-bm25f-L4`, 04:46 to 07:25 UTC), 28 containers ran on `rd-data` from 06:11 to 06:53. 24 lasted 0 to 14 s each: status reads, the tool-bound replay and the guard selftests, all with `--network none`. Two tests of the new tool preflight failed at once. Two more ran the harness for 300 s each, with network access, on one U250 dev case with a fake key, so each CLI waited on a rejected key until the limit. The second of these covered the last 59 s of setup and the first 243 s of the main run of cell 3's only timeout case. Their load wasn't sampled. The case was judged a method timeout (item 2).
   - **From 2026-11-07 07:00 UTC,** by the coordinator's rule, no containers and no Docker tests ran on the host while a test queue ran or a list was about to launch, unless the coordinator approved first. The approved exception was one short read-only audit container per finished cell: `--network none`, `rd-data` mounted read-only, `--cpus 1`, under 60 s, reading status fields and `run.env` only, logged in that cell's audit. These ran while a later test cell was running:

     | Container | Ran (UTC) | Test cell running |
     |---|---|---|
     | `rd-aud-wk10`, then `rd-aud-wk10b` (the first exited on an import error) | 11-07 10:23:15–17, 10:25:14–15 | p2 U10000 hidden, list 12a |
     | `rd-aud-wk12a` | 11-07 13:06:12–13 | p1 U5000 real hybrid, list 12b |
     | `rd-aud-wk12b1` | 11-07 14:41:33–34 | p2 U5000 real hybrid, list 12b |
     | `rd-aud-g1` | 11-08 00:21:45 | p2 U5000 hidden L5, reruns-g |
     | `rd-aud-g2`, `rd-aud-g3` | 11-08 01:23:23–25, 01:23:35–36 | p1 U10000 hidden, reruns-g |
     | `rd-aud-g4` | 11-08 03:56:45–46 | p2 U10000 hidden, reruns-g |

     The first two ran during list 12a, which failed on 1 timeout case. Whether that case overlapped them wasn't checked. The other containers after 07:00 ran with no test cell running. They include the audits after list 12b and reruns-g ended; the two `rd-move-g` containers that moved both failed hidden-name passes aside, the first of which failed before moving anything; and `rd-aud-g5r`, which read the 3-attempt run of item 9.

9. **Pre-turn retries, including one run that took 3 attempts.** Pre-turn retries are logged and not counted (item 4). One run took 3 attempts, the first logged with more than 2: the main run of one case in the accepted pass 2 of `u10000-hidden-c2-bm25f-L4` (reruns-g). Its first two attempts ended before the CLI emitted any event, so before a session opened. The harness keeps only the final attempt's record, so whether each was an error or a timeout isn't recorded. The third attempt opened a session, with its first event at 53.8 s, and ran 21 model turns to its turn budget in 126.5 s. The case wasn't rerun whole, has no `error` status, and its follow-up took 1 attempt. §5 allows up to 3 retries, so this is within it, and it isn't a provider-error case.

10. **What was read, and incidental reads.**
    - The audits read trace status and attempt fields, `parse` status, case and attempt counts, per-case tool-call counts with each logged call's outcome and CLI status, timing fields, `run.env`, and queue and host logs. No prediction, ranking, metric, score, answer or agent text of a test pass was opened.
    - **Two approved filtered reads went further.**
      - On 2026-11-07 at about 06:20 UTC, to find the outage's cause, a filter read one broken and one working withdrawn pass per window. It printed only MCP error fields, rejection reasons, the tool names in MCP tool listings, and system-event fields. No accepted pass was read this way.
      - On 2026-11-08 at 06:27 UTC, for the 3-attempt run of item 9, a filter read that one case's events in the accepted pass. It printed only event types and subtypes, run times, whether a session ID existed, and model-call counts. It printed no message text, ranking or answer.
    - **Incidental reads.**
      - A cloud worker's `grep` printed a few lines from U50 test traces: snippets of a tool's README, with no prediction or score. The same output printed three lines from `internal/selection/predictions/v1/*.jsonl` in the study's agent store. They're believed to be dev-split predictions, but that hasn't been checked. Nothing in this addendum draws on them, and no run file records them beyond this entry.
      - At about 00:15 UTC on 2026-11-09, a search by the worker writing this addendum, for its own agent ID, also ran over the store's `internal/`, `internal/test-run/` included. It was stopped, and its output, which could hold only the names of files containing that ID, was never read.
      - At about 00:19 UTC on 2026-11-09, the paper-writing-guide worker (`bc-4a3becdc-18ba-51c8-90f3-c545e2f390a8`) ran a text search over the study agent store's `internal/` folder. It printed about 16 lines from 6 trace files of the withdrawn 2026-11-01 copies of p1 and p2 `u50-real-c1-L2`, which are copied into the store under `internal/test-run/mac-runs/runs/test/`.
        - The lines were agent tool calls (grep, read and glob) with their patterns and results, README excerpts and one file listing, from five test cases. The case IDs name their target repositories, so they're kept out of this repository, in the store's `internal/incidental-reads.md`.
        - It opened no `pred.jsonl`, ranking, metric, score or final answer, and nothing from the lines was used. Those copies are withdrawn and unscored (item 13), and the reruns are fresh agent runs that this read can't influence.
      - At about 01:18 UTC on 2026-11-09, the scoring-freeze worker (`bc-224070da`) ran a ripgrep search over the whole store, with `-g '!internal/test-run/**'` to leave `internal/test-run/` out. ripgrep anchors that glob to the working directory. So it excludes nothing when the search path, as written, doesn't start at the working directory, as with an absolute path from elsewhere or through a symlink. The search named an absolute path, and it covered `internal/test-run/`.
        - It printed 30 lines from the traces of 21 test cases, all in the withdrawn 2026-11-01 copies of p1 and p2 `u50-real-c1-L2`. Each line gave a trace path, a tool-call key name (only `readToolCall` and `grepToolCall`) and a per-file match count, from 26 to 48. The case IDs are kept out of this repository, in the scoring-freeze worker's account in the store, `internal/incidental-read-tool-call-key-counts.md`. The store's `internal/incidental-reads.md` links it.
        - No event content, prediction, ranking, target or score was printed. Those copies are withdrawn and unscored (item 13), and the reruns are fresh agent runs that this read can't influence.
        - Earlier, between about 00:07 and 00:11 UTC and before the coordinator's 00:21 UTC instruction to keep out of `internal/test-run/`, the same worker had listed file names under `internal/test-run/mac-runs/` and got grep matches in notes there.
        - The scoring freeze's parser check (its item 4) reads a dev events file only.
        - That check's record, the store's `internal/scoring-freeze/dev-events-tool-keys.md`, states one fact from the test side, at line 47: the audit of item 13's pass 2 rerun counted one `editToolCall`, a CLI built-in tool. It comes from that audit's per-case tool-call counts, not from an incidental read's output, and the note is being marked as test-side. No code or test in this repository mentions `editToolCall`, and `TEST_ANALYSIS.md` names it only to say so. The first-search parser reads only grep, ripgrep and glob calls and `search_repos` calls under `mcpToolCall`.
      - Between 01:57 and 02:06 UTC on 2026-11-09, while locating `dev-events-tool-keys.md`, the laptop runner, which already audits the test traces, ran two searches over the whole store. Both covered `internal/test-run/`.
        - The searches were a file-name search for `dev-events-tool-keys.md` and a text search of `*.md` files for `incidental|editToolCall`.
        - Neither returned a file under the copied test runs, `internal/test-run/mac-runs/runs/`. The only match inside `internal/test-run/` was line 3 of `mac-runs/README.md`.
        - The runner also read the store's `internal/incidental-reads.md`, which lists the earlier reads' case IDs.
        - No result of either search was used in any code or analysis.
      - Agents now leave `internal/test-run/` out of store searches. `-g '!**/test-run/**'` excluded it in every working directory and search path tested, symlinked paths included. `-g '!internal/test-run/**'` doesn't, as the 01:18 search shows.

11. **Correction to §2.** §2 says "The dev salts are lost." That's untrue for the published dev salt. The study's agent store holds it, with the U10000 dev build made under it. Entry 6's hidden-name second dev pass would run on it, but that pass is held (item 14). The other dev salts weren't checked. The test passes used §2's new salt, which is unchanged.

12. **Each pass.** Accepted run: the queue and the start of the accepted pass (UTC, 2026). Host: as `run.env` names it, where *MBP* is `Andrews-MBP/Darwin-arm64` and *mbp-1* is `andrews-macbook-pro-1/Darwin-arm64`. Kept passes have no `run.env`. Each queue's tools hash is in item 7. Withdrawn copies are listed by directory, with the queue for those withdrawn during the reruns. † marks a copy in which the tool never reached its server. Counted tries are under item 2's recount. The two `u50-real-c1-L2` passes were withdrawn and rerun (item 13), so all 34 passes are accepted.

    | Pass | Accepted run | Host | Pre-turn retries | Non-provider fallbacks | Withdrawn copies, unscored | Counted tries |
    |---|---|---|---|---|---|---|
    | p1/u50-real-c1-L2 | `u50-c1-rerun`, 11-09 00:46 (item 13) | mbp-1 | 0 | 0 | unrecorded-commit (the kept 11-01 copy, `15ec4ed` by reflog; withdrawn 11-08) | 1 |
    | p1/u50-hidden-c1-L2 | reruns-a, 11-05 05:54 | MBP | 0 | 0 | appledouble; concurrency | 1 |
    | p1/u250-hidden-c1-L2 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
    | p1/u250-real-c1-L3 | reruns-a, 11-05 08:38 | MBP | 0 | 0 | appledouble; unpushed-commit | 1 |
    | p1/u250-real-l5-n10 | reruns-a, 11-05 06:39 | MBP | 0 | 0 | appledouble; unpushed-commit | 1 |
    | p1/u1000-hidden-c1-L4 | kept, 11-01 (`f85b205`) | laptop | 0 | 2 | appledouble | 1 |
    | p1/u1000-hidden-l5-n50 | reruns-a, 11-05 04:59 | MBP | 0 | 0 | appledouble; concurrency† | 1 |
    | p1/u1000-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 2 | appledouble | 1 |
    | p1/u1000-real-l5-n50 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
    | p1/u5000-hidden-c2-bm25f-L4 | reruns-a, 11-05 01:50 | MBP | 0 | 0 | invalid-key† | 1 |
    | p1/u5000-hidden-l5-n50 | reruns-g, 11-07 23:30 | mbp-1 | 0 | 1 | appledouble; concurrency†; tool† (reruns-a) | 1 |
    | p1/u5000-real-c2-hybrid-L4 | list 12b, 11-07 12:42 | mbp-1 | 1 | 1 | appledouble (4 cases); unpushed-commit†; tool† (reruns-a) | 1 |
    | p1/u5000-real-l5-n20 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
    | p1/u10000-hidden-l5-n20 | reruns-a, 11-05 07:02 | MBP | 0 | 1 | appledouble; invalid-key | 1 |
    | p1/u10000-real-l5-n20 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
    | p1/u10000-hidden-c2-bm25f-L4 | reruns-g, 11-08 01:21 | mbp-1 | 0 | 0 | invalid-key†; deadline† (reruns-b); timeouts† (reruns-c); timeouts-g (reruns-f, cell 3) | 2 |
    | p1/u10000-real-c2-bm25f-L4 | reruns-f, 11-07 02:31 | mbp-1 | 1 | 0 | appledouble (2 cases); invalid-key†; provider† (reruns-c) | 1 |
    | p2/u50-real-c1-L2 | `u50-c1-rerun`, 11-09 01:05 (item 13) | mbp-1 | 0 | 0 | unrecorded-commit (the kept 11-01 copy, `45f673c` by reflog, before its push; withdrawn 11-08) | 1 |
    | p2/u50-hidden-c1-L2 | reruns-a, 11-05 06:17 | MBP | 0 | 0 | invalid-key | 1 |
    | p2/u250-hidden-c1-L2 | reruns-a, 11-05 09:48 | MBP | 0 | 0 | invalid-key | 1 |
    | p2/u250-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
    | p2/u250-real-l5-n10 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
    | p2/u1000-hidden-c1-L4 | reruns-a, 11-05 09:09 | MBP | 0 | 4 | invalid-key | 1 |
    | p2/u1000-hidden-l5-n50 | reruns-a, 11-05 05:26 | MBP | 0 | 2 | invalid-key | 1 |
    | p2/u1000-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
    | p2/u1000-real-l5-n50 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble (5 cases) | 1 |
    | p2/u5000-hidden-c2-bm25f-L4 | reruns-a, 11-05 03:20 | MBP | 0 | 0 | invalid-key | 1 |
    | p2/u5000-hidden-l5-n50 | reruns-g, 11-08 00:07 | mbp-1 | 0 | 0 | invalid-key; tool† (reruns-a) | 1 |
    | p2/u5000-real-c2-hybrid-L4 | list 12b, 11-07 14:09 | mbp-1 | 0 | 1 | invalid-key†; tool† (reruns-a) | 1 |
    | p2/u5000-real-l5-n20 | reruns-g, 11-08 00:46 | mbp-1 | 0 | 0 | appledouble (4 cases); concurrency†; tool† (reruns-a) | 1 |
    | p2/u10000-hidden-l5-n20 | reruns-a, 11-05 07:34 | MBP | 0 | 0 | invalid-key | 1 |
    | p2/u10000-real-l5-n20 | reruns-a, 11-05 08:07 | MBP | 1 | 0 | concurrency† | 1 |
    | p2/u10000-hidden-c2-bm25f-L4 | reruns-g, 11-08 03:41 | mbp-1 | 1 (3 attempts, item 9) | 1 | invalid-key; tool† (reruns-c); timeouts-g (list 12a) | 2 |
    | p2/u10000-real-c2-bm25f-L4 | list 10, 11-07 07:39 | mbp-1 | 0 | 1 | invalid-key; timeouts† (reruns-e); timeouts-f (reruns-f) | 2 |

13. **The kept `u50-real-c1-L2` passes recorded no commit, and pass 2 ran on an unpushed one. Both are withdrawn and rerun whole.** Entry 1 kept both passes, because their L2 copies held no `._*` file, and entry 7 left them kept. The run recorded no commit for either: their pass directories hold only `pred.jsonl` and the traces beside the `.log`, there's no `run.env`, and neither the logs, nor the 2026-11-01 queue logs, nor `durations.json` names one. The commits below come from the git reflog of the worktree that the 2026-11-01 queues mounted. The reflog shows HEAD only, not whether the tree had uncommitted changes.
    - **Pass 1** ran 08:17:00–08:24:21 UTC on 2026-11-01, on `15ec4ed`. HEAD was there from 06:45:59 to 09:24:54. `15ec4ed` was pushed at 06:46:00 and descends from the registered `76882fe`.
    - **Pass 2** ran 10:31:21–10:40:53 UTC, on `45f673c`. HEAD was there from 09:36:46 to 11:31:16. `45f673c` was first pushed at 11:31:18, 50 minutes after pass 2 ended.
    - **What differs.** `15ec4ed..45f673c` is two commits, which change 4 files by +32/−11 lines with no method change:
      - `17ebece` adds `--resume` to `scripts/anonymize_corpus.py`, a corpus-build script.
      - `45f673c` ([PR #35](https://github.com/ForeverTheIntern/experiments/pull/35)) changes how `candidate_digest` in `rankers/bm25.py` names each candidate's evidence directory: by name instead of by resolved path. It also edits two tests. `candidate_digest` is used only by the search index and the `search_repos` tool, and a `c1` L2 cell has no search tool.
    - **Inconsistent with entry 7.** Pass 2 ran on an unpushed commit. Entry 7 sent three other passes to `runs/withdrawn-unpushed-commit/` for the same condition. Unless the registration distinguished the two cases, keeping pass 2 would be inconsistent with that withdrawal.
    - **Decision.** Made on 2026-11-08 at 23:56 UTC, before any score was read, and recorded here before the reruns run. Both passes are withdrawn unread and rerun whole.
      - Pass 2 is withdrawn on Andrew's decision, for the unpushed commit, consistent with entry 7.
      - Pass 1 is withdrawn by the coordinator under Andrew's standing rule (see the introduction), because its commit is known only from the reflog and its tree state is unknown. Andrew didn't keep pass 1. He launched the reruns of both passes himself at about 00:33 UTC on 2026-11-09, from `.local/run/u50-c1-rerun-2026-11-08.txt` at `CAP=950`.
    - **The reruns.** Both rerun whole from `c4b458f` on the laptop's runner (item 7), under item 4's bound: 0 timeout cases and 0 provider-error cases. `c1` gives the agent no tool, so the tool bound of item 1 doesn't apply. The cap for them is $950 (item 6).
      - The withdrawn copies stay unscored and count toward test spend. Neither is a counted try. This is the coordinator's reading under item 2's recount: a commit and tree state that can't be verified is a setup failure, and the withdrawal was decided blind, not because of either pass's outcome. Item 12 still lists both withdrawn copies, so its table of tries stays complete.
      - A rerun that fails its bound is a counted try. The pass is then rerun whole again, which adds to item 3's selection effect.
    - **The reruns' audit.** Both passed their bound in a blind audit at 01:20 UTC on 2026-11-09, and both are accepted, each on its first counted try. The audit is in the study agent store's `internal/test-run/post-fix-run-audit.md`.
      - Pass 1 ran 00:46:14–00:59:54 UTC and pass 2 01:05:11–01:19:25 UTC on 2026-11-09, on the laptop's runner (`andrews-macbook-pro-1/Darwin-arm64`) with `cursor-agent` 2026.10.22-27dcf5f, tools hash `67989c6537139021`.
      - Each has 59 predictions and 59 traces, 0 of 59 timeout cases, 0 of 59 provider-error cases, 0 pre-turn retries and 0 fallbacks. No trace has an MCP tool call.
      - Both ran from `c4b458f`, checked in `run.env`, and launched from a clean tree: `go.sh` refuses to launch unless `git status --porcelain` is empty.
      - They cost $11.85 together, which brought test spend to $921.70, under the $950 cap.
    - **Scoring dry run.** A dry run of `test_report.py` at commit `c3ba3e6`, before scoring was frozen, found 32 of the 34 registered passes scoreable, with 0 problems. The 2 it left pending are exactly these reruns, and it reads `c4b458f` in both passes' `run.env`. Its output is the study agent store's `internal/scoring-freeze/dry-run.json` (sha256 `68da74f4…5110`). The first dry run at the frozen scoring commit `683880b` (item 19), the store's `internal/scoring-freeze/dry-run-683880b.json` (sha256 `30849a7187de70848ba19cd78c8e1ac8b07292732fdb5a0429841e9f570de647`), found 2 input problems: the static files and `merge_dates`, then missing (item 20). The final dry run supersedes it. It's the store's `internal/scoring-freeze/dry-run-683880b-final.json` (sha256 `5e264db5f82225fc0d8367e0077f4a5fff6b1066f6a524ef3fc5b1f8ff032b35`), run from a clean `683880b` clone from 15:19:17 to 15:19:20 UTC on 2026-11-09. It exited 0, with 0 input problems and 0 test lines with problems. Item 21 repeats it on the set with the 21 fresh-store files.

14. **Entry 6's L5 N = 50 test passes: the plan, recorded before they ran, and how they ran.**
    - **The passes.** Entry 6's four: p1 and p2 of `u5000-real-l5-n50` and `u10000-real-l5-n50`. Each command line is the registered N = 20 line with only `l5-n20` changed to `l5-n50` and `--open-budget 20` changed to `--open-budget 50`. `--registered 76882fe` is kept. They stay exploratory, as entry 6 says, so none enters H1–H3 or §4's secondary analyses.
    - **The list.** `n50-real-2026-11-08.txt`, sha256 `39ec2e29af535a0c8b558450c611a03347a3585d9fdb25cc016d3ec83d6839af`. It runs p1 U5000, p1 U10000, p2 U5000 and p2 U10000, in that order.
    - **When and where.** They were to be launched by hand on the laptop's runner (item 7), with `CAP=935`, only after entry 6's dev timing lists finished on 2026-11-08.
    - **Deadline.** The queue's deadline is 2026-11-09T06:00Z, with `MARGIN=1.25`. The queue skips any pass whose estimated duration × 1.25 doesn't fit before the deadline.
    - **The cap.** The coordinator raised the test cap from $925 to $935 under Andrew's budget delegation. Each pass is estimated at about 0.5 h and $11.70 to $11.90, about $47 for all four, or $62 on high figures. From $862.41, that ends near $909, or $924 on high figures. `queue.sh` starts a pass only while spend + $20 is within the cap; on high figures, that's about $929 before the fourth pass. When the coordinator made this raise, every registered pass was accepted, so it couldn't change which registered runs exist or are scored. The later raise to $950 is for the `u50-real-c1-L2` reruns (items 6 and 13).
    - **Held for them.** The optional dev U10000 hidden-name cell of entry 6's second dev pass (EXP-42's list 80) is held so that these passes can run.
    - **How they ran.** All four ran on the laptop's runner from 2026-11-08 22:12:28 to 2026-11-09 00:20:58 UTC, in the list's order, under `CAP=935` and tools hash `88f1163beb4e464a`. In a blind audit at 00:22 UTC on 2026-11-09, each passed item 4's bound and the tool bound: 59 predictions and 59 traces, 0 timeout cases, 0 provider-error cases, and `open_repo` calls logged in all 59 cases, none dropped. They cost $47.44, which brought test spend to $909.85.

15. **H1–H3 pool each agent cell's two passes, a rule set only in code.** Recorded on 2026-11-09, before any test score was read.
    - **What the registration says.** §4 gives every agent cell 2 passes. Under agent stability, it reports "each pass, the pooled mean, and pass-2 minus pass-1 per cell". It doesn't say how H1–H3, the secondary analyses or the per-cell intervals combine a cell's passes.
    - **What the analysis does.** `scripts/test_report.py` takes one predictions file per pass. Each case's value of every metric is its mean over the cell's files, and every per-cell interval and paired comparison, H1–H3 included, uses those per-case means. With two passes, a case's CR@10 is 0, 0.5 or 1, and cases won and lost compare these means.
    - **When it was set.** The script was first committed in `f85b205`, on 2026-11-01 at 11:31 UTC, after the registration commit `76882fe` (06:45 UTC). The pooling hasn't changed since; `b178c24` added only the `--registered` check. At the frozen scoring commit `683880b` (item 19), `scripts/heldout_score.py` does the pooling, with the same rule. No test score had been read then, and none has been since.
    - **Deviation.** This fills in information the registration left out, after registration and before any score was read. H1–H3 use the pooled per-case means as `test_report.py` computes them. Each pass is still reported under §4's stability analysis.

16. **Six cells' two passes ran from different commits, a deviation from §5.** Recorded on 2026-11-09, before any test score was read. §5 says "Every test cell runs from one pushed commit, named in the results." Entry 7 let "a cell's two passes ... come from different commits and hosts", with the results naming both, but didn't label that as a deviation from §5. This item does.
    - **The six cells.** Each has one pass kept from 2026-11-01 on `f85b205` and one rerun from `c4b458f` (item 12):
      - pass 1 on `f85b205` and pass 2 on `c4b458f`: `u250-hidden-c1-L2`, `u1000-hidden-c1-L4`, `u5000-real-l5-n20` and `u10000-real-l5-n20`;
      - pass 1 on `c4b458f` and pass 2 on `f85b205`: `u250-real-c1-L3` and `u250-real-l5-n10`.
    - `u5000-real-l5-n20` is the U5000 real-name secondary pick, so H3's real-name test uses a mixed-commit cell.
    - **The other cells** each run from one commit: `u1000-real-c1-L3` and `u1000-real-l5-n50` from `f85b205`, and 9 cells from `c4b458f`. `u50-real-c1-L2` is one of the 9, through item 13's reruns; its withdrawn passes had run on `15ec4ed` and `45f673c`.
    - **What differs.** `f85b205..c4b458f` changes 9 files. In the package, only `cli.py` and `split.py` change: the CLI's case selection needs `--registered` for test cases, and one help string changes. The rest are `scripts/test_report.py` (the same `--registered` check), tests and documentation. No method, prompt, budget, K or ranker changes. Every pass ran on the same laptop (item 7).

17. **Exploratory analyses of the test passes, declared before any test score is read.** Recorded on 2026-11-09. They come from the recommendations that fit the current preregistration in the study's independent review (`docs/study-question-review.md` in the study's agent store).
    - **Status.** None is confirmatory. None enters H1–H3's Holm family or §4's secondary analyses, none reports a p-value, and none changes a method, a pick or a registered analysis. They're reported under §4's Exploratory heading and computed with the scored analysis.
    - **Scope and conventions.**
      - Unless an analysis says otherwise, it covers every agent cell of §3 and of entry 6, and every static cell of §3.
      - An agent cell's per-case values are means over its accepted passes, as in item 15.
      - Each cell is computed in its own names. Hidden-name cases keep `scope_visibility`, and hidden-name universes keep each candidate's `role` and `source`. A repository's owner is the part of its name before `/`: the GitHub owner, or the owner ID `o<hex>` that every repository of that owner shares.
      - Every interval uses §4's ecosystem-cluster bootstrap. A comparison is a paired per-case difference, with its interval and the cases won and lost.
    - **Terms.** G is a case's target set, and |G| its size. The case's target owners are the owners of the repositories in G. Its owner set O is every candidate in the case's universe at that size whose owner is a target owner, G included.
    - **The owner shortcut.**
      - *First search.* For each case of each pass of an agent cell, take the first tool call in the case's `events.jsonl` that is a grep, a glob or a `search_repos` call.
        - Its search string is the `query` of a `search_repos` call. For a grep or glob call, it's every string argument other than the path arguments that `cursor_agent._path_args` reads. Item 19 also leaves out `outputMode` and `toolCallId`.
        - The call names a target owner if its search string contains one as a whole token: case-insensitively, with no letter, digit or hyphen directly before or after it.
        - Per cell, report the runs whose first search names a target owner, the runs whose first search doesn't, and the runs with no such call.
      - *Owner-given references,* per size and name condition:
        - (i) owner first, random order: the exact expected CR@10 when O comes first in a uniformly random order. That's C(10, |G|) / C(|O|, |G|), or 1 when |O| ≤ 10.
        - (ii) owner first, then `bm25f` at L4: `bm25f`'s L4 ranking restricted to O, which is the within-owner rescoring below for that cell.
      - *Within-owner rescoring.* Every cell's ranking restricted to O, in its own order, scored against G on §4's metrics and CR@|G|.
    - **Set quality,** from the saved rankings:
      - CR@|G|: 1 when the first |G| ranks are exactly G. Also CR@3 and CR@5.
      - Non-targets above the last target: LastRequiredRank − |G|. A case with a target below rank 100 is censored. Report the median over all cases, with censored cases counted above every other value, and the number censored.
      - What fills the top 10: the mean number of non-targets per case in the first 10 ranks. They're counted by universe layer: WideSWE context (`role` `ecosystem`, `source` `wideswe`), the same-owner layer (`ecosystem`, `same_owner`) and the frame sample (`distractor`, `frame`). They're also counted by whether their owner is a target owner.
    - **The `none` visibility group.**
      - These are the cases whose `scope_visibility` is `none`: `visibility.classify`'s alias matching finds no target named in the real-name request. A hidden-name case carries the same label.
      - For every cell, §4's metrics and every metric of this item are reported for this group beside the all-case value. H1–H3's six comparisons are also reported within the group, as paired differences with intervals and cases won and lost, without p-values.
      - The write-up describes the hidden-name condition as uninformative names in a request that still points at its targets by ID.

18. **Entry 7's concurrency rule withdraws passes that §5 would score, a deviation from §5.** Recorded on 2026-11-09, before any test score was read. Entry 7 sits among the deviations after registration, but didn't say that its rule departs from §5. This item does.
    - **What the registration says.** §5 handles errors case by case. A provider-error case is rerun whole once, and one that still errors "is scored as written and listed". "Timeouts and turn-budget stops stay as written." §5 sets no bound on a pass and no rule for withdrawing or rerunning one, so a pass that runs to its end is scored.
    - **What entry 7 did.** Because its passes had run 4 to 6 cells at once, more than entry 2's 2 to 3, it set a bound on a pass: the pass's timeout rate and provider-error rate must each be within the range of the same cell's dev runs, or at most 1.5 × their pooled rate where that is non-zero. It withdrew the 5 passes that failed the bound and reran them whole. Under §5, those 5 would have been scored, their timeout and provider-error cases as written.
    - **Item 4's extension.** Item 4 applies the same bound to every rerun pass. For every rerun cell but one, that allows no timeout case and no provider-error case.
    - **When it was set.** Entry 7 was committed on 2026-11-04 at 19:55 UTC. The 2026-11-01 passes it judges had ended, and its audit had read their timeout and provider-error counts. So the rule was chosen with those counts known, but before any score was read. Item 4's extension was set on 2026-11-04 at 20:28 UTC, before any rerun started.
    - **Deviation.** The bound changes which run of a pass is scored, so it's a deviation from §5. Within a pass, §5's case rules are unchanged. The bound is why every accepted pass has 0 timeout cases, and item 3 records the selection effect that follows.

19. **Item 17's first-search string leaves out two more arguments of grep calls, a change to item 17.** Recorded on 2026-11-09, before any test score was read.
    - **What item 17 says.** A grep or glob call's search string is every string argument other than the path arguments that `cursor_agent._path_args` reads. A target owner is named if the string contains it as a whole token, with no letter, digit or hyphen directly before or after it, so `_` counts as a boundary.
    - **What was found.** At 01:21 UTC on 2026-11-09, a check of one dev events file, from EXP-35's dev timing pass at U5000, listed the arguments in each call's `started` event. It's recorded in the study agent store's `internal/scoring-freeze/dev-events-tool-keys.md`.
      - A grep's string arguments are `pattern`, `path`, `glob`, `outputMode` and `toolCallId`. `outputMode` is the grep's output format, and `toolCallId` is the CLI's ID for the call. Neither is what the agent searched for.
      - Because `_` is a boundary, an owner spelled like an `outputMode` value, or like a segment of a tool-call ID, could count as named.
    - **What changes.** A grep or glob call's search string also leaves out `outputMode` and `toolCallId`. Every other argument stays. The whole-token match (`names_owner` in the scoring code) is unchanged. A call whose search string is empty after the exclusions still counts as the run's first search, and names no target owner.
    - **When it was set.** After that check, and before any test score was read. The check read a dev file only, and the argument names came only from it. Neither incidental read of test traces in item 10 was used. The 00:19 read's lines weren't used, and the 01:18 read showed only tool-call key names and match counts, with no argument names. The change was committed at 01:35 UTC on 2026-11-09.
    - **Deviation.** This changes one of item 17's definitions after item 17 was recorded, before any score was read. Item 17's analyses stay exploratory, and nothing confirmatory changes. The change is implemented in scoring commit `ee2a60d`, as `NOT_SEARCH_TEXT` in `scripts/heldout_score.py`, with tests. Scoring is frozen at `683880b9aa3873ee613980863108102bbe5830ea`, one commit on `ee2a60d`, which keeps the change.

20. **The static test cells are rerun at `c4b458f`, and the reruns are scored. `merge_dates` is built at `c4b458f`.** Recorded on 2026-11-09, before any audit of the host files ran and before any test score was read. The facts are from the study agent store's `internal/scoring-freeze/missing-inputs.md`.
    - **What was found.** At the frozen scoring commit `683880b`, the laptop's first dry run found all 34 registered passes scoreable (item 13). Its input check found two inputs missing: the 241 static runs, and the `merge_dates` file. The final dry run, with the reruns and `merge_dates` in place, found none missing (item 13).
    - **What the registration says.**
      - §3 runs every static ranker "at every size and both name conditions". §6's deviation 1 makes `hybrid-rrf` at L0 the U50 real-name secondary. The scoring code turns that into 201 static cells and 241 files: 20 rankers × 5 sizes × 2 name conditions, plus `u50-real-hybrid-rrf-L0`, with 5 draws (seeds 0 to 4) in each `bm25f-deps-random` cell.
      - §5 says "Every test cell runs from one pushed commit, named in the results."
      - The only record of the static runs is entry 1's "Static rankers ran on the host's clean corpus and are unaffected." No entry or item names their commit or their files, or says whether the set was complete.
    - **The host files.** The laptop holds 240 static prediction files written on 2026-11-01, covering the 20 × 5 × 2 grid. Neither the files nor their logs record a commit.
      - The committed static ranking code ranks the same at every commit the laptop could have had that day. But the files can't show whether the tree was clean or the commit pushed.
      - At 11:30 UTC on 2026-11-01, the laptop was on the unpushed `45f673c`, with uncommitted edits (entry 7).
    - **The rule.** The coordinator decided it under Andrew's standing rule to favour integrity (see the introduction), before any audit of the host files ran.
      - All 241 static cells are rerun at `c4b458f` on the laptop's runner (`docker/run.sh`, item 7), and those reruns are scored, with item 21's change for the 21 embedding cells. `c4b458f` is pushed and descends from `76882fe`, and entry 7's reruns ran from it.
      - The 240 host files are audited blind and compared by digest with the reruns, for the record only. They're never scored, because no record shows which commit made them.
      - Entry 7 is the precedent: it withdrew three passes started from `45f673c` before it was pushed, because "§5 requires a pushed commit".
      - The rule rests on provenance only, so no audit or comparison result can change it.
    - **How the reruns run.** `run-statics.sh` (sha256 `7217b3a4fd18189bb7cc421c450f1ffe5b19deaa672e0add41e8528248767235`) refuses to start unless HEAD is `c4b458f`, the clone is clean, and `76882fe` is an ancestor. It also refuses unless every test universe it reads has the right size and fetch level, and no corpus it reads holds a `._*` file.
      - Each cell runs `repo-discovery run --split test --registered 76882fe`. The script prints counts only and scores nothing.
      - The reruns read the runner volume's corpus, which since entry 1's fix holds the host corpus's 1,871,832 files.
      - **The runs, on 2026-11-09 (UTC).** The L0 cell ran from 03:13:21 to 03:14:56. The full rerun's container started at 03:16:10 and passed its preflight and `._*` scan at 03:32:40. It finished at 15:19:03 with exit 0 and 0 failed cells, leaving 241 files in all, and every preflight line reported 0 wrong. The files' modification times run from 03:14:55 to 15:19:00.
      - `run.env` records commit `c4b458f`, registered `76882fe`, Linux 7.0.14-linuxkit aarch64 and Python 3.12.3.
      - **The run's `SHA256SUMS`** lists the 241 files, and its own sha256 is `688b3d68508dc195c9357882b6710134be1bca757cd29c5cc51fa8f462df731c`. Item 21 replaces its 21 embedding files with reruns from an empty vector store and gives the scored set.
      - **The reruns' audit** (`audit-static.py`, inputs layout, with the scripts' sha256 values re-checked). All 241 files were found, and all pass every content check:
        - 59 test cases each, with 0 dev, unknown or duplicate cases;
        - the right ranker and size;
        - one universe root per file;
        - 5 distinct draws in each of the 10 `bm25f-deps-random` cells.
      - **The reruns' logs.** None is absent, and 0 lines name a metric. 66 other lines are all in the 20 `dense-cards` and `hybrid-rrf` logs and the L0 cell's log, and all come from loading the embedding model. Each of these 21 logs shows the weights-loading progress bar at 0% and at 100%, and 4 of them redraw it in between. 19 carry a `huggingface_hub` warning that requests went to the Hugging Face Hub without a token. Only the lines' digit-masked shapes were read.
    - **The host files' record.** Added on 2026-11-09 from the laptop's host-side checks. It's a record only and doesn't change the rule. `audit-static.py` (sha256 `2ed4da9a16b463ff15bf0be8af04c35cf5bcd4370ebc1c35aa4a1fa20baee93d`) reads the files in code and prints only counts, digests and times, with no ranking or metric. Times are UTC on 2026-11-01.
      - **Start times.** A file's birth time is its start. The first file started at 07:07:34, 22 minutes after registration, and the last at 21:19:26. None started before registration (06:45:38) or before `scripted.py` was first committed (04:02:06). Only 10 of the 240 have a birth time equal to their modification time, so the files weren't copied, and these are their run times.
      - **HEAD at each start, from the laptop's git records.** 33 files started under `15ec4ed`, the commit after registration, pushed at 06:46:00. 1 started under `17ebece` and 17 under `45f673c`, neither pushed until 11:31:18; 14 of the 17 are real-name U10000 files and 3 real-name U1000. The other 189 started under `f85b205`, after it was pushed. The host's Python was an editable install of that worktree, so it ran the working tree's code, and nothing shows whether the tree was clean.
      - **Audit, at `683880b`.** All 240 files were found. 0 of 240 pass the content checks, because every file holds 120 rows: the 59 test cases and the 61 dev cases. The dev rows alone mean the host files couldn't have been scored as they are, under this rule or the one alternative considered, which required this audit to pass. Every other check passes:
        - no missing, unknown or duplicate case, and no row with extra keys;
        - the right ranker and size in every row;
        - 5 distinct draws in each of the 10 `bm25f-deps-random` cells;
        - one macOS-native universe root per name condition and size.
      - **Logs.** The 240 logs have 0 lines naming a metric. They have 79 unexpected lines, all in the 20 logs of `dense-cards` and `hybrid-rrf`. These are the same kinds as the reruns' 66, plus one macOS-only PyTorch import warning per log, and only their digit-masked shapes were read. The Hub warning shows that the embedding cells contacted the Hugging Face Hub in both sets.
        - Both sets loaded `BAAI/bge-small-en-v1.5` at revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`, which `embeddings.py` at `c4b458f` pins. It checks the weights' sha256 on load, against `3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad`.
        - Each set's model cache holds only that snapshot, and its weights match the pinned sha256.
        - No model file in the reruns' cache was created or changed from 03:13 to 15:19 UTC on 2026-11-09. The only change to that cache was `huggingface_hub` 2.4.0's own `.agent_harnesses.json`, which isn't model data.
        - Dev runs set `HF_HUB_OFFLINE=1` against the same cache, so they could only have loaded that revision.
      - **Shell history.** The laptop's zsh history (433 lines) has 0 lines matching the spec's pattern `runs/static|repo-discovery (run|evaluate)|repo_discovery\.cli`, and 0 lines containing `evaluate`. There's no bash history. No line matches the batch's own `run` commands either, so the history doesn't record how the batch was started.
      - **Reproduction.** 0 of the 240 host files equal their rerun by whole-file digest, as expected, since each host file also carries the 61 dev rows.
        - Case by case, 14,152 of the 14,160 test rankings (240 files × 59 cases) are identical, and 234 of the 240 files match on all 59 cases.
        - All 8 differences are in hidden-name embedding cells: 2 each in `u250-hidden-dense-cards` and `u250-hidden-hybrid-rrf`, and 1 each in `u1000-hidden-dense-cards`, `u5000-hidden-dense-cards`, `u5000-hidden-hybrid-rrf` and `u10000-hidden-hybrid-rrf`. That fits torch's numerics differing between macOS and Linux. Item 21 records that both sets may have read the same stored card vectors.
        - This doesn't change which set is scored.
      - **The registration's opening statement needs no correction.** No host file started before registration, so "When this was written, no test case had been run, scored or inspected" holds. The 2026-11-01 batch ran the test cases through the static rankers from 07:07:34, 22 minutes after registration, and no log line or shell-history line shows its output evaluated.
    - **`u50-real-hybrid-rrf-L0` completes a registered cell, so it isn't a deviation.** §6's deviation 1 registers the cell. The 2026-11-01 batch covered only the 20 × 5 × 2 grid and missed it, so it has no host file.
      - It ran at `c4b458f` like the other 240 cells, but first and on its own (from 03:13:21 to 03:14:56 UTC on 2026-11-09), on the volume's real-name corpus restricted to L0 by `fetch_levels restrict`.
      - §5 is read per cell (item 16), and this item names the cell's commit.
    - **`merge_dates`.** It feeds §4's exploratory change-memory split. §4 gives that split from `scripts/model_cutoffs.py` as "Test has 25 cases before and 34 after", so the script ran before registration. But no `--out` file was kept, and scoring reads that file.
      - It's built at `c4b458f` by `build-merge-dates.sh` (sha256 `de6fc55d26da16733be5ead3a5104d01c892d50e17f5ddea084500683d889535`) from the 2026-11-01 date cache, with the network on.
      - It reads case metadata, WideSWE's `repos.yaml` and the cache, and no prediction, trace or score. `model_cutoffs.py` and the modules it uses are unchanged from `5070bc0`, where it was first committed, to `c4b458f`.
      - The script copies the cache aside and compares checksums before and after. An unchanged checksum means every date came from the 2026-11-01 cache.
      - `/data/cache` wasn't writable in the runner, so the script ran by its own `CACHE_SRC` route: `REPO_DISCOVERY_CACHE=/data/cache-merge-dates`, with `wideswe` linked to `/data/cache/wideswe`. Neither the script nor the original cache changed.
      - Built at 02:55:42 UTC on 2026-11-09. The cache's sha256, `fb2f43b303f8f13bbdc9a32b838d8cd297053161c96b49955ac9f4020842c80d`, was the same before and after, so every date came from the 2026-11-01 cache. All 120 cases are dated. 25 of the 59 test cases fall before 2026-03-01 and 34 after, as §4 registers.
    - **Deviation.** The scored static runs aren't the ones entry 1 records, so this departs from entry 1, to meet §5. It was decided before any static output was audited, compared or scored. The scoring code is unchanged at `683880b`, and the reruns and `merge_dates` are inputs it reads.

21. **The 21 embedding cells are rerun with an empty vector store, and those reruns are scored, a change to item 20.** Recorded on 2026-11-09, before any step below ran, before any vector or ranking was compared and before any test score was read. It's pushed before any step runs. The code check is in the study agent store's `internal/scoring-freeze/card-vector-store-key-check.md`.
    - **What was found.** At `c4b458f`, the embedding rankers read card vectors from a cache whose keys can't show what made them.
      - `rankers/dense.py` keeps card vectors in one SQLite store per encoder revision, at `embeddings/BAAI__bge-small-en-v1.5--5c38ec7c405e.sqlite` under the cache root (`REPO_DISCOVERY_CACHE`) on the runner volume. Real and hidden names, every size, and the dev and test splits share it.
      - A vector's key is its card variant (with the fetch level), budget, repository and snapshot commit. It holds no card text and no code version. A stored vector is used as it is and never re-checked: only keys the store lacks are encoded.
      - The agents' search tool reads the same store. Its hybrid backend (`rankers/search_repos.py`) builds `HybridRanker()` and loads every candidate's vector from the store, so the scored `u5000-real-c2-hybrid-L4` passes read cached vectors too.
      - The card code is identical at `c4b458f` and at the four commits the host files started under (`15ec4ed`, `17ebece`, `45f673c` and `f85b205`), and unchanged since 2026-10-29 01:46 UTC. But nothing records where, when or from which tree each stored vector was computed. Item 20's reruns and the host files may have read the same stored vectors, which may be why the real-name embedding cells match exactly.
    - **The rule.** The coordinator fixed it under Andrew's standing rule (see the introduction), before any comparison ran. It holds whatever the comparisons show.
      1. **The current store is kept.** Before anything runs, its sha256 and size are recorded, and it's kept unchanged: sha256 `[current store sha256]`, `[size]` bytes.
      2. **The embedding cells are rerun with an empty store.** The 21 embedding cells (the 20 `dense-cards` and `hybrid-rrf` cells, and `u50-real-hybrid-rrf-L0`) are rerun at `c4b458f` with an empty vector store. They use a new cache root for the vectors, the same pinned model (item 20) and `HF_HUB_OFFLINE=1`, and every other input is the one item 20's reruns read. The keys that the hybrid backend reads for the scored `u5000-real-c2-hybrid-L4` passes are encoded into the same fresh store, by the backend's own code at `c4b458f`, with no agent run.
      3. **The fresh files are scored.** The 21 fresh-store files are scored in place of item 20's 21, and the other 220 files of item 20's reruns stay. The scored set is the 241 files listed in a new `SHA256SUMS`, whose own sha256 is `[new SHA256SUMS sha256]`. The final dry run (item 13) is repeated on that set: `[dry-run file]`, sha256 `[dry-run sha256]`.
      4. **The comparisons are for the record only.** Old and fresh vectors are compared key by key. Of the fresh store's `[n]` keys, `[n]` are absent from the current store, `[n]` are byte-identical, `[n]` aren't identical but are at cosine ≥ 0.99999, `[n]` are at cosine ≥ 0.9999 and below 0.99999, and `[n]` are below 0.9999. The fresh 21 cells' per-case test rankings are compared with item 20's 21: `[n]` of the 1,239 (21 × 59) are identical, and `[n]` of the 21 files match on all 59 cases. Both comparisons run in code and print counts only, with no metric.
      5. **The agent passes are scored as run.** The comparison for the keys the hybrid backend reads is reported with them: `[counts, in point 4's categories]`. Any of those keys below cosine 0.9999 is listed as a deviation for both passes: `[none / the keys]`. The rankers write a key only when the store lacks it, so the current store holds the vectors the passes read, unless a concurrent run wrote the same key or something outside the rankers rewrote it.
    - **The runs.** `[times (UTC), run.env, exit codes, the fresh store's sha256 and key count, and item 20's audit of the 21 fresh files]`
    - **Deviation.** This changes item 20's scored set after item 20 was recorded, so that what the embedding cells read is made within the scored run. It was decided before any comparison ran and before any score was read. The scoring code is unchanged at `683880b`. The agent passes' scoring doesn't change; their record adds the key comparison and any deviation from point 5.
