"""The frozen held-out analysis (scripts/test_report.py and scripts/heldout_*.py), on a
synthetic study: 59 invented test cases in 30 ecosystems, hidden-name copies, layered
universes, every registered pass and static run. Nothing here comes from the test run."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shlex
import statistics
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from repo_discovery import split
from repo_discovery.cases import Case, RepoAtCommit, write_cases
from repo_discovery.contract import evidence_dir
from repo_discovery.metrics import case_metrics
from repo_discovery.predictions import Prediction, write_predictions

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import heldout_plan as plan
import heldout_report as hreport
import heldout_runs as runs
import heldout_score as score
import test_report as report

REAL, HIDDEN = "real", "hidden"
VISIBILITY = ("none", "partial", "complete")
N_FRAME = 24
PENDING = [k for k, p in plan.PASSES.items() if p.status == "pending"]
# Cells whose rankings the tests fix; every other ranking puts the targets first or last
# by a hash of (cell, pass or draw, case).
FIXED = {
    ("u5000-real-c2-hybrid-L4", None): "first",
    ("u5000-real-bm25f", None): "last",
    ("u250-real-l5-n10", "p1"): "first",
    ("u250-real-l5-n10", "p2"): "last",
    ("u5000-real-scripted-search", None): "missing",
}


# The synthetic study -------------------------------------------------------------------


def sha(*parts: int) -> str:
    return "".join(f"{p:04x}" for p in parts).ljust(40, "0")


def owner_of(eco: int, names: str) -> str:
    return f"own{eco:02d}" if names == REAL else f"anon{eco:02d}"


def study_case(i: int, names: str) -> Case:
    eco = i // 2
    o = owner_of(eco, names)
    return Case(
        case_id=f"t{i:02d}" if names == REAL else f"h{i:02d}",
        source="wideswe",
        ecosystem=f"eco{eco:02d}" if names == REAL else f"anon-eco{eco:02d}",
        prompt=f"Change {i}",
        gold=tuple(RepoAtCommit(f"{o}/g{i:02d}-{j}", sha(i, j, 1)) for j in range(1 + i % 3)),
        cutoff="2025-06-01T00:00:00+00:00",
        context=tuple(RepoAtCommit(f"{o}/ctx{i:02d}-{j}", sha(i, j, 2)) for j in range(2)),
        scope_visibility=VISIBILITY[i % 3],
        split="test",
    )


def same_owner(i: int) -> int:
    return 3 + 6 * (i % 2)


def universe_rows(case: Case, i: int) -> list[dict]:
    o = case.gold[0].repo.split("/")[0]

    def row(repo: str, commit: str, role: str, source: str | None = None) -> dict:
        out = {"repo": repo, "commit": commit, "snapshot_date": "2026-02-28", "role": role}
        return out | ({"source": source} if source else {})

    return [
        *(row(g.repo, g.commit, "gold") for g in case.gold),
        *(row(c.repo, c.commit, "ecosystem", "wideswe") for c in case.context),
        *(
            row(f"{o}/so{i:02d}-{k}", sha(i, k, 3), "ecosystem", "same_owner")
            for k in range(same_owner(i))
        ),
        *(row(f"frm{k:02d}/f{k:02d}", sha(k, 0, 4), "distractor", "frame") for k in range(N_FRAME)),
    ]


def write_universe(root: Path, rows: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "universe.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    for r in rows:
        packet = evidence_dir(root, r["repo"], r["commit"])
        packet.mkdir(parents=True, exist_ok=True)
        (packet / "README.md").write_text(f"# {r['repo']}\n", encoding="utf-8")
        (packet / "paths.txt").write_text("README.md\n", encoding="utf-8")


def mode(cell: str, label: str | None, i: int) -> str:
    for key in ((cell, label), (cell, None)):
        if key in FIXED:
            return FIXED[key]
    if cell.endswith("bm25f-deps-random"):
        return "first" if i % 5 < int(label or 0) else "last"
    return "first" if hashlib.md5(f"{cell}|{label}|{i}".encode()).digest()[0] < 128 else "last"


def ranking(rows: list[dict], gold: tuple[str, ...], how: str, i: int) -> list[str]:
    others = sorted(
        (r["repo"] for r in rows if r["role"] != "gold"),
        key=lambda r: hashlib.md5(f"{i}|{r}".encode()).hexdigest(),
    )
    return {"first": [*gold, *others], "last": [*others, *gold], "missing": others}[how]


def events(i: int, target_owner: str) -> list[dict]:
    """Case i's first search: names the owner (grep), names it only in a path (not named),
    no search, or names it in a ``search_repos`` query."""
    kind = i % 4
    if kind == 2:
        return [{"type": "assistant", "message": target_owner}]
    if kind == 0:
        call = {"grepToolCall": {"args": {"pattern": f"{target_owner}/", "path": "/u"}}}
    elif kind == 1:
        call = {"grepToolCall": {"args": {"pattern": "change", "path": f"/u/{target_owner}"}}}
    else:
        call = {
            "mcpToolCall": {
                "args": {
                    "name": "repo-search_repos",
                    "args": {"query": f"{target_owner.upper()} x"},
                }
            }
        }
    return [{"type": "tool_call", "subtype": "started", "tool_call": call}]


def trace(spec: plan.CellSpec, ranked: list[str], i: int, status: str = "ok") -> dict:
    out = {
        "status": status,
        "runs": [
            {"status": "ok", "usage": {"inputTokens": 1000 + i, "outputTokens": 100}, "context": []}
        ],
        "seconds": 10.0 + i,
        "returned": min(len(ranked), 20),
        "opened": ranked[:3] if spec.method == "l5" else [],
    }
    if spec.tool:
        out["tools"] = {"mcpToolCall": 2}
        out["searches" if spec.tool == "search_repos" else "opens"] = [{"n": 1}]
    return out


class Study:
    """A synthetic study tree and its inputs file."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.cases = {
            names: [study_case(i, names) for i in range(plan.N_CASES)] for names in plan.NAMES
        }
        self.rows = {
            names: [universe_rows(c, i) for i, c in enumerate(cs)]
            for names, cs in self.cases.items()
        }
        dev = [replace(study_case(i, REAL), case_id=f"d{i}", split="dev") for i in range(3)]
        write_cases(root / "cases" / "real.jsonl", [*self.cases[REAL], *dev])
        write_cases(root / "cases" / "hidden.jsonl", self.cases[HIDDEN])
        mapping = {f"t{i:02d}": f"h{i:02d}" for i in range(plan.N_CASES)}
        (root / "cases" / "map.json").write_text(json.dumps({"cases": mapping}))
        reviewed = [replace(c, gold=c.gold[:1]) for c in self.cases[REAL]]
        write_cases(root / "cases" / "reviewed-real.jsonl", reviewed)
        for names, cases in self.cases.items():
            for case, rows in zip(cases, self.rows[names], strict=True):
                write_universe(root / "universes" / names / case.case_id, rows)
        with (root / "merge_dates.jsonl").open("w") as handle:
            for i in range(plan.N_CASES):
                handle.write(
                    json.dumps(
                        {
                            "case_id": f"t{i:02d}",
                            "last_merge": "2026-01-15" if i < 25 else "2026-04-01",
                        }
                    )
                    + "\n"
                )
        sizes = {s: [s, s / 100] for s in plan.SIZES}
        costs = {
            "fetch": {lvl: sizes for lvl in ("L0", "L1", "L2", "L3", "L4")},
            "index": {"bm25f": {"*": {"build_ms": 1.0, "kb": 2.0, "query_s": 0.01}}},
        }
        (root / "costs.yaml").write_text(json.dumps(costs))
        for key, registered in plan.PASSES.items():
            self.write_pass(plan.TEST_AREA, key, registered)
        for key in plan.S1_PASSES:
            self.write_pass(plan.S1_AREA, key, plan.PASSES[key], withdrawn=True)
        for spec in plan.CELLS.values():
            if not spec.agent:
                self.write_static(spec)
        self.inputs = root / "inputs.json"
        self.write_inputs()

    def write_inputs(self, **changes: object) -> Path:
        inputs = {
            "runs_root": "runs",
            "cases": {"real": "cases/real.jsonl", "hidden": "cases/hidden.jsonl"},
            "case_map": "cases/map.json",
            "static": "static/{cell}.jsonl",
            "static_draws": {"template": "static/{cell}-{draw}.jsonl", "draws": [0, 1, 2, 3, 4]},
            "universes": {"real": "universes/real", "hidden": "universes/hidden"},
            "accept": {k: "audit passed (synthetic)" for k in PENDING},
            "merge_dates": "merge_dates.jsonl",
            "reviewed": {"real": "cases/reviewed-real.jsonl"},
            "costs": "costs.yaml",
        } | changes
        self.inputs.write_text(json.dumps({k: v for k, v in inputs.items() if v is not None}))
        return self.inputs

    def predictions(
        self, spec: plan.CellSpec, label: str | None, how: Callable[[int], str] | None = None
    ) -> list[Prediction]:
        out = []
        for i, case in enumerate(self.cases[spec.names]):
            ranked = ranking(
                self.rows[spec.names][i],
                case.gold_repos,
                (how or (lambda i: mode(spec.name, label, i)))(i),
                i,
            )
            out.append(Prediction(case.case_id, spec.method, tuple(ranked), "u", spec.size, 0.1))
        return out

    def write_pass(
        self, area: str, key: str, registered: plan.RegisteredPass, withdrawn: bool = False
    ) -> None:
        spec = plan.CELLS[registered.cell]
        directory = self.root / "runs" / area / key
        label = key.split("/")[0]
        how = (lambda i: "last") if withdrawn else None
        predictions = self.predictions(spec, label, how)
        if withdrawn:
            predictions = predictions[:-2]
        write_predictions(directory / plan.PRED_FILE, predictions)
        for i, (case, p) in enumerate(
            zip(self.cases[spec.names], self.predictions(spec, label, how), strict=True)
        ):
            status = "timeout" if withdrawn and i < 3 else "ok"
            (directory / f"{case.case_id}.json").write_text(
                json.dumps(trace(spec, list(p.ranking), i, status))
            )
            o = case.gold[0].repo.split("/")[0]
            (directory / f"{case.case_id}.events.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events(i, o))
            )
        if not registered.kept:
            (directory / plan.RUN_ENV).write_text(
                f"started=2026-11-08T10:00:00Z\nhost=docker-linux\ncomplete=1\ncommit={plan.RERUN_COMMIT}\nAPI_TOKEN=do-not-read\n"
            )

    def write_static(self, spec: plan.CellSpec) -> None:
        if spec.draws == 1:
            write_predictions(
                self.root / "static" / f"{spec.name}.jsonl", self.predictions(spec, None)
            )
            return
        for d in range(spec.draws):
            write_predictions(
                self.root / "static" / f"{spec.name}-{d}.jsonl", self.predictions(spec, str(d))
            )

    def pass_dir(self, key: str, area: str = plan.TEST_AREA) -> Path:
        return self.root / "runs" / area / key

    def run_list(self, name: str, keys: list[str], area: str = plan.TEST_AREA) -> Path:
        lines = ["# synthetic run list", *(run_line(self.root / "runs", area, k) for k in keys)]
        path = self.root / f"{name}.txt"
        path.write_text("\n".join(lines) + "\n")
        return path


def run_line(runs_root: Path, area: str, key: str) -> str:
    spec = plan.CELLS[key.split("/", 1)[1]]
    out = runs_root / area / key / plan.PRED_FILE
    tokens = [
        "python",
        "scripts/v5_dev_run.py",
        "--split",
        "test",
        "--registered",
        plan.REGISTRATION[:7],
        "--universes",
        f"/data/u{spec.size}/{spec.level or 'L4'}",
        "--out",
        str(out),
        "--trace-dir",
        str(out.parent),
    ]
    if spec.method == "l5":
        tokens += ["--evidence", "on-demand", "--open-budget", str(spec.budget)]
    if spec.search:
        tokens += ["--search", spec.search]
    if spec.names == HIDDEN:
        tokens += ["--anonymized", "everywhere"]
    return shlex.join(tokens)


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> Study:
    return Study(tmp_path_factory.mktemp("study"))


@pytest.fixture(autouse=True)
def registered(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Stands in for the git check (CI clones one commit deep) and records each commit."""
    seen: list[str | None] = []

    def check(commit: str | None, repo: Path | None = None) -> str:
        seen.append(commit)
        if not commit:
            raise SystemExit("test cases need --registered COMMIT")
        return plan.REGISTRATION

    monkeypatch.setattr(split, "check_registered", check)
    monkeypatch.setattr(report, "check_registered", check)
    monkeypatch.setattr(
        hreport,
        "code_version",
        lambda repo=None: {"commit": "f" * 40, "dirty": False, "changed": []},
    )
    monkeypatch.setattr(
        report,
        "code_version",
        lambda repo=None: {"commit": "f" * 40, "dirty": False, "changed": []},
    )
    return seen


@pytest.fixture(scope="module")
def built(study: Study, tmp_path_factory: pytest.TempPathFactory) -> tuple[hreport.Report, Path]:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(split, "check_registered", lambda commit, repo=None: plan.REGISTRATION)
        mp.setattr(
            hreport,
            "code_version",
            lambda repo=None: {"commit": "f" * 40, "dirty": False, "changed": []},
        )
        result = hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION)
        out = tmp_path_factory.mktemp("report")
        hreport.write(result, out)
    return result, out


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def cell_value(out: Path, cell: str, metric: str, group: str = "all") -> dict:
    return next(
        r
        for r in read_csv(out / "cells.csv")
        if r["cell"] == cell and r["metric"] == metric and r["group"] == group
    )


# The plan -------------------------------------------------------------------------------


def test_plan_matches_the_registration_and_addendum() -> None:
    statuses = [p.status for p in plan.PASSES.values()]
    assert len(statuses) == 38
    assert statuses.count("pending") == 2 and statuses.count("exploratory") == 4
    assert sum(p.kept for p in plan.PASSES.values()) == 10
    assert {p.commit for p in plan.PASSES.values() if p.kept} == {plan.KEPT_COMMIT}
    assert len(plan.CONFIRMATORY) == 6 and {c.metric for c in plan.CONFIRMATORY} == {plan.PRIMARY}
    assert len(plan.REGISTERED_AGENT_CELLS) == 17 and len(plan.AGENT_CELLS) == 19
    assert sum(not c.agent for c in plan.CELLS.values()) == 201
    assert len(plan.S1_PASSES) == 5 and set(plan.S1_TOOL_BROKEN) <= set(plan.S1_PASSES)
    assert all(plan.PASSES[k].cell == k.split("/", 1)[1] for k in plan.PASSES)


# Item 17's definitions ------------------------------------------------------------------


def test_owner_reference_is_the_exact_random_order_expectation() -> None:
    assert score.owner_reference(8, 2) == 1.0
    assert score.owner_reference(10, 3) == 1.0
    assert score.owner_reference(20, 2) == pytest.approx(45 / 190)
    assert score.owner_reference(12, 1) == pytest.approx(10 / 12)
    rng = np.random.default_rng(1)
    hits = [set(rng.permutation(20)[:10]) >= {0, 1} for _ in range(20000)]
    assert np.mean(hits) == pytest.approx(45 / 190, abs=0.01)


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("acme/billing", True),
        ("ACME billing", True),
        ("from acme_core", True),
        ("acme-corp", False),
        ("xacme", False),
        ("acme2", False),
        ("the-acme", False),
        ("(acme)", True),
        ("billing", False),
    ],
)
def test_first_search_owner_match_is_a_whole_token(text: str, named: bool) -> None:
    assert score.names_owner(text, ["acme"]) is named


def test_first_search_reads_the_first_grep_glob_or_search_repos_call(tmp_path: Path) -> None:
    def first(*calls: dict) -> str:
        path = tmp_path / "e.jsonl"
        lines = [{"type": "tool_call", "subtype": "started", "tool_call": c} for c in calls]
        lines.insert(
            0,
            {
                "type": "tool_call",
                "subtype": "completed",
                "tool_call": {"grepToolCall": {"args": {"pattern": "acme"}}},
            },
        )
        path.write_text("".join(json.dumps(x) + "\n" for x in lines))
        return score.first_search(path, ["acme"])

    read = {"readToolCall": {"args": {"path": "acme/README.md"}}}
    shell = {"shellToolCall": {"args": {"command": "rg acme"}}}
    assert (
        first(read, shell, {"grepToolCall": {"args": {"pattern": "acme", "path": "/x"}}}) == "named"
    )
    assert (
        first({"grepToolCall": {"args": {"pattern": "billing", "path": "/u/acme"}}}) == "not-named"
    )
    assert (
        first({"globToolCall": {"args": {"globPattern": "**/acme*", "targetDirectory": "/u"}}})
        == "named"
    )
    assert (
        first(
            {
                "mcpToolCall": {
                    "args": {"name": "srv-search_repos", "args": {"query": "Acme ledger"}}
                }
            }
        )
        == "named"
    )
    assert (
        first({"mcpToolCall": {"args": {"toolName": "search_repos", "args": {"query": "ledger"}}}})
        == "not-named"
    )
    assert (
        first({"mcpToolCall": {"args": {"name": "srv-open_repo", "args": {"repo": "acme/x"}}}})
        == "none"
    )
    assert first(read, shell) == "none"
    assert score.first_search(tmp_path / "absent.jsonl", ["acme"]) == "none"


def test_first_search_reads_the_dev_event_layout(tmp_path: Path) -> None:
    def started(call: dict) -> dict:
        return {
            "type": "tool_call",
            "subtype": "started",
            "call_id": "c1",
            "tool_call": call
            | {"hookAdditionalContexts": [], "toolCallId": "toolu_01", "startedAtMs": "1"},
            "model_call_id": "m1",
            "session_id": "s1",
            "timestamp_ms": 1,
            "_run_s": 0.1,
        }

    def grep(pattern: str, output_mode: str = "content") -> dict:
        args = {
            "pattern": pattern,
            "path": "/tmp/v5-x/workspace/acme",
            "glob": "*.md",
            "outputMode": output_mode,
            "caseInsensitive": False,
            "headLimit": 20,
            "multiline": False,
            "toolCallId": "toolu_01",
            "offset": 0,
        }
        return {"grepToolCall": {"args": args}}

    search = {
        "mcpToolCall": {
            "args": {
                "name": "repo-discovery-search_repos",
                "args": {"query": "acme ledger", "k": 20},
                "toolCallId": "toolu_02",
                "providerIdentifier": "repo-discovery",
                "toolName": "search_repos",
                "smartModeApprovalOnly": False,
                "skipApproval": True,
                "serverIdentifier": "repo-discovery",
                "symbolicPathArguments": [],
                "argumentsRepaired": False,
            }
        }
    }
    read = {"readToolCall": {"args": {"path": "acme/README.md", "offset": 0, "limit": 50}}}
    glob = {"globToolCall": {"args": {"targetDirectory": "/u/acme", "globPattern": "**/*.toml"}}}

    def first(owner: str, *calls: dict) -> str:
        path = tmp_path / "events.jsonl"
        init = {"type": "system", "subtype": "init", "session_id": "s1", "model": "m"}
        path.write_text("".join(json.dumps(x) + "\n" for x in [init, *map(started, calls)]))
        return score.first_search(path, [owner])

    assert first("acme", read, grep("acme/")) == "named"
    assert first("acme", read, grep("billing")) == "not-named"
    assert first("acme", glob) == "not-named"
    assert first("acme", search) == "named"
    assert first("acme", read) == "none"


def test_first_search_ignores_output_mode_and_tool_call_id() -> None:
    grep = {
        "grepToolCall": {
            "args": {
                "pattern": "ledger",
                "path": "/u/acme",
                "glob": "*.md",
                "outputMode": "files_with_matches",
                "caseInsensitive": False,
                "toolCallId": "toolu_01",
            }
        },
        "toolCallId": "toolu_01",
    }
    assert score.search_string(grep) == "ledger *.md"
    for owner in ("files", "matches", "toolu"):
        assert not score.names_owner(score.search_string(grep) or "", [owner])
    in_glob = {"grepToolCall": {"args": {"pattern": "x", "glob": "acme/*", "outputMode": "count"}}}
    assert score.names_owner(score.search_string(in_glob) or "", ["acme"])
    glob = {"globToolCall": {"args": {"globPattern": "**/acme*", "targetDirectory": "/u"}}}
    assert score.search_string(glob) == "**/acme*"


def test_first_search_keeps_underscore_as_a_token_boundary(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    call = {"grepToolCall": {"args": {"pattern": "acme_core", "outputMode": "content"}}}
    path.write_text(json.dumps({"type": "tool_call", "subtype": "started", "tool_call": call}))
    assert score.first_search(path, ["acme"]) == "named"
    assert score.names_owner("acme_core", ["acme"]) and score.names_owner("core_acme", ["acme"])


def test_first_search_counts_a_call_with_no_search_text(tmp_path: Path) -> None:
    empty = {
        "grepToolCall": {
            "args": {"path": "/u/acme", "outputMode": "content", "toolCallId": "toolu_01"}
        }
    }
    assert score.search_string(empty) == ""
    assert score.search_string({"globToolCall": {"args": {"targetDirectory": "/u/acme"}}}) == ""
    named = {"grepToolCall": {"args": {"pattern": "acme"}}}
    path = tmp_path / "e.jsonl"
    path.write_text(
        "".join(
            json.dumps({"type": "tool_call", "subtype": "started", "tool_call": c}) + "\n"
            for c in (empty, named)
        )
    )
    assert score.first_search(path, ["acme"]) == "not-named"


def test_set_quality_and_top10_fill() -> None:
    universe = score.CaseUniverse(
        {
            "a/g1": "other",
            "a/g2": "other",
            "a/s": "same_owner",
            "a/c": "wideswe",
            "f/x": "frame",
            "b/y": "frame",
        },
        frozenset({"a/g1", "a/g2", "a/s", "a/c"}),
        1.0,
    )
    gold = ("a/g1", "A/G2")
    v = score.ranking_values(gold, ["a/g2", "a/g1", "f/x"], universe)
    assert v[score.GIVEN] == 1.0 and v["CompleteRecall@3"] == 1.0
    assert v[score.ABOVE_LAST] == 0
    v = score.ranking_values(gold, ["a/g1", "f/x", "a/s", "a/g2", "b/y"], universe)
    assert v[score.GIVEN] == 0.0 and v["CompleteRecall@3"] == 0.0 and v["CompleteRecall@5"] == 1.0
    assert v[score.ABOVE_LAST] == 2
    assert v[f"{score.TOP10}non-targets"] == 3
    assert (
        v[f"{score.TOP10}frame"],
        v[f"{score.TOP10}same_owner"],
        v[f"{score.TOP10}wideswe"],
    ) == (2, 1, 0)
    assert (v[f"{score.TOP10}target-owner"], v[f"{score.TOP10}other-owner"]) == (1, 2)
    assert v[f"{score.OWNER}{score.GIVEN}"] == 0.0
    assert v[f"{score.OWNER}LastRequiredRank"] == 3
    # Raw ranks, as case_metrics counts them: a repeated repository still takes a rank.
    v = score.ranking_values(("a/g1",), ["f/x", "f/x", "a/g1"])
    assert (
        v["LastRequiredRank"]
        == case_metrics(("a/g1",), ["f/x", "f/x", "a/g1"], plan.KS)["LastRequiredRank"]
        == 3
    )
    assert v[score.ABOVE_LAST] == 2
    # Censored when a target ranks below 100 or not at all.
    filler = [f"z/{k}" for k in range(100)]
    assert math.isinf(score.ranking_values(gold, [*filler, "a/g1", "a/g2"])[score.ABOVE_LAST])
    assert math.isinf(score.ranking_values(gold, ["a/g1"])[score.ABOVE_LAST])
    assert score.ranking_values(gold, [*filler[:98], "a/g1", "a/g2"])[score.ABOVE_LAST] == 98
    v = score.ranking_values(gold, ["a/g1", "a/g2"], reviewed=("a/g1",))
    assert v[f"{score.REVIEWED}CompleteRecall@10"] == 1.0


def test_case_universe_owner_set_and_layers(study: Study) -> None:
    case = study.cases[REAL][3]
    u = score.case_universe(study.root / "universes" / REAL, case)
    assert len(u.owner_set) == len(case.gold) + 2 + same_owner(3)
    assert u.layer["frm00/f00"] == "frame" and u.layer[case.context[0].repo] == "wideswe"
    assert u.reference == pytest.approx(
        math.comb(10, len(case.gold)) / math.comb(len(u.owner_set), len(case.gold))
    )


def test_pool_means_each_case_over_its_parts() -> None:
    pooled = score.pool([{"c": {"x": 1.0, "y": 2.0}}, {"c": {"x": 0.0}}])
    assert pooled == {"c": {"x": 0.5}}
    assert math.isinf(score.pool([{"c": {"x": math.inf}}, {"c": {"x": 1.0}}])["c"]["x"])


# The bootstrap and Holm are the registered ones ---------------------------------------


def old_bootstrap(diffs: np.ndarray, clusters: list[str]) -> tuple[float, float, float, float]:
    """scripts/test_report.py's bootstrap as registered (before this rewrite)."""
    _, index = np.unique(np.asarray(clusters), return_inverse=True)
    sums, counts = np.bincount(index, weights=diffs), np.bincount(index)
    draws = np.random.default_rng(0).integers(0, len(sums), size=(2000, len(sums)))
    reps = sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    low, high = np.quantile(reps, [0.025, 0.975])
    return float(diffs.mean()), float(low), float(high), float((reps <= 0).mean())


def old_holm(pvalues: dict[str, float], alpha: float = 0.05) -> dict[str, tuple[float, bool]]:
    order = sorted(pvalues, key=pvalues.get)  # type: ignore[arg-type]
    out, running, rejecting = {}, 0.0, True
    for i, name in enumerate(order):
        running = min(1.0, max(running, (len(order) - i) * pvalues[name]))
        rejecting = rejecting and running <= alpha
        out[name] = (running, rejecting)
    return out


def test_comparisons_match_the_registered_bootstrap_and_holm() -> None:
    rng = np.random.default_rng(7)
    ids = [f"c{i:02d}" for i in range(59)]
    ecosystem = {i: f"e{k // 2:02d}" for k, i in enumerate(ids)}
    spec = plan.CELLS["u5000-real-bm25f"]
    cells = {}
    for name in {n for c in plan.CONFIRMATORY for n in (c.a, c.b)}:
        values = {
            i: {m: float(rng.random() < 0.5) for m in (plan.PRIMARY, plan.KEY_SECONDARY)}
            for i in ids
        }
        cells[name] = score.CellResult(replace(spec, name=name), [name], values, [values])
    rows, _ = score.comparisons(cells, ecosystem)
    expected_p = {}
    for row in rows:
        c = row.comparison
        if c.family != "confirmatory":
            continue
        diffs = np.array(
            [
                cells[c.a].per_case[i][plan.PRIMARY] - cells[c.b].per_case[i][plan.PRIMARY]
                for i in ids
            ]
        )
        mean, low, high, p = old_bootstrap(diffs, [ecosystem[i] for i in ids])
        assert (row.interval.mean, row.interval.low, row.interval.high) == pytest.approx(
            (mean, low, high), abs=1e-12
        )
        assert row.p_one_sided == pytest.approx(p, abs=1e-12)
        expected_p[c.id] = p
    assert len(expected_p) == 6
    for row in rows:
        if row.comparison.id in expected_p:
            p_holm, reject = old_holm(expected_p)[row.comparison.id]
            assert row.p_holm == pytest.approx(p_holm) and row.reject is reject
    assert all(r.p_one_sided is None for r in rows if r.comparison.family != "confirmatory")


# What stops scoring, before any prediction is read ------------------------------------


@pytest.fixture
def no_predictions(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(path: Path) -> None:
        raise AssertionError(f"read {path}")

    monkeypatch.setattr(score, "read_predictions", refuse)


def test_pending_passes_stop_scoring_unless_accepted(study: Study, no_predictions: None) -> None:
    inputs = score.Inputs.load(study.write_inputs(accept={}))
    try:
        with pytest.raises(SystemExit, match="2 registered passes are pending"):
            hreport.build(inputs, plan.REGISTRATION)
        sources, notes = score.plan_passes(inputs, allow_pending=True)
        assert not sources["u50-real-c1-L2"] and len(notes) == 2
        bad = score.Inputs.load(study.write_inputs(accept={"p1/u5000-real-l5-n20": "x"}))
        with pytest.raises(SystemExit, match="aren't pending"):
            score.plan_passes(bad)
    finally:
        study.write_inputs()


def test_withdrawn_areas_are_never_the_runs_root(study: Study) -> None:
    inputs = score.Inputs.load(study.inputs)
    with pytest.raises(SystemExit, match="withdrawn area"):
        score.plan_passes(replace(inputs, runs_root=study.root / "runs" / plan.S1_AREA))
    sources, _ = score.plan_passes(inputs)
    assert all(plan.S1_AREA not in str(s.predictions) for cell in sources.values() for s in cell)
    with_s1, _ = score.plan_passes(inputs, s1=True)
    swapped = [s for cell in with_s1.values() for s in cell if s.as_written]
    assert sorted(s.label for s in swapped) == sorted(plan.S1_PASSES)
    assert all(plan.S1_AREA in s.predictions.parts for s in swapped)


def test_a_registered_pass_out_of_bounds_stops_scoring(study: Study, no_predictions: None) -> None:
    key = "p2/u5000-real-c2-hybrid-L4"
    path = study.pass_dir(key) / "t05.json"
    saved = path.read_text()
    try:
        path.write_text(json.dumps(json.loads(saved) | {"status": "timeout"}))
        with pytest.raises(SystemExit, match=f"{key}: 1 timeout cases"):
            hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION)
        path.write_text(
            json.dumps(json.loads(saved) | {"tools": {"mcpToolCall": 3}, "searches": []})
        )
        with pytest.raises(SystemExit, match="tool bound \\(a\\)"):
            hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION)
    finally:
        path.write_text(saved)


def test_run_env_naming_another_commit_stops_scoring(study: Study, no_predictions: None) -> None:
    env = study.pass_dir("p1/u5000-hidden-l5-n50") / plan.RUN_ENV
    saved = env.read_text()
    try:
        env.write_text(saved.replace(plan.RERUN_COMMIT, "deadbeef1"))
        with pytest.raises(SystemExit, match="names commit deadbeef1"):
            hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION)
    finally:
        env.write_text(saved)


def test_an_exploratory_pass_out_of_bounds_is_dropped(study: Study) -> None:
    inputs = score.Inputs.load(study.inputs)
    cases = score.load_cases(inputs, plan.REGISTRATION)
    path = study.pass_dir("p1/u5000-real-l5-n50") / "t00.json"
    saved = path.read_text()
    try:
        path.write_text(json.dumps(json.loads(saved) | {"status": "timeout"}))
        sources, _ = score.plan_passes(inputs)
        _, notes = score.audit_passes(sources, cases, inputs)
        assert [s.label for s in sources["u5000-real-l5-n50"]] == ["p2/u5000-real-l5-n50"]
        assert any("dropped (exploratory)" in n for n in notes)
    finally:
        path.write_text(saved)


def test_run_env_naming_no_commit_is_scored_and_noted(study: Study) -> None:
    key = "p1/u5000-hidden-l5-n50"
    env = study.pass_dir(key) / plan.RUN_ENV
    saved = env.read_text()
    try:
        env.write_text(saved.replace(f"commit={plan.RERUN_COMMIT}\n", ""))
        passes = hreport.passes_table(
            hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION)
        )
        assert f"{plan.RERUN_COMMIT} (run.env names no commit)" in passes
        assert "Passes whose run.env names no commit" in passes
        assert passes.rstrip().endswith(key)
    finally:
        env.write_text(saved)


def test_run_env_keeps_only_whitelisted_keys(study: Study) -> None:
    env = runs.read_run_env(study.pass_dir("p1/u5000-hidden-l5-n50") / plan.RUN_ENV)
    assert "API_TOKEN" not in env and env["commit"] == plan.RERUN_COMMIT


# The dry run ----------------------------------------------------------------------------


def test_dry_run_reads_run_lists_and_opens_no_prediction_or_trace(
    study: Study, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    opened: list[str] = []
    real_open = io.open

    def watch(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", watch)
    monkeypatch.setattr("builtins.open", watch)
    keys = [k for k in plan.PASSES if not k.startswith("p2/")]
    first = study.run_list("test-p1", keys)
    second = study.run_list("test-p2", [k for k in plan.PASSES if k.startswith("p2/")])
    withdrawn = study.run_list("withdrawn", list(plan.S1_PASSES), plan.S1_AREA)
    out = study.root / "dry.json"
    assert (
        report.main(
            [
                "--dry-run",
                str(first),
                "--dry-run",
                str(second),
                "--dry-run",
                str(withdrawn),
                str(study.inputs),
                "--s1",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    touched = [
        p
        for p in opened
        if p.endswith(plan.PRED_FILE)
        or (p.endswith(".json") and "/runs/" in p)
        or p.endswith(".events.jsonl")
    ]
    assert touched == []
    record = json.loads(out.read_text())
    decisions = {(r["area"], r["pass"]): r["decision"] for r in record["lines"] if r["pass"]}
    assert sum(d == "scored" for d in decisions.values()) == 34
    assert sum(d.startswith("scored as exploratory") for d in decisions.values()) == 4
    assert all(decisions[(plan.S1_AREA, k)] == "read by S1 (on)" for k in plan.S1_PASSES)
    assert all(not r["problems"] for r in record["lines"] if r["pass"]), [
        r for r in record["lines"] if r["problems"]
    ]
    assert "Would score 34 registered passes" in text
    assert record["trace_dirs"] == ["{pass}"] and "puts its traces at `{pass}`" in text
    assert record["unlisted"] == []
    assert [Path(p["path"]) for p in record["s1"]["passes"]] == [
        study.pass_dir(k, plan.S1_AREA) for k in plan.S1_PASSES
    ]
    assert "API_TOKEN" not in text and "do-not-read" not in text


def test_dry_run_flags_pending_and_wrong_lines(study: Study) -> None:
    path = study.root / "odd.txt"
    good = run_line(study.root / "runs", plan.TEST_AREA, "p1/u5000-real-c2-hybrid-L4")
    path.write_text(
        "\n".join(
            [
                run_line(study.root / "runs", plan.TEST_AREA, PENDING[0]),
                good.replace("--search hybrid", "--search bm25f"),
                good.replace("--split test", "--split dev"),
                run_line(study.root / "runs", "withdrawn-stale", "p1/u5000-real-c2-hybrid-L4"),
                "echo nothing",
            ]
        )
        + "\n"
    )
    _, record = runs.dry_run([path], study.root / "runs", {}, False)
    decisions = [r["decision"] for r in record["lines"]]
    assert decisions[0].startswith("pending")
    assert decisions[1] == decisions[2] == "line differs from its cell; check first"
    assert decisions[3] == "withdrawn; never scored" and decisions[4].startswith("not a pass line")
    _, accepted = runs.dry_run([path], study.root / "runs", {PENDING[0]: "ok"}, False)
    assert accepted["lines"][0]["decision"] == "scored"


def test_dry_run_gives_the_trace_dir_and_checks_the_inputs_against_it(study: Study) -> None:
    path = study.root / "traces-sub.txt"
    keys = ["p1/u5000-real-c2-hybrid-L4", "p2/u5000-real-c2-hybrid-L4"]
    lines = [run_line(study.root / "runs", plan.TEST_AREA, k) for k in keys]
    path.write_text(
        "".join(
            line.replace(f"--trace-dir {d}", f"--trace-dir {d}/traces") + "\n"
            for line, d in zip(lines, (study.pass_dir(k) for k in keys), strict=True)
        )
    )
    text, record = runs.dry_run([path], study.root / "runs", {}, False)
    assert record["trace_dirs"] == ["{pass}/traces"]
    assert "puts its traces at `{pass}/traces`" in text
    assert [r["decision"] for r in record["lines"]] == ["scored", "scored"]
    _, wrong = runs.dry_run([path], study.root / "runs", {}, False, None, "{pass}")
    assert [r["decision"] for r in wrong["lines"]] == [
        "line differs from its cell; check first"
    ] * 2
    assert "INPUTS.json's trace_dir is {pass}" in wrong["lines"][0]["problems"][0]
    _, right = runs.dry_run([path], study.root / "runs", {}, False, None, "{pass}/traces")
    assert all(r["decision"] == "scored" and not r["problems"] for r in right["lines"])


# End to end on the synthetic study ------------------------------------------------------


def test_confirmatory_results_on_known_rankings(built: tuple[hreport.Report, Path]) -> None:
    result, out = built
    rows = {r["id"]: r for r in read_csv(out / "comparisons.csv") if r["group"] == "all"}
    h1 = rows["H1-real"]
    assert float(h1["diff"]) == 1.0 and float(h1["low"]) == 1.0 and h1["won"] == "59"
    assert float(h1["p_one_sided"]) == 0.0 and h1["reject"] == "True"
    assert "< 0.0005" in result.tables["confirmatory"]
    assert sum(r["family"] == "confirmatory" for r in rows.values()) == 6
    assert all(r["p_one_sided"] == "" for r in rows.values() if r["family"] != "confirmatory")
    assert not [s for s in result.skipped if "Holm" in s]


def test_agent_cells_pool_each_case_over_both_passes(built: tuple[hreport.Report, Path]) -> None:
    result, out = built
    row = cell_value(out, "u250-real-l5-n10", plan.PRIMARY)
    assert (float(row["mean"]), float(row["low"]), float(row["high"])) == (0.5, 0.5, 0.5)
    passes = [r for r in read_csv(out / "per_pass.csv") if r["cell"] == "u250-real-l5-n10"]
    assert {(r["pass"], r[plan.PRIMARY]) for r in passes} == {
        ("p1/u250-real-l5-n10", "1.0"),
        ("p2/u250-real-l5-n10", "0.0"),
    }
    assert result.results["u50-real-c1-L2"].sources == ["p1/u50-real-c1-L2", "p2/u50-real-c1-L2"]
    assert len(result.audits) == 38


def test_pooling_matches_the_registered_rule(
    study: Study, built: tuple[hreport.Report, Path]
) -> None:
    """The pre-rewrite test_report.py's per-case rule: §4's metrics, averaged over passes."""
    result, _ = built
    name = "u1000-hidden-c1-L4"
    spec = plan.CELLS[name]
    for i, case in enumerate(study.cases[HIDDEN]):
        runs_ = [
            case_metrics(case.gold_repos, p.ranking, plan.KS)
            for p in (study.predictions(spec, label)[i] for label in ("p1", "p2"))
        ]
        expected = {m: statistics.fmean(r[m] for r in runs_) for m in plan.METRICS}
        got = result.results[name].per_case[f"t{i:02d}"]
        assert {m: got[m] for m in plan.METRICS} == expected


def test_draws_are_averaged_and_censoring_is_reported(built: tuple[hreport.Report, Path]) -> None:
    result, out = built
    draws = result.results["u5000-real-bm25f-deps-random"]
    assert len(draws.sources) == 5
    assert all(
        draws.per_case[f"t{i:02d}"][plan.PRIMARY] == pytest.approx((4 - i % 5) / 5)
        for i in range(plan.N_CASES)
    )
    censored = cell_value(out, "u5000-real-scripted-search", f"{score.ABOVE_LAST}:median")
    assert censored["censored"] == "59" and censored["mean"] == "censored"
    assert (
        float(cell_value(out, "u5000-real-scripted-search", "LastRequiredRank")["mean"])
        == plan.LAST_RANK_CAP
    )
    first = cell_value(out, "u5000-real-c2-hybrid-L4", f"{score.ABOVE_LAST}:median")
    assert float(first["mean"]) == 0.0 and first["censored"] == "0"


def test_first_search_counts_per_run(built: tuple[hreport.Report, Path]) -> None:
    _, out = built
    count = {
        k: float(cell_value(out, "u5000-hidden-l5-n50", f"first-search:{k}")["mean"])
        for k in hreport.FIRST_SEARCH
    }
    per_pass = {"named": 15 + 14, "not-named": 15, "none": 15}
    assert count == {k: 2 * v for k, v in per_pass.items()}
    none = {
        k: float(cell_value(out, "u5000-hidden-l5-n50", f"first-search:{k}", "none")["mean"])
        for k in hreport.FIRST_SEARCH
    }
    assert sum(none.values()) == 2 * sum(1 for i in range(plan.N_CASES) if i % 3 == 0)
    with (out / "first_search.csv").open(encoding="utf-8") as handle:
        rows = [
            r
            for r in csv.DictReader(handle)
            if r["cell"] == "u5000-hidden-l5-n50" and r["visibility"] == "none"
        ]
    assert Counter(r["first_search"] for r in rows) == {k: v for k, v in none.items() if v}


def test_owner_references_and_none_group(built: tuple[hreport.Report, Path], study: Study) -> None:
    result, out = built
    refs = result.refs[(5000, REAL)]
    for i, case in enumerate(study.cases[REAL]):
        n_owner = len(case.gold) + 2 + same_owner(i)
        assert refs[case.case_id] == pytest.approx(score.owner_reference(n_owner, len(case.gold)))
    none = cell_value(out, "u5000-real-c2-hybrid-L4", plan.PRIMARY, "none")
    assert int(none["n"]) == sum(1 for i in range(plan.N_CASES) if i % 3 == 0)
    within = [r for r in read_csv(out / "comparisons.csv") if r["group"] == "none"]
    assert len(within) == 6 and all(r["p_one_sided"] == "" for r in within)
    assert "H1-H3 within the `none` group" in result.tables["none-group"]


def test_change_memory_and_reviewed_labels(built: tuple[hreport.Report, Path]) -> None:
    result, _ = built
    memory = result.tables["change-memory"]
    assert "25 cases before 2026-03-01, 34 after, 0 undated" in memory and "differ" not in memory
    reviewed = result.tables["reviewed"]
    assert "H1-H3 on reviewed labels" in reviewed
    assert (
        result.results["u5000-real-bm25f"].per_case["t02"][f"{score.REVIEWED}{plan.PRIMARY}"] == 0.0
    )


def test_outputs_are_written(built: tuple[hreport.Report, Path]) -> None:
    result, out = built
    for name in (
        "report.md",
        "cells.csv",
        "per_case.csv",
        "per_pass.csv",
        "first_search.csv",
        "misses.csv",
        "audits.csv",
        "comparisons.csv",
        "results.json",
        "figures/forest.svg",
        "figures/hit-vs-cr.svg",
    ):
        assert (out / name).is_file(), name
    assert {p.stem for p in (out / "tables").glob("*.md")} == set(result.tables)
    record = json.loads((out / "results.json").read_text())
    assert (
        record["cases"] == 59
        and record["ecosystems"] == 30
        and record["registration"] == plan.REGISTRATION
    )
    assert set(record["choices"]) == set(plan.CHOICES)
    assert (out / "frontier").is_dir() and record["frontier"]
    text = (out / "report.md").read_text()
    assert "S1 is off (the default)" in text
    assert not any(token in text for token in (" nan", "nan ", "[nan", "inf]", " inf "))
    assert "kept; no run.env by design" in result.tables["passes"]
    misses = read_csv(out / "misses.csv")
    assert all(r["status"] == "ok" for r in misses if r["cell"] == "u250-real-l5-n10")


def test_s1_is_off_by_default_and_minimal_when_on(
    study: Study, built: tuple[hreport.Report, Path]
) -> None:
    base, _ = built
    assert base.s1 is None
    with_s1 = hreport.build(score.Inputs.load(study.inputs), plan.REGISTRATION, s1=True)
    s1 = with_s1.s1
    assert sorted(a.key for a in s1["audits"]) == sorted(plan.S1_PASSES)
    assert all(len(a.timeouts) == 3 and a.traces == plan.N_CASES for a in s1["audits"])
    touched = {k.split("/", 1)[1] for k in plan.S1_PASSES}
    assert set(s1["results"]) == touched
    swapped = s1["results"]["u5000-real-l5-n20"]
    assert swapped.sources == ["p1/u5000-real-l5-n20", "p2/u5000-real-l5-n20"]
    p2 = swapped.per_source[1]
    assert all(p2[f"t{i:02d}"][plan.PRIMARY] == 0.0 for i in range(plan.N_CASES))
    assert p2["t58"]["LastRequiredRank"] == plan.LAST_RANK_CAP
    assert len(s1["diffs"]) == 6
    assert (
        with_s1.results["u5000-real-l5-n20"].per_case == base.results["u5000-real-l5-n20"].per_case
    )


def test_cli_checks_the_registration_then_refuses_dirty_code(
    study: Study,
    tmp_path: Path,
    registered: list[str | None],
    monkeypatch: pytest.MonkeyPatch,
    no_predictions: None,
) -> None:
    with pytest.raises(SystemExit, match="--registered"):
        report.main([str(study.inputs), "--out", str(tmp_path / "r")])
    monkeypatch.setattr(
        report,
        "code_version",
        lambda repo=None: {"commit": "a", "dirty": True, "changed": [" M scripts/x.py"]},
    )
    with pytest.raises(SystemExit, match="differs from its commit"):
        report.main([str(study.inputs), "--registered", "abc1234", "--out", str(tmp_path / "r")])
    assert registered == [None, "abc1234"]
    assert not (tmp_path / "r").exists()


def test_cli_needs_costs_and_merge_dates(
    study: Study, tmp_path: Path, no_predictions: None
) -> None:
    try:
        for dropped in ({"costs": None}, {"merge_dates": None}):
            study.write_inputs(**dropped)
            with pytest.raises(SystemExit, match=f"needs {next(iter(dropped))}"):
                report.main(
                    [str(study.inputs), "--registered", "abc1234", "--out", str(tmp_path / "r")]
                )
    finally:
        study.write_inputs()
    assert not (tmp_path / "r").exists()


def test_reviewed_labels_absent_says_why(study: Study) -> None:
    result = hreport.build(score.Inputs.load(study.write_inputs(reviewed=None)), plan.REGISTRATION)
    study.write_inputs()
    assert hreport.reviewed_table(result).startswith("Not computed: no adjudicated test labels")
    assert all(
        f"{score.REVIEWED}{plan.PRIMARY}" not in v
        for v in result.results["u5000-real-bm25f"].per_case.values()
    )


def test_cli_scores_the_synthetic_study(
    study: Study, tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    out = tmp_path / "report"
    assert report.main([str(study.inputs), "--registered", "abc1234", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "| H1-real |" in printed and "reject H0" in printed
    assert (out / "report.md").is_file()
