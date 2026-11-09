"""anonymize_corpus.py on a toy corpus: a build with --collapse-owners against one without,
on the same salt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from repo_discovery.cases import Case, RepoAtCommit, read_cases, write_cases
from repo_discovery.contract import UNIVERSE_FILE, evidence_dir

ROOT = Path(__file__).resolve().parents[1]
REPOS = [
    "getsentry/sentry",
    "getsentry/sentry-cli",
    "sveltejs/svelte",
    "sveltejs/kit",
    "pallets/click",
]
OWNERS = ("getsentry", "sveltejs", "pallets")
PROMPT = "getsentry/sentry-cli drops SvelteKit events; the getsentry SDK owns it, not Sentry."


def commit(repo: str) -> str:
    return f"{REPOS.index(repo):040x}"


def mapping(build: Path) -> dict:
    return json.loads((build / "private" / "mapping.json").read_text())


@pytest.fixture(scope="module")
def builds(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("anon")
    corpus = root / "corpus"
    rows = [
        {"repo": r, "commit": commit(r), "snapshot_date": "2026-02-01", "role": "distractor"}
        for r in REPOS
    ]
    for row in rows:
        owner, name = row["repo"].split("/")
        packet = evidence_dir(corpus, row["repo"], row["commit"])
        packet.mkdir(parents=True)
        (packet / "README.md").write_text(
            f"# {name}\n\nMaintained by {owner}. See {row['repo']}.\n"
        )
        (packet / "paths.txt").write_text(f"README.md\nsrc/{name}/main.py\n")
    listing = corpus / "universes" / "monthly" / "u50" / "d1"
    listing.mkdir(parents=True)
    (listing / UNIVERSE_FILE).write_text("".join(json.dumps(r) + "\n" for r in rows))

    def case(case_id: str, split: str, gold: str) -> Case:
        return Case(
            case_id=case_id,
            source="toy",
            ecosystem="js",
            prompt=PROMPT,
            gold=(RepoAtCommit(gold, commit(gold)),),
            cutoff="2026-03-01T00:00:00+00:00",
            split=split,
        )

    cases = root / "cases.jsonl"
    write_cases(
        cases, [case("d1", "dev", "getsentry/sentry-cli"), case("t1", "test", "pallets/click")]
    )
    path = os.pathsep.join(p for p in (str(ROOT / "src"), os.environ.get("PYTHONPATH")) if p)
    out = {}
    for variant, extra in (("default", []), ("collapsed", ["--collapse-owners"])):
        target = root / variant
        (target / "private").mkdir(parents=True)
        (target / "private" / "salt").write_text("ab" * 32 + "\n")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "anonymize_corpus.py"),
                *("--corpus", str(corpus), "--tier", "u50", "--cases", str(cases)),
                *("--out", str(target), "--workers", "1", *extra),
            ],
            env={**os.environ, "PYTHONPATH": path},
            check=True,
            capture_output=True,
        )
        out[variant] = target
    return out


def test_collapsed_build_has_one_owner_and_the_default_builds_repository_ids(
    builds: dict[str, Path],
) -> None:
    default, collapsed = mapping(builds["default"]), mapping(builds["collapsed"])
    [shared] = set(collapsed["owners"].values())
    assert len(set(default["owners"].values())) == len(OWNERS)
    assert collapsed["cases"] == default["cases"]
    for repo in REPOS:
        owner, name = collapsed["repos"][repo].split("/")
        assert owner == shared and name.startswith("r")
        if default["repos"][repo].split("/")[1].startswith("r"):
            assert name == default["repos"][repo].split("/")[1]
    [case_dir] = (builds["collapsed"] / "universes" / "monthly" / "u50").iterdir()
    listed = [json.loads(line)["repo"] for line in (case_dir / UNIVERSE_FILE).open()]
    assert sorted(listed) == sorted(collapsed["repos"].values())
    assert {p.name.split("__")[0] for p in (builds["collapsed"] / "repos").iterdir()} == {shared}
    stats = json.loads((builds["collapsed"] / "scrub-stats.json").read_text())
    assert (stats["owner_ids"], stats["collapse_owners"]) == (1, True)
    stats = json.loads((builds["default"] / "scrub-stats.json").read_text())
    assert (stats["owner_ids"], stats["collapse_owners"]) == (len(OWNERS), False)


def test_collapsed_build_leaves_no_owner_to_group_by(builds: dict[str, Path]) -> None:
    default, collapsed = mapping(builds["default"]), mapping(builds["collapsed"])
    shared, anon = collapsed["owners"]["getsentry"], collapsed["repos"]
    sentry = anon["getsentry/sentry"].split("/")[1]
    [case] = read_cases(builds["collapsed"] / "cases-scrubbed.jsonl")
    assert case.prompt == (
        f"{anon['getsentry/sentry-cli']} drops {anon['sveltejs/kit']} events; "
        f"the {shared} SDK owns it, not {sentry}."
    )
    assert [g.repo for g in case.gold] == [anon["getsentry/sentry-cli"]]
    assert [c.prompt for c in read_cases(builds["collapsed"] / "cases-verbatim.jsonl")] == [PROMPT]

    packet = evidence_dir(builds["collapsed"], anon["getsentry/sentry"], commit("getsentry/sentry"))
    readme = (packet / "README.md").read_text()
    assert readme == f"# {sentry}\n\nMaintained by {shared}. See {anon['getsentry/sentry']}.\n"
    text = "".join(
        p.read_text().lower() for p in (builds["collapsed"] / "repos").rglob("*") if p.is_file()
    )
    for leak in (*OWNERS, *default["owners"].values()):
        assert leak not in text and leak not in case.prompt.lower()
