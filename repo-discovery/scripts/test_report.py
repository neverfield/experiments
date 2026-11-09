"""The preregistered held-out test analysis: PREREGISTRATION.md §4 with the addendum to
entry 7, frozen before any test score was read. See TEST_ANALYSIS.md.

    python scripts/test_report.py INPUTS.json --registered COMMIT --out DIR \\
        [--allow-pending] [--s1] [--allow-dirty]
    python scripts/test_report.py --dry-run RUNLIST [--dry-run RUNLIST ...] \\
        (INPUTS.json | --runs-root ROOT) [--s1] [--out FILE]

COMMIT is the registration commit, which the checkout must descend from; it's checked
before anything is read. INPUTS.json says where the cases, passes, static runs,
universes and optional inputs are (TEST_ANALYSIS.md). Each agent cell's per-case values
are the mean over its passes (addendum item 15). The report, tables, figures, CSVs and
JSON go to DIR, and the confirmatory table to stdout. Scoring stops, before any
prediction is read, if a registered pass is pending (unless ``--allow-pending``), fails
its trace bounds, or the code differs from its commit (unless ``--allow-dirty``).

``--dry-run`` reads only the run lists, ``run.env`` stamps and file names, and reports
which passes would be scored and which withdrawn passes S1 would read. It opens no
prediction or trace, and needs no ``--registered``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from heldout_report import build, code_version, write
from heldout_runs import dry_run
from heldout_score import Inputs, ScoringError

from repo_discovery.split import check_registered


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("inputs", nargs="?", type=Path, metavar="INPUTS.json")
    p.add_argument("--registered", metavar="COMMIT", help="the commit that registered the preregistration")
    p.add_argument("--out", type=Path, help="report directory; with --dry-run, a JSON file")
    p.add_argument("--allow-pending", action="store_true", help="score without the pending passes")
    p.add_argument("--s1", action="store_true", help="add sensitivity analysis S1 (off by default)")
    p.add_argument("--allow-dirty", action="store_true", help="run on code that differs from its commit")
    p.add_argument("--dry-run", type=Path, action="append", metavar="RUNLIST")
    p.add_argument("--runs-root", type=Path, help="with --dry-run and no INPUTS.json")
    args = p.parse_args(argv)

    if args.dry_run:
        inputs = Inputs.load(args.inputs) if args.inputs else None
        root = args.runs_root or (inputs.runs_root if inputs else None)
        if root is None:
            p.error("--dry-run needs INPUTS.json or --runs-root")
        text, record = dry_run(
            args.dry_run,
            root,
            inputs.accept if inputs else {},
            args.s1,
            inputs.run_env_commit_key if inputs else None,
        )
        print(text, end="")
        if args.out:
            args.out.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        return 0

    registered = check_registered(args.registered)
    if args.inputs is None or args.out is None:
        p.error("scoring needs INPUTS.json and --out")
    version = code_version()
    if version["dirty"] and not args.allow_dirty:
        raise ScoringError(
            "the analysis code differs from its commit "
            f"({', '.join(version['changed'][:5])}); commit it, or pass --allow-dirty"
        )
    report = build(Inputs.load(args.inputs), registered, args.allow_pending, args.s1)
    write(report, args.out)
    print(f"## {len(report.results)} cells scored; report in {args.out / 'report.md'}\n")
    print(report.tables["confirmatory"], end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
