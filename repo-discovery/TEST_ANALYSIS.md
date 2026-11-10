# Held-out test analysis

The scoring and analysis code for the held-out test run, frozen before any test score is read. It implements §4 of [PREREGISTRATION.md](PREREGISTRATION.md) with entries 6 and 7 and the addendum to entry 7 (items 1–19 and 22). The addendum's items 15–19 were recorded on 2026-11-09, on branch `cursor/prereg-7-7-addendum-02fb`, at `c8c2edc` when scoring was frozen. Item 22 was recorded on 2026-11-10, after scoring stopped at `683880b`, and scoring is frozen again at the commit that implements it ([Freeze record](#freeze-record)). Where those leave a choice open, the code makes one, and [Open choices](#open-choices) lists each with its decision or a recommendation.

| File | What it holds |
|---|---|
| `scripts/test_report.py` | The entry point: scoring and `--dry-run` |
| `scripts/heldout_plan.py` | The frozen plan: cells, comparisons, the 38 passes of item 12 and 14, bounds, `CHOICES`. It reads no file |
| `scripts/heldout_runs.py` | Pass locations, `run.env` checks, trace audits (item 4 and item 1's bounds), run-list parsing, the dry run. It opens no prediction |
| `scripts/heldout_score.py` | Inputs, cases, universes, per-ranking values, first search, pass planning, per-cell scoring and pooling, the bootstrap, comparisons, the frontier, the inputs check for the dry run |
| `scripts/heldout_report.py` | Tables, figures, CSVs, `results.json` |
| `tests/test_heldout_analysis.py` | A synthetic study: 59 invented cases in 30 ecosystems, every pass and static run |

It reuses existing code rather than copying it:
- the metrics: `metrics.case_metrics`;
- the bootstrap, Holm and percentile intervals: `stats`;
- case selection behind the registration: `split.run_cases`;
- prediction reading: `predictions.read_predictions`;
- universe resolution: `contract`;
- agent cost: `v5_dev_report.case_cost` and `v5_memory_report._rate`, through `heldout_score.pass_rate`. A pass with no finished first run has no rate of its own, so its stopped runs are priced at item 22's `heldout_plan.FALLBACK_RATE`, $0.257/Mtok;
- open-N fetch cost: `v5_export_cases.fetch`;
- the cost frontier: `selection`.

The bootstrap draws are the same as the old `test_report.py`'s (seed 0, 2000 resamples over the sorted ecosystems), and a test checks that a cell's estimate and Holm's adjustment match it exactly.

## Running it

From `repo-discovery/`, with the package installed (`pip install -e ".[dev]"`) or `PYTHONPATH=src`:

```bash
# Tests: synthetic fixtures only
pytest tests/test_heldout_analysis.py tests/test_registered_entry_points.py

# Dry run: reads the run lists, run.env stamps and file names; opens no prediction or trace
python scripts/test_report.py --dry-run .local/run/LIST1.txt --dry-run .local/run/LIST2.txt ... \
    INPUTS.json [--out dry-run.json]

# Scoring
python scripts/test_report.py INPUTS.json --registered 76882fe --out results/test/
```

The dry run takes every registered run list. Item 12 names the lists, and items 13 and 14 add `u50-c1-rerun-2026-11-08.txt` and `n50-real-2026-11-08.txt`. It needs no `--registered`. `--runs-root ROOT` can replace `INPUTS.json`. For each pass line, it reports:
- whether the pass would be scored, is pending, is exploratory, is withdrawn, or isn't registered;
- whether the line's flags match its cell (split, registration, evidence, open budget, search, anonymization, universe size and level, trace directory);
- whether `pred.jsonl` exists, and how many traces;
- the `run.env` host and completion stamp, and whether its commit matches item 12's.

Each line's files are looked for where scoring will read them: under `runs_root`, with traces at `INPUTS.json`'s `trace_dir` (or, without `INPUTS.json`, at the line's `--trace-dir`). A test line has a problem, and isn't counted as scored, if:
- its `--out` isn't under `runs_root`;
- its `--trace-dir` doesn't give `INPUTS.json`'s `trace_dir`;
- its pass directory or `pred.jsonl` is absent, or it has fewer than 59 traces;
- its `run.env` names a commit other than item 12's.

It gives the `trace_dir` template the lines' `--trace-dir`s share. With `INPUTS.json`, it also checks that every file scoring would read exists, without opening any: the case files, `case_map`, `merge_dates`, `costs`, every static run and draw, and each universe root. It lists what's missing under "INPUTS.json: N problems", along with `accept` entries that aren't pending. It then lists registered passes that appear in no list. Lines under `withdrawn-*` are reported as withdrawn and never scored, and their directories aren't opened. `run.env` is read line by line; only `started`, `finished`, `complete`, `host`, `cursor_agent`, `tools` and keys naming a commit are kept, so tokens in it are never stored or printed.

Scoring checks `--registered` first, then refuses to run if the analysis code differs from its commit, unless you pass `--allow-dirty`, or if `INPUTS.json` gives no `costs` or `merge_dates`. The report's header names the commit and says whether the tree was clean. `--allow-pending` scores without pending passes, and isn't for the reported run (choice 3).

## Inputs

`INPUTS.json`. Relative paths are relative to this file; `~` and `$VARS` expand.

| Field | Required | What it is |
|---|---|---|
| `runs_root` | yes | The directory holding `test/p<N>/<cell>/`. Never a `withdrawn-*` directory |
| `cases` | yes | `{"real": cases.jsonl, "hidden": cases.jsonl}`, the real-name and hidden-name case files. Only test cases are read, through `split.run_cases` with the registration |
| `case_map` | with `hidden` | The anonymization's `private/mapping.json`; only its `cases` map (real ID to hidden ID) is read |
| `static` | yes | The static runs, with `{cell}` for the cell name, such as `static/{cell}.jsonl` |
| `static_draws` | yes | `{"template": "static/{cell}-{draw}.jsonl", "draws": [0, 1, 2, 3, 4]}`, the five draws of `bm25f-deps-random` |
| `universes` | for item 17 | `{"real": ".../u{size}/L4", "hidden": ...}`: per name condition, the universe root for each size. It holds one `universe.jsonl` or one per case |
| `trace_dir` | no | Where each pass's traces are, with `{pass}` for the pass directory. The default is `{pass}/traces` (choice 5) |
| `accept` | for item 13 | `{"p1/u50-real-c1-L2": "item 13 audit, c4b458f", ...}`: pending passes accepted after their audit (choice 3). Only pending passes may be listed |
| `merge_dates` | for scoring | `model_cutoffs.py --out` output, one `{"case_id", "last_merge"}` per real-name case, for change memory |
| `reviewed` | no | `{"real": cases.jsonl}`, `adjudicate.py apply` output, for the reviewed-label analysis. No adjudication of the test cases is recorded, so leave it out (item 7) |
| `costs` | for scoring | The dev selection's registry YAML (`selection_table.py --registry`); only its `fetch` and `index` tables are used, for the frontier |
| `run_env_commit_key` | no | A `run.env` key that names the commit, if no key contains "commit" |

```json
{
  "runs_root": "/data/runs",
  "cases": {"real": "cases/wideswe-release120.jsonl", "hidden": "anon/u10000/cases.jsonl"},
  "case_map": "anon/u10000/private/mapping.json",
  "static": "static/{cell}.jsonl",
  "static_draws": {"template": "static/{cell}-{draw}.jsonl", "draws": [0, 1, 2, 3, 4]},
  "universes": {"real": "/data/universes/u{size}/L4", "hidden": "/data/anon/u{size}/L4"},
  "trace_dir": "{pass}/traces",
  "accept": {
    "p1/u50-real-c1-L2": "item 13 audit, c4b458f",
    "p2/u50-real-c1-L2": "item 13 audit, c4b458f"
  },
  "merge_dates": "merge-dates.jsonl",
  "costs": "selection/cells.yaml"
}
```

`runs_root`, `trace_dir` and `accept` are the values for the reported run. The other paths are examples: the files are on the machine that holds the runs, and the dry run with `INPUTS.json` checks that each one exists.

## What it scores

- **Cells: 220.**
  - 201 static: 20 rankers × 5 sizes × 2 name conditions, plus `u50-real-hybrid-rrf-L0`.
  - 19 agent: §3's 10 primary picks, 7 agent secondary picks, and entry 6's 2 exploratory N = 50 cells.
- **Passes: 38.**
  - 32 are accepted in item 12. 10 of these are kept from 2026-11-01 on `f85b205`, with no `run.env` by design.
  - 2 are pending: `u50-real-c1-L2`'s reruns (item 13).
  - 4 are exploratory: item 14's N = 50 passes.
  - Only `runs/test/` is read. Withdrawn copies are never read or scored (item 2).
- **Per-case values.** An agent cell's per-case value is the mean over its passes (item 15), so a case's CR@10 is 0, 0.5 or 1. `bm25f-deps-random`'s is the mean over its 5 draws.
- **Metrics.** §4's metrics at K = 3, 5, 10, 20, 50, 100, with LastRequiredRank censored at 101.
- **Intervals.** §4's 95% percentile bootstrap over the 30 test ecosystems: 2000 resamples, seed 0, the same draws for every cell and comparison.
- **Confirmatory.** H1–H3 at U5000, real and hidden names: 6 paired one-sided tests on CR@10, p = the share of resamples with a difference ≤ 0, and Holm at α = 0.05.
- **Secondary.** All with intervals and cases won and lost, and no p-values:
  - H1–H3 at U1000 and U10000;
  - H1–H3 on CR@20 at U1000, U5000 and U10000;
  - mechanisms M1–M4 at U5000, both name conditions;
  - Hit@10 against CR@10 for every cell;
  - agent stability (each pass, pooled, pass 2 − pass 1, with each pass's commit and host);
  - cost and the cost frontier (the dev selection's rules, 10% tolerance).
- **Exploratory, labelled as such.**
  - Change memory, using 2026-03-01 (§4).
  - Reviewed labels.
  - Misses.
  - Entry 6's N = 50 cells, with their two comparisons.
  - Item 17:
    - the owner shortcut: first search, the owner-given references (i) and (ii), and within-owner rescoring;
    - set quality: CR@|G|, CR@3, CR@5, non-targets above the last target with censoring, and top-10 fill by layer and by owner;
    - the `none` visibility group: every metric beside the all-case value, and H1–H3 within the group without p-values.

## What stops scoring

Every check below runs before any prediction is read, except the last three, which stop while predictions are being read or compared. Nothing is written when scoring stops.

- `--registered` is missing, isn't a commit, or isn't an ancestor of HEAD.
- The analysis code has uncommitted changes (unless `--allow-dirty`).
- `INPUTS.json` gives no `costs` or no `merge_dates`.
- The case files don't give 59 test cases in 30 ecosystems, or the hidden-name cases don't map one to one onto them.
- A registered pass is pending and not accepted (unless `--allow-pending`), or `accept` names a pass that isn't pending.
- `runs_root`, or a pass directory, resolves into a `withdrawn-*` directory.
- A pass, registered or exploratory, fails its bounds:
  - a missing trace;
  - any timeout case;
  - more provider-error cases than item 4 allows (0, or 29 for `u1000-hidden-c1-L4`);
  - for `c2` and `l5`: any case where the CLI logged tool calls that the server never received, or more than 2 cases with no tool call;
  - a `run.env` naming a commit other than item 12's, or a rerun pass without a `run.env`.

  A kept pass's provider-error cases are reported, not bounded.
- A prediction file is missing, holds a case that isn't a test case, has the wrong universe size, or has a line whose `ranker` isn't its cell's (`cursor-agent` for an agent cell, the method's name for a static one).
- A pass or static run has no prediction for some test case.
- Fewer than the 6 confirmatory tests ran; §4 fixes Holm's family at 6.

## Outputs

Everything goes in `--out DIR`:
- `report.md`: every table, under §4's headings;
- `tables/*.md`, one per section;
- `figures/forest.svg` (confirmatory differences, with per-ecosystem dots) and `figures/hit-vs-cr.svg`;
- `cells.csv`: every metric of every cell for the `all` and `none` groups, with censoring and first-search counts;
- `per_case.csv` (pooled values and costs) and `per_pass.csv`;
- `first_search.csv` (with each case's visibility), `misses.csv` and `audits.csv`;
- `comparisons.csv`: every comparison, for the `all` and `none` groups;
- `frontier/`;
- `results.json`: all of the above with the registration, the code commit, `CHOICES`, notes and skipped comparisons.

Standard output gets the confirmatory table.

## Open choices

Each item says what the code does. Items 1 to 7 were put to the study's coordinator before freezing, and each one's decision (2026-11-09) is given; items 8 to 28 give a recommendation.

### Settled before freezing

1. **Pooling the two passes for H1–H3 (item 15).** The code uses each case's mean over both passes, for H1–H3 and every other per-cell result. This rule came in with `f85b205`, after the registration commit `76882fe`, and item 15 records it as a deviation. Each pass is still reported under agent stability. *Decided:* keep it as the primary analysis.
2. **S1, scoring entry 7's five concurrency withdrawals as written (item 18).** *Removed* before freezing. Item 2 says every withdrawn copy is never scored, and item 3 records Andrew's decision that the write-up makes no adjustment or sensitivity analysis for the rerun selection effect. Its code, flag, tests and report section are gone, and no withdrawn directory is opened.
3. **The pending `u50-real-c1-L2` reruns (item 13).** Scoring stops until both are in `accept`. They must still pass item 4's bound. *Decided:* item 13's audit accepted both reruns, and item 12 counts all 34 passes as accepted (addendum at `c8c2edc`), so `accept` is `{"p1/u50-real-c1-L2": "item 13 audit, c4b458f", "p2/u50-real-c1-L2": "item 13 audit, c4b458f"}`. Never use `--allow-pending` for the reported run: it would leave the U50 real-name primary pick unscored.
4. **The first search's tool names (item 17).** The code counts:
   - `grepToolCall`, `ripgrepToolCall` and `globToolCall` events;
   - `mcpToolCall` events whose `toolName` is `search_repos`, or whose `name` ends in it.

   The agents have no shell, so shell `rg` isn't a case. If the CLI used other names, every run would count as "no such call". *Decided:* check the parser against the key names a worker with dev traces records, and nothing else. *Checked* (2026-11-09) against one dev `events.jsonl` from EXP-35's U5000 `search_repos` timing pass: it has `grepToolCall`, `globToolCall`, `readToolCall` and `mcpToolCall` with `toolName` `search_repos`, at the paths the code reads. `ripgrepToolCall` doesn't occur, which does no harm. Nothing needed changing, and `test_first_search_reads_the_dev_event_layout` builds its events in that file's layout.

   **The search string (a deviation from item 17).** Item 17 defines a grep or glob call's search string as every string argument other than the path arguments. In the dev events file, a grep call's string arguments include `outputMode`, the output format, and `toolCallId`, the CLI's ID for the call, and a whole-token match allows `_` beside the owner. So an owner spelled like one of their values, or a part of one, would count as named. *Decided* (2026-11-09, after review):
   - `outputMode` and `toolCallId` are dropped as well (`NOT_SEARCH_TEXT`). Grep keeps `pattern` and `glob`, glob keeps `globPattern`, and any other non-path string argument still counts; there's no allowlist. The addendum records this as item 19.
   - `names_owner` stays as registered, with `_` a token boundary.
   - A grep or glob call left with no search text gives the empty string. It's still the first search, and counts as not naming an owner.
5. **Where the traces are.** The dry run turns each line's `--trace-dir` into a `trace_dir` template, reports the one the lines share, and, given INPUTS.json, flags a line whose traces aren't at its `trace_dir`. A wrong `trace_dir` stops scoring anyway, with every case missing its trace. *Decided:* set `trace_dir` from a dry run on the real run lists. That dry run, at `ee2a60d`, found all 73 lines of the registered run lists putting traces at `{pass}/traces`, so that is now the default.
6. **What `run.env` names.**
   - The code checks every `run.env` key containing "commit" (or `run_env_commit_key`) against item 12's commit, and stops on a mismatch or on a rerun pass without a `run.env`.
   - If a `run.env` names no commit, the pass is labelled "run.env names no commit" and scored. The passes table lists every such pass in a note. Items 12 and 16 are then the record of its commit.

   *Decided:* accept stamps that can't be checked, and note them.
7. **Optional inputs.** Without `costs` there's no frontier, and the cost table shows only $, tokens, latency and fetches. Without `merge_dates` there's no change memory. Without `reviewed`, the reviewed-label analysis isn't computed. §2 reports reviewed labels only if two-reviewer adjudication of the test cases finishes; RECORD.md records none, and the paper draft lists it as open. *Decided:* supply `costs` (the dev selection's `cells.yaml`) and `merge_dates` (`model_cutoffs.py --out` for the test cases), which scoring now requires. Leave out `reviewed`; the report then says why that table is skipped.

### Answered in the code

8. **Mixed-commit cells (item 16).** Both passes are pooled, and the stability table names each pass's commit and host. *Recommend:* keep.
9. **Bootstrap details.**
   - numpy's default (linear) quantile;
   - one set of draws over the sorted real-name ecosystems, shared by every cell and comparison, and identical to the old `test_report.py`;
   - hidden-name cells resampled through their real-name IDs.

   *Recommend:* keep.
10. **p-values.** §4's rule, with no +1 correction. A p of 0 shows as "< 0.0005". *Recommend:* keep. The alternative, (k + 1)/(B + 1), floors p at 0.0005 and changes no Holm decision at α = 0.05 unless the p-values sit at the boundary.
11. **Multiplicity.** Holm runs over the 6 confirmatory tests only, and scoring stops if any of them didn't run. Secondary and exploratory comparisons report intervals and cases won and lost, with no p-values. *Recommend:* keep, since §4 makes no confirmatory claim outside H1–H3.
12. **Where secondary comparisons run.** §4's "the same comparisons at U1000 and U10000, and on CR@20" is run as CR@10 at U1000 and U10000, plus CR@20 at U1000, U5000 and U10000. The mechanisms run at U5000 under both name conditions. *Recommend:* keep. It's the wider reading, and none of these is confirmatory.
13. **Subgroup intervals.** The `none` group and the change-memory groups resample their own ecosystems, with the same seed and count. The after − before gap uses the all-case draws, so both groups move together. *Recommend:* keep.
14. **Won, lost and tied.** These count pooled per-case values, so 0.5 against 0 is a win. Ties are counted separately. *Recommend:* keep.
15. **Censoring after pooling.** A case's pooled non-targets above the last target is censored if either pass is censored. Medians put censored cases above every other value, and the number censored is reported. *Recommend:* keep; it's conservative.
16. **The whole-token rule (item 17).** A target owner counts as named when it isn't directly preceded or followed by a letter, digit or hyphen, matched case-insensitively. An underscore isn't in item 17's list, so `acme_billing` names `acme`. Unicode letters count as letters. *Recommend:* keep, as item 17 is written.
17. **Ranks as saved.** Set quality and within-owner rescoring use positions in the saved ranking, as `case_metrics` does. The harness rejects repeated repositories, so a duplicate can't occur. *Recommend:* keep.
18. **Top-10 layers.** Candidates whose (`role`, `source`) isn't one of item 17's three layers count as `other-layer`. The by-owner split covers every non-target. *Recommend:* keep.
19. **Turn-budget stops.** They're scored as written (§5), and the misses table counts them. Item 4's bound covers timeouts and provider errors, not turn budgets. *Recommend:* keep.
20. **Missing predictions.** A registered pass with a missing case stops scoring; there's no imputation. *Recommend:* keep. Item 4's bound already requires every case to have run.
21. **Kept passes' provider errors.** The 10 kept passes met entry 7's rule. Item 4's 0 bound applies to reruns only, so their provider-error cases are noted, not enforced. *Recommend:* keep.
22. **Exploratory passes that fail their bounds** stop scoring, as registered ones do. No item says what happens to an N = 50 pass outside item 4's bound. Item 14 records that all four passed it in a blind audit, so this fires only if the scoring audit disagrees with that record, and then the disagreement needs a decision rather than a note. *Recommend:* keep.
23. **Change memory's counts.** If `merge_dates` doesn't split the test cases 25 before and 34 after (§4), the report notes the counts it found and goes on. *Recommend:* keep. It's exploratory, but check the note.
24. **The Hit-vs-CR figure** plots five static methods per name condition, for legibility: `bm25f`, `hybrid-rrf`, `dense-cards`, `name-match` and `scripted-search`. The table covers every cell. *Recommend:* keep.
25. **No dev comparison.** The report doesn't set test results beside dev results; §4 doesn't ask for it. The only exception is one line of dev context under the confirmatory table (§7, entry 3). *Recommend:* keep.
26. **No exact binomial intervals.** Only §4's bootstrap is computed. *Recommend:* keep.
27. **Rounding.** JSON and CSV use 4 decimals and markdown uses 3. Censored values (a case's non-targets above the last target, or a censored median) are written as `censored`. *Recommend:* keep.
28. **The dirty-tree refusal.** Scoring refuses uncommitted analysis code unless `--allow-dirty` is passed. *Recommend:* run the reported analysis from the frozen commit with a clean tree.

## Freeze record

The scoring code is frozen at the commit that adds this section, on `cursor/test-scoring-freeze-0263`. Before freezing, an independent review of `ee2a60d` (the study agent store's `internal/scoring-freeze/code-review.md`) found that no registered number had moved since `c3ba3e6`. It listed one medium, five low and three info findings. Each one, and what was done:

| Finding | What was done |
|---|---|
| M2: S1 scores withdrawn copies, which items 2 and 3 rule out | Removed (choice 2) |
| L1: the dry run didn't check the root it reported on, and an absent directory counted as scored | Fixed. A line's files are judged under `runs_root` and `trace_dir`. A line whose `--out` isn't under `runs_root`, or with no pass directory, no `pred.jsonl` or fewer than 59 traces, has a problem and isn't counted. The dry run also checks that every input file exists |
| L2: a missing events file counts as no search call | Left as is; see below |
| L3: the `ranker` field wasn't checked | Fixed: a line from another ranker stops scoring |
| L4: an exploratory pass failing its bounds was dropped with a note | Fixed: it stops scoring (choice 22) |
| L5: Holm ran on fewer than 6 tests with a note | Fixed: scoring stops (choice 11) |
| I1: kept passes' provider errors are noted, not bounded | Left as is: item 4's bound covers rerun passes only (choice 21) |
| I2: `--allow-pending` still exists | Left as is: it's for checks on partial runs. Choice 3 rules it out for the reported run, and the passes table notes each pass it leaves out |
| I3: `dev-events-tool-keys.md` cites one fact from the test side, `editToolCall` | That file isn't part of this code. No code or test mentions `editToolCall`, and the first-search parser doesn't read it |
| Choice 4's example values weren't in the dev doc | Dropped |

Left as is, with the reason:
- **A missing events file counts as no search call (L2).** At every commit the passes ran from (`15ec4ed`, `45f673c`, `f85b205` and `c4b458f`), `cursor_agent._trace` writes a case's `.events.jsonl` just before its trace, so a trace without one would be a lost file. But this was to change only if dev data showed that a missing file is never legitimate, and no dev run is on the machine the code was frozen on. A missing trace still stops scoring, so a wrong `trace_dir` is caught.
- **The other input paths.** The code fixes `trace_dir`'s default and documents `accept`. The case, `case_map`, static, universe, `merge_dates` and `costs` paths are on the machine that holds the runs. The dry run with `INPUTS.json` checks that each exists, and scoring stops if one doesn't.
- **A pass listed on several lines** is judged on its directory's current contents each time, since that's what scoring reads.

Run on the frozen commit:
- **The full test suite:** 467 passed, and 1 skipped because it needs the network.
- **The synthetic study, scored by `ee2a60d` and by the frozen commit.** The study is the tests' 59 cases in 30 ecosystems with the fixed rankings cleared, so H1–H3 aren't degenerate. Both runs used the CLI from a clean worktree, with `--registered 76882fe`.
  - 45 of the 47 files both write are byte-identical, among them every CSV, every table but `s1.md`, and both figures.
  - `report.md` differs only in the commit in its header and in the S1 section, now gone. `tables/s1.md` is no longer written.
  - `results.json` differs only in the code commit, the output path of `frontier/`, and `CHOICES`, where `s1` is gone and `exploratory-bounds` is new.

### Item 22: the fallback rate

Scoring at `683880b` stopped in `_rate`, because 5 agent passes have no finished first run (addendum item 22). The commit that implements item 22 changes the scoring code only there.
- `heldout_score.pass_rate` returns `_rate`'s value for a pass, or None where `_rate` would stop or divide by zero. `score_cell` then uses `heldout_plan.FALLBACK_RATE` and records the pass in `CellResult.rate_fallback`.
- Each such pass is listed in its cell's notes, which appear in the cells table and `results.json`, and in the frontier's notes. It's also named in a footnote to the cost table.
- Nothing else changes. With no fallback pass, no output mentions it.

Run on that commit:
- **The full test suite:** 477 passed, and 1 skipped because it needs the network.
- **The new tests** score a synthetic study with stopped runs through `score_cell`, `score_all`, `build()` and `write()`. In it, 5 passes have no finished first run, one has exactly 1, and some follow-ups end at the time limit or the turn budget with no usage. They also price a pass whose first runs all hit the time limit, which `build()` stops at its audit. On `683880b`, the end-to-end test stops with the same `_rate` message that scoring printed.
- **The tests' synthetic study, scored by `683880b`, by `7e9a22c` and by this commit,** with `build()` and `write()`, the same output path and the commit in the header held fixed. All 47 files each writes are byte-identical.
- **The study with stopped runs.** For the 33 passes that keep their own rate, `683880b` and this commit give the same per-case costs, notes and values. They were scored alone and within the 15 agent cells that have no fallback pass.
