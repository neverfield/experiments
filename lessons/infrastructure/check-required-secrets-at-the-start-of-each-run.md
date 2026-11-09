# Check required secrets at the start of each run

**Experiment:** repo-discovery · **Added:** 2026-10-29 · **Source:** coordinator's notes; store `docs/repo-discovery-study.plan.md` §9

**What happened.** A secret was added to the Cloud Agent settings partway through the study. VMs that were already running didn't see it.

**What it cost.** Work on those VMs that needed the secret couldn't go ahead until it ran on a fresh VM.

**Next time.** At the start of each run, check that every required secret is set, without printing it:

```bash
for v in CURSOR_API_KEY; do [ -n "${!v:-}" ] || echo "missing: $v"; done
```

After adding a secret, start a new VM rather than waiting for a running one to pick it up.

**Seen again:** same-org feasibility (store `internal/same-org-feasibility/handoff.md`). The GitHub integration was reinstalled at 01:27:50 UTC after the repo was renamed. Every authenticated call from the running agent then returned 401, and its token never came back, because the run was tied to the repo's old name. The work moved to a new agent from a handoff note. Check the token and the repo's current name at the start, and again before a long fetch, with one cheap call such as `GET /rate_limit`. Make long fetches resumable from a cache, so another run can continue them.
