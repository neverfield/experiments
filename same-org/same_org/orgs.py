"""Org groups and census loading shared by the scripts.

A dataset name is either one GitHub owner or a group in `GROUPS`, mined and labelled as one org.
"""

from __future__ import annotations

import json
from pathlib import Path

GROUPS = {"k8s": ("kubernetes", "kubernetes-sigs")}


def owners_of(name: str) -> tuple[str, ...]:
    return tuple(o.lower() for o in GROUPS.get(name, (name,)))


def search_scope(name: str) -> str:
    return " ".join(f"org:{o}" for o in owners_of(name))


def in_owners(full_name: str, owners: tuple[str, ...]) -> bool:
    return full_name.split("/", 1)[0].lower() in owners


def load_census(census: str | Path, name: str) -> dict[str, dict]:
    """Every listed repo of the dataset's owners, keyed on lower-case full name."""
    repos = {}
    for o in GROUPS.get(name, (name,)):
        p = Path(census).expanduser() / "repos" / f"{o}.jsonl"
        if not p.exists():
            raise FileNotFoundError(f"no census listing for {o}: {p}")
        for line in open(p):
            r = json.loads(line)
            repos[r["full_name"].lower()] = r
    return repos
