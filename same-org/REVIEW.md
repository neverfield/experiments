# Hand-check guide for `sample_review.py` sheets

Each `## R001` block is one candidate multi-repo change. It shows the target repos, the PRs (date, author, branch, files changed, link contexts, title and the start of the body), and either the PR-to-PR edges that formed the change or the hub issue the PRs link to. Block IDs are shuffled and hide which label method found the change; a change found by several methods appears once, and `sample.json` maps each block to its cases. Judge from the sheet alone, and record one entry per block in `verdicts.json`:

```json
{"R001": {"v": "same", "kind": "coordinated", "unsure": false, "why": "API field added in X, client reads it in Y"}}
```

**Verdict (`v`).** The question is whether the target repos are the repos one piece of work had to change: if a developer had been handed that piece of work, would each target repo have needed a change?

| `v` | When |
|---|---|
| `same` | Every target repo's PRs belong to one piece of work. |
| `partial` | At least two target repos belong to one piece of work, and at least one target doesn't. |
| `not` | Fewer than two target repos belong to one piece of work: the PRs are separate pieces of work joined by a loose mention, a shared issue they don't serve, or a coincidental branch name. |

**Kind (`kind`)**, for `same` and `partial`, the kind of the piece of work; for `not`, why it fails.

| `kind` | Meaning |
|---|---|
| `coordinated` | Different code changes per repo that together deliver one feature or fix (API and client, library and consumer code beyond a version bump). |
| `propagation` | A change in one repo, plus a dependency bump or vendoring in another repo to pick it up, with little other code. |
| `mirror` | The same fix or feature applied separately to sibling repos (duplicated code, parallel plugins) for one need. |
| `sweep` | One mechanical change (CI, config, linting, license, dependency pinning, bot setup) applied across several repos. |
| `epic` | An umbrella issue whose PRs deliver one larger feature or migration over weeks or months. |
| `followup` | A later change in another repo that reacts to an earlier, separately requested change, such as adapting to a breaking change weeks later. Usually `not`. |
| `unrelated` | No real connection. `not` only. |
| `other` | Anything else; say what in `why`. |

Set `unsure` to true when the sheet's text isn't enough to decide. Keep `why` under 25 words. Don't look anything up: the point is what the mined evidence shows.
