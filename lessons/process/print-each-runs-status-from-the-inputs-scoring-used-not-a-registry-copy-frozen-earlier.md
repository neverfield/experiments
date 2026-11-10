# Print each run's status from the inputs scoring used, not a registry copy frozen earlier

**Experiment:** repo-discovery held-out test (EXP-13), scoring · **Added:** 2026-11-10 · **Source:** store `docs/heldout-results.md` (The `u50-real-c1-L2` "pending" label); store `docs/heldout-test-report/report/report.md` (Passes scored); `repo-discovery/scripts/heldout_plan.py` (`ITEM_12`)

**What happened.**
- **The code kept a copy of a registered table.** The scoring code keeps a copy of the addendum's per-pass table (item 12) in `heldout_plan.ITEM_12`. It was copied at 00:39 UTC on 2026-11-09, while the two `u50-real-c1-L2` reruns were pending, and both rows read "none yet; rerun pending (item 13)".
- **The registry moved on and the copy didn't.** The reruns passed their audit at 01:20 UTC. The addendum's own item 12 was updated at 01:36 to show them accepted, but the code's copy wasn't.
- **That was partly by design.** Acceptance reached scoring through `INPUTS.json`'s `accept` list (`TEST_ANALYSIS.md`, choice 3). The copy's "pending" is what made scoring stop without that list.
- **The report contradicts itself.** Its passes table shows both passes as "pending", with "none yet", while its Commit column shows their `c4b458f` reruns. Every result table scores them, as the U50 real-name primary pick. Only `results.json`'s `choices.pending` says why.

**What it cost.** A table in the report of record that contradicts the results under it. The code was frozen, so the contradiction can only be explained in the write-up.

**Next time.**
- **Print what scoring used.** Have the report print each run's status from the inputs scoring actually used, such as "accepted (`INPUTS.json` accept: item 13 audit)", not a status set before the decision.
- **Don't hand-copy registered tables into code.** Parse them from the registered text, or add a test that the copy matches it.
- **Test the case in the synthetic study.** Include a pass that's pending in the registry and accepted in the inputs, and check its row in the passes table.
