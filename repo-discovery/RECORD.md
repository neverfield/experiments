# repo-discovery: record

Where each part of the study lives. Findings are in the reports in the Experiments Project's
agent store (`bc-c364fa0b-55a8-56e7-96c4-2b320bedf063`), not here; a path written as store
`docs/x.md` is under that store. Cloud agent sessions open at
`https://cursor.com/agents/<agent>`.

| Work | PRs | Agent | Store report |
|---|---|---|---|
| Plan | | coordinator | `docs/repo-discovery-study.plan.md` |
| Foundation: cases, split, harness, metrics | [#1](https://github.com/neverfield/experiments/pull/1) | `bc-88741561-cdfd-5361-ad43-6a388f6c4eb5` | |
| V0 keyword search | [#2](https://github.com/neverfield/experiments/pull/2) | `bc-c837a07d-53cd-599b-8c01-4eee99888661` | `docs/v0-keyword-pilot.md` |
| Universes and evidence packets | [#4](https://github.com/neverfield/experiments/pull/4) | `bc-a285e2cc-7899-57ee-b183-abdc54d0dff0` | `internal/corpus/README.md` |
| V2 dependency graph | [#5](https://github.com/neverfield/experiments/pull/5) | `bc-05d9b40e-86e5-5648-85df-8eefb9c743b4` | `docs/v2-dependency-graph.md` |
| V3 contract joins | [#8](https://github.com/neverfield/experiments/pull/8) | `bc-193e52f9-acc9-5bd7-bd3e-51178f22de90` | `docs/v3-contract-joins.md` |
| V4 dense retrieval | [#6](https://github.com/neverfield/experiments/pull/6) | `bc-df214894-151a-5b58-ac27-2bc6e40b3fcd` | `docs/v4-embeddings.md` |
| V1 LLM cards | [#13](https://github.com/neverfield/experiments/pull/13) | `bc-ada502cf-8e22-56d8-b0c0-ef71a7ae3be1` | `docs/v1-llm-cards.md` |
| Fetch levels L0–L5, U10000 | [#9](https://github.com/neverfield/experiments/pull/9), [#11](https://github.com/neverfield/experiments/pull/11), [#15](https://github.com/neverfield/experiments/pull/15) | `bc-df214894-151a-5b58-ac27-2bc6e40b3fcd` | `docs/fetch-level-index-shape.md` |
| V5 agent: trial, dev run, memory checks | [#3](https://github.com/neverfield/experiments/pull/3), [#7](https://github.com/neverfield/experiments/pull/7), [#10](https://github.com/neverfield/experiments/pull/10) | `bc-a7a08739-8734-54ad-b106-43f66a5341e1` | `docs/v5-cursor-agent.md`, `docs/v5-memory-checks.md` |
| V5 agent: L5 on demand, c1, c2 | [#16](https://github.com/neverfield/experiments/pull/16), [#17](https://github.com/neverfield/experiments/pull/17), [#18](https://github.com/neverfield/experiments/pull/18) | `bc-a7a08739-8734-54ad-b106-43f66a5341e1` | `docs/v5-on-demand.md`, `docs/v5-index-use.md` |
| V5 at scale (EXP-27) | [#14](https://github.com/neverfield/experiments/pull/14), [#22](https://github.com/neverfield/experiments/pull/22), [#24](https://github.com/neverfield/experiments/pull/24) | `bc-a7a08739-8734-54ad-b106-43f66a5341e1` | `docs/v5-scale.md` |
| Selection step (EXP-28) | [#19](https://github.com/neverfield/experiments/pull/19), [#20](https://github.com/neverfield/experiments/pull/20), [#21](https://github.com/neverfield/experiments/pull/21) | `bc-c7b7aaa7-baa4-5b34-8e74-b8119781f8db` (export: `bc-df214894-…`) | `docs/selection-step.md`, `internal/selection/` |
| Packet construction and doc health | [#26](https://github.com/neverfield/experiments/pull/26), [#27](https://github.com/neverfield/experiments/pull/27) | `bc-df214894-151a-5b58-ac27-2bc6e40b3fcd` | `docs/packet-construction.md` |
| Lessons | [#12](https://github.com/neverfield/experiments/pull/12), [#23](https://github.com/neverfield/experiments/pull/23), [#25](https://github.com/neverfield/experiments/pull/25), [#28](https://github.com/neverfield/experiments/pull/28), [#29](https://github.com/neverfield/experiments/pull/29) | `bc-b061dd98-2e18-5b63-907f-06412e47f598` and the workers | |
| Linux runner, pre-test fixes, scripted controls | [#31](https://github.com/neverfield/experiments/pull/31), [#32](https://github.com/neverfield/experiments/pull/32), [#33](https://github.com/neverfield/experiments/pull/33) | `bc-ab8b72fd-57be-4f36-a496-c9394d912d35` | |
| Preregistration and test run (EXP-13) | [#34](https://github.com/neverfield/experiments/pull/34), [#35](https://github.com/neverfield/experiments/pull/35), [#36](https://github.com/neverfield/experiments/pull/36) | `bc-ab8b72fd-57be-4f36-a496-c9394d912d35` (#36: `bc-a6c757c7-7494-5524-9e93-8395a751ed9a`) | [PREREGISTRATION.md](PREREGISTRATION.md), store `internal/reconcile/test-run-brief.md` |
| Test reruns: §7.7's addendum, items 1–21 (EXP-13) | [#38](https://github.com/neverfield/experiments/pull/38) | `bc-084152b8-02b8-5000-b1f0-2ba1b6c002fb` | [PREREGISTRATION.md](PREREGISTRATION.md) §7, store `internal/scoring-freeze/` |
| Test scoring: freeze, and item 22's fallback rate (EXP-13) | [#39](https://github.com/neverfield/experiments/pull/39), [#42](https://github.com/neverfield/experiments/pull/42) | `bc-224070da-01e8-5e7d-877c-874257b50263` (Mac tests, merge and scoring: `bc-44045ea2-08c4-50ea-ad04-19d1642ee803`) | [TEST_ANALYSIS.md](TEST_ANALYSIS.md), store `internal/scoring-freeze/heldout-score-ae33125/record.md` |
| Held-out results (EXP-13) | [#43](https://github.com/neverfield/experiments/pull/43) | `bc-44045ea2-08c4-50ea-ad04-19d1642ee803` | store `docs/heldout-results.md`, `docs/heldout-test-report/` |

## Status (as of 2026-11-10)

- Every reported result is on the 61 dev cases. The selection step froze the picks on dev on
  2026-10-29 (store `docs/selection-step.md`).
- The held-out test run is registered in [PREREGISTRATION.md](PREREGISTRATION.md) at commit
  `76882fe` (2026-10-31). Later changes are dated entries in its §7.
- The first test run started on 2026-11-01 in a Docker runner on a laptop. All its agent cells
  but `u50-real-c1-L2` were withdrawn because macOS metadata files had leaked into the copied
  corpus (§7.1).
- Of the 32 passes run after that fix, 10 are kept. The other 22 were withdrawn for a revoked
  API key, a start from an unpushed commit, or a concurrency check fixed before any score was
  read (§7.7).
- The 22 were rerun whole from `c4b458f` on the laptop's runner, from 2026-11-04 to 2026-11-08.
  Test spend was $862.41 when they ended. On the way, 6 passes were withdrawn because the
  agent's MCP tool never reached its server, and the cap rose to $925 for the last queue.
  §7.7's addendum records these and every other deviation in the reruns.
- All 34 registered test passes are accepted. On 2026-11-08, before any score was read, both
  `u50-real-c1-L2` passes kept from 11-01 were withdrawn and rerun whole from `c4b458f`. The
  run recorded no commit for either, and pass 2 ran on an unpushed commit (the addendum's
  item 13). Entry 6's four exploratory L5 N = 50 passes ran too (item 14). Test spend was
  $921.70 when the last pass ended.
- Scoring was frozen at `683880b` ([TEST_ANALYSIS.md](TEST_ANALYSIS.md)). It stopped twice
  there, before any score was read, on agent passes with no finished first run to price from.
  Item 22 prices those runs at the dev selection's rate, and scoring was frozen again at
  `ae33125`.
- On 2026-11-10 the held-out test was scored once, at `ae33125`. All six H1–H3 tests reject H0
  after Holm's adjustment. The results are in store `docs/heldout-results.md`, and the
  scorer's report is store `docs/heldout-test-report/`.
- `repo-discovery run`, `evaluate` and `scripts/test_report.py` need `--registered` for test
  cases.
