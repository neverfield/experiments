# Check which author and repo pair supply the positives before counting them

**Experiment:** same-org feasibility · **Added:** 2026-11-09 · **Source:** store `docs/same-org-feasibility.md` (Evidence: distinct changes)

**What happened.** The first hashicorp count had 164 issue-close and 686 shared-branch multi-repo cases, the most of any method. All 164 issue-close cases and 618 of the branch cases were the same pair, `terraform-provider-google` and `terraform-provider-google-beta`, with PRs opened about eight seconds apart by `modular-magician`. That account is Google's Magic Modules generator, and it runs as a GitHub User, so the `Bot` type and the `[bot]` suffix both missed it. With it filtered out, hashicorp has 0 issue-close and 83 branch cases.

**What it saved.** The headline count for hashicorp would have been about six times too high, and a hand-check sample drawn from it would have been mostly generated mirrors.

**Next time.** Before reporting a count of positives, list the top authors and the top target sets with their shares, and the share of cases whose parts were created within a couple of minutes of each other. Treat any single source above about 10% as a likely generator or mirror until someone has looked at it, and report the count with and without it.
