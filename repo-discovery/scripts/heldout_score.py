"""Score the held-out test passes: PREREGISTRATION.md §4, with addendum items 4, 12 and
14 to 17 of entry 7.

Every cell is read one ranking file at a time. Each ranking becomes its per-case values
at once (§4's metrics, item 17's set quality, within-owner rescoring and top-10 fill,
and the reviewed-label rescoring), and is then dropped, so a U10000 run fits in memory.
An agent cell's per-case value is the mean over its accepted passes (item 15), and
``bm25f-deps-random``'s the mean over its draws. Every interval is §4's ecosystem-cluster
bootstrap, on the real-name ecosystems, so every cell and comparison shares one set of
resamples.

Before any prediction is read, every pass is checked against the registry
(``heldout_plan.PASSES``): a pending pass stops scoring unless the inputs accept it, a
withdrawn pass is never read, and each pass's traces must meet item 4's and item 1's
bounds.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from heldout_plan import (
    AGENT_CELLS,
    ALPHA,
    CELLS,
    COMPARISONS,
    KS,
    LAST_RANK_CAP,
    METRICS,
    N_BOOT,
    N_CASES,
    N_ECOSYSTEMS,
    NAMES,
    PASSES,
    PRED_FILE,
    S1_AREA,
    S1_PASSES,
    SEED,
    TEST_AREA,
    TOOLS,
    CellSpec,
    Comparison,
    RegisteredPass,
)
from heldout_runs import PassAudit, audit_pass, pass_dir, trace_dir
from v5_dev_report import PRICES, case_cost
from v5_export_cases import fetch
from v5_memory_report import _rate

from repo_discovery import selection
from repo_discovery.cases import Case, read_cases, repo_key
from repo_discovery.contract import raw_rows, resolve_universe
from repo_discovery.metrics import case_metrics
from repo_discovery.predictions import read_predictions
from repo_discovery.rankers.cursor_agent import _PATH_ARGS
from repo_discovery.split import run_cases
from repo_discovery.stats import cluster_replicates, holm, percentile_interval

MODEL = "composer-2.5"
GIVEN = "CompleteRecall@|G|"
ABOVE_LAST = "NonTargetsAboveLast"
OWNER = "Owner:"
REVIEWED = "Reviewed:"
TOP10 = "Top10:"
# Item 17's universe layers, by (role, source).
LAYERS = {
    ("ecosystem", "wideswe"): "wideswe",
    ("ecosystem", "same_owner"): "same_owner",
    ("distractor", "frame"): "frame",
}
TOP10_KEYS = tuple(
    f"{TOP10}{k}"
    for k in (
        "non-targets",
        "wideswe",
        "same_owner",
        "frame",
        "other-layer",
        "target-owner",
        "other-owner",
    )
)
SEARCH_KINDS = ("grep", "ripgrep", "glob")
OWNER_METRICS = (*METRICS, GIVEN)
REVIEWED_METRICS = METRICS
# Static rankers whose index the frontier names explicitly (as in the dev selection).
FRONTIER_INDEX = {
    "random": [],
    "bm25f-deps": ["bm25f@L4"],
    "bm25f-deps-random": ["bm25f@L4"],
    "contract-joins": ["bm25f@L4"],
    "bm25f-contract-text": ["bm25f@L4"],
    "scripted-search": ["bm25f@L4"],
}
_OPEN = re.compile(r"(bm25f|scripted)-open(\d+)")


class ScoringError(SystemExit):
    """Scoring can't go on as registered; nothing has been scored."""


# Inputs -------------------------------------------------------------------------------


@dataclass
class Inputs:
    """Where everything is. Paths are relative to the inputs file. See TEST_ANALYSIS.md."""

    runs_root: Path
    trace_dir: str
    cases: dict[str, Path]
    static: str
    case_map: Path | None = None
    static_draws: dict = field(default_factory=dict)
    universes: dict[str, str] = field(default_factory=dict)
    accept: dict[str, str] = field(default_factory=dict)
    merge_dates: Path | None = None
    reviewed: dict[str, Path] = field(default_factory=dict)
    costs: Path | None = None
    run_env_commit_key: str | None = None

    @classmethod
    def load(cls, path: Path) -> Inputs:
        raw = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent

        def p(value: str | None) -> Path | None:
            return None if value is None else selection.resolve(value, base)

        def t(value: str) -> str:
            return str(selection.resolve(value, base))

        unknown = set(raw) - {f for f in cls.__dataclass_fields__}
        if unknown:
            raise ScoringError(f"{path}: unknown inputs {sorted(unknown)}")
        draws = dict(raw.get("static_draws") or {})
        if draws:
            draws["template"] = t(draws["template"])
        return cls(
            runs_root=p(raw["runs_root"]),  # type: ignore[arg-type]
            trace_dir=raw.get("trace_dir", "{pass}"),
            cases={k: p(v) for k, v in raw["cases"].items()},  # type: ignore[misc]
            static=t(raw["static"]),
            case_map=p(raw.get("case_map")),
            static_draws=draws,
            universes={k: t(v) for k, v in (raw.get("universes") or {}).items()},
            accept=dict(raw.get("accept") or {}),
            merge_dates=p(raw.get("merge_dates")),
            reviewed={k: p(v) for k, v in (raw.get("reviewed") or {}).items()},  # type: ignore[misc]
            costs=p(raw.get("costs")),
            run_env_commit_key=raw.get("run_env_commit_key"),
        )


# Cases --------------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseSet:
    """One name condition's test cases, keyed by their own IDs, with the real-name ID,
    ecosystem and visibility label of each."""

    names: str
    cases: Mapping[str, Case]
    real: Mapping[str, str]
    ecosystem: Mapping[str, str]
    visibility: Mapping[str, str | None]

    @property
    def ids(self) -> list[str]:
        """Real-name case IDs, in a fixed order."""
        return sorted(self.real.values())


def load_cases(inputs: Inputs, registered: str) -> dict[str, CaseSet]:
    real_cases = run_cases(read_cases(inputs.cases["real"]), "test", registered)
    if len(real_cases) != N_CASES or len({c.ecosystem for c in real_cases}) != N_ECOSYSTEMS:
        raise ScoringError(
            f"{inputs.cases['real']}: {len(real_cases)} test cases in "
            f"{len({c.ecosystem for c in real_cases})} ecosystems, not {N_CASES} in {N_ECOSYSTEMS}"
        )
    ecosystem = {c.case_id: c.ecosystem for c in real_cases}
    out = {
        "real": CaseSet(
            "real",
            {c.case_id: c for c in real_cases},
            {c.case_id: c.case_id for c in real_cases},
            ecosystem,
            {c.case_id: c.scope_visibility for c in real_cases},
        )
    }
    if "hidden" in inputs.cases:
        if inputs.case_map is None:
            raise ScoringError("hidden-name cases need a case_map")
        to_hidden = json.loads(inputs.case_map.read_text(encoding="utf-8"))["cases"]
        to_real = {h: r for r, h in to_hidden.items()}
        hidden = run_cases(read_cases(inputs.cases["hidden"]), "test", registered)
        real = {c.case_id: to_real.get(c.case_id) for c in hidden}
        if sorted(r for r in real.values() if r) != sorted(ecosystem) or None in real.values():
            raise ScoringError("hidden-name test cases don't map one to one onto the real ones")
        out["hidden"] = CaseSet(
            "hidden",
            {c.case_id: c for c in hidden},
            real,  # type: ignore[arg-type]
            ecosystem,
            {real[c.case_id]: c.scope_visibility for c in hidden},
        )
    return out


def load_reviewed(inputs: Inputs, cases: Mapping[str, CaseSet]) -> dict[str, dict[str, tuple]]:
    """Per name condition, own case ID to its reviewed gold (``adjudicate.py apply``)."""
    out = {}
    for names, path in inputs.reviewed.items():
        own = {c.case_id: c.gold_repos for c in read_cases(path)}
        unknown = set(own) - set(cases[names].cases)
        if unknown:
            raise ScoringError(f"{path}: {len(unknown)} cases that aren't test cases")
        out[names] = own
    return out


# Universes ----------------------------------------------------------------------------


def owner(key: str) -> str:
    """Item 17: the part of a repository's name before ``/``."""
    return key.split("/", 1)[0]


@dataclass(frozen=True)
class CaseUniverse:
    """What item 17 needs of one case's universe: each candidate's layer, and the owner
    set O (every candidate whose owner is a target owner, the targets included)."""

    layer: Mapping[str, str]
    owner_set: frozenset[str]
    reference: float


def owner_reference(n_owner: int, n_gold: int) -> float:
    """Item 17 (i): the exact expected CR@10 with O first in a uniformly random order."""
    return 1.0 if n_owner <= 10 else math.comb(10, n_gold) / math.comb(n_owner, n_gold)


def case_universe(root: Path, case: Case) -> CaseUniverse:
    rows = raw_rows(resolve_universe(root, case.case_id))
    layer = {repo_key(r["repo"]): LAYERS.get((r["role"], r.get("source")), "other") for r in rows}
    gold = {repo_key(g) for g in case.gold_repos}
    targets = {owner(g) for g in gold}
    owners = frozenset(k for k in layer if owner(k) in targets) | gold
    return CaseUniverse(layer, owners, owner_reference(len(owners), len(gold)))


def universe_root(inputs: Inputs, names: str, size: int) -> Path | None:
    template = inputs.universes.get(names)
    return None if template is None else Path(template.replace("{size}", str(size)))


# Per-ranking values -------------------------------------------------------------------


def complete_at_given(gold: Sequence[str], ranking: Sequence[str]) -> float:
    """Item 17's CR@|G|: 1 when the first |G| ranks are exactly G."""
    targets = {repo_key(g) for g in gold}
    return float({repo_key(r) for r in ranking[: len(targets)]} == targets)


def ranking_values(
    gold: Sequence[str],
    ranking: Sequence[str],
    universe: CaseUniverse | None = None,
    reviewed: Sequence[str] | None = None,
) -> dict[str, float]:
    """One ranking's per-case values: §4's metrics at ``KS``; item 17's CR@|G|,
    non-targets above the last target (inf when censored) and, with the universe, the
    top-10 fill and the within-owner rescoring; and §4's metrics on reviewed gold. Ranks
    are positions in the ranking as saved, as in ``case_metrics``."""
    values = case_metrics(gold, ranking, KS)
    keys = [repo_key(r) for r in ranking]
    targets = {repo_key(g) for g in gold}
    values[GIVEN] = complete_at_given(gold, ranking)
    last = values["LastRequiredRank"]
    values[ABOVE_LAST] = math.inf if last >= LAST_RANK_CAP else last - len(targets)
    if universe is not None:
        top = [k for k in keys[:10] if k not in targets]
        target_owners = {owner(t) for t in targets}
        fill = Counter(universe.layer.get(k, "other") for k in top)
        values[f"{TOP10}non-targets"] = float(len(top))
        for layer in ("wideswe", "same_owner", "frame"):
            values[f"{TOP10}{layer}"] = float(fill[layer])
        values[f"{TOP10}other-layer"] = float(len(top) - sum(fill[x] for x in LAYERS.values()))
        named = sum(owner(k) in target_owners for k in top)
        values[f"{TOP10}target-owner"] = float(named)
        values[f"{TOP10}other-owner"] = float(len(top) - named)
        within = [k for k in keys if k in universe.owner_set]
        rescored = case_metrics(gold, within, KS)
        rescored[GIVEN] = complete_at_given(gold, within)
        values |= {f"{OWNER}{m}": rescored[m] for m in OWNER_METRICS}
    if reviewed is not None:
        again = case_metrics(reviewed, ranking, KS)
        values |= {f"{REVIEWED}{m}": again[m] for m in REVIEWED_METRICS}
    return values


def target_ranks(gold: Sequence[str], ranking: Sequence[str]) -> str:
    position: dict[str, int] = {}
    for rank, repo in enumerate(ranking, start=1):
        position.setdefault(repo_key(repo), rank)
    return ",".join(str(position.get(repo_key(g), "-")) for g in gold)


# First search (item 17) ---------------------------------------------------------------


def _strings(value: object) -> Iterable[str]:
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str):
            yield item


def search_string(tool_call: Mapping) -> str | None:
    """The search string of a grep, glob or ``search_repos`` call, else None."""
    kind = next((k for k in tool_call if k.endswith("ToolCall")), None)
    if kind is None:
        return None
    args = tool_call[kind].get("args") or {}
    stem = kind[: -len("ToolCall")].lower()
    if stem in SEARCH_KINDS:
        return " ".join(s for k, v in args.items() if k not in _PATH_ARGS for s in _strings(v))
    if stem == "mcp" and (
        args.get("toolName") == TOOLS["c2"] or str(args.get("name", "")).endswith(TOOLS["c2"])
    ):
        return " ".join(_strings((args.get("args") or {}).get("query")))
    return None


def names_owner(text: str, owners: Iterable[str]) -> bool:
    """Whether ``text`` holds a target owner as a whole token, case-insensitively: no
    letter, digit or hyphen directly before or after it."""
    return any(
        re.search(rf"(?<![^\W_])(?<!-){re.escape(o)}(?![^\W_])(?!-)", text, re.IGNORECASE)
        for o in owners
    )


def first_search(events: Path, owners: Iterable[str]) -> str:
    """``named``, ``not-named`` or ``none``: whether the case's first grep, glob or
    ``search_repos`` call names a target owner."""
    if not events.is_file():
        return "none"
    with events.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") != "tool_call" or event.get("subtype") != "started":
                continue
            text = search_string(event.get("tool_call") or {})
            if text is not None:
                return "named" if names_owner(text, owners) else "not-named"
    return "none"


# Passes -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Source:
    """One ranking file of a cell: an agent pass or a static run (or draw)."""

    label: str
    predictions: Path
    traces: Path | None = None
    registered: RegisteredPass | None = None
    as_written: bool = False


def plan_passes(
    inputs: Inputs, allow_pending: bool = False, s1: bool = False
) -> tuple[dict[str, list[Source]], list[str]]:
    """Each agent cell's accepted passes, and notes on what was left out and why. Only
    ``runs_root/test/`` is read; S1 swaps in its five passes from ``withdrawn-concurrency``."""
    if any(part.startswith("withdrawn-") for part in inputs.runs_root.resolve().parts):
        raise ScoringError(f"runs_root {inputs.runs_root} is a withdrawn area")
    unknown = sorted(set(inputs.accept) - {k for k, p in PASSES.items() if p.status == "pending"})
    if unknown:
        raise ScoringError(f"the inputs accept passes that aren't pending: {', '.join(unknown)}")
    pending = [k for k, p in PASSES.items() if p.status == "pending" and k not in inputs.accept]
    if pending and not allow_pending:
        raise ScoringError(
            f"{len(pending)} registered passes are pending (item 13): {', '.join(pending)}. "
            "Accept them in the inputs once they pass their bound, or pass --allow-pending."
        )
    notes, sources = [], {name: [] for name in AGENT_CELLS}
    for key, registered in PASSES.items():
        if key in pending:
            notes.append(f"{key} left out: pending (--allow-pending)")
            continue
        area, as_written = TEST_AREA, False
        if s1 and key in S1_PASSES:
            area, as_written = S1_AREA, True
        directory = pass_dir(inputs.runs_root, key, area)
        resolved = directory.resolve()
        if area == TEST_AREA and any(p.startswith("withdrawn-") for p in resolved.parts):
            raise ScoringError(f"{directory} resolves into a withdrawn area: {resolved}")
        sources[registered.cell].append(
            Source(
                key,
                directory / PRED_FILE,
                trace_dir(directory, inputs.trace_dir),
                registered,
                as_written,
            )
        )
    return sources, notes


def audit_passes(
    sources: Mapping[str, list[Source]], cases: Mapping[str, CaseSet], inputs: Inputs
) -> tuple[list[PassAudit], list[str]]:
    """Every pass against its bounds, from traces only. A failing registered pass stops
    scoring; a failing exploratory one is dropped with a note. S1's passes are scored as
    written, so their audits are reported, not enforced."""
    audits, failures, notes = [], [], []
    for cell, cell_sources in sources.items():
        spec = CELLS[cell]
        for source in list(cell_sources):
            audit = audit_pass(
                spec,
                source.registered,
                source.predictions.parent,
                source.traces,  # type: ignore[arg-type]
                list(cases[spec.names].cases),
                inputs.run_env_commit_key,
            )
            if source.registered is not None and source.registered.kept:
                kept = [p for p in audit.problems if "provider-error" in p]
                audit.problems = [p for p in audit.problems if p not in kept]
                if kept:
                    notes.append(
                        f"{source.label}: {kept[0]}; a kept pass met entry 7's rule, item 4's "
                        "rerun bound doesn't apply"
                    )
            audits.append(audit)
            if not audit.problems or source.as_written:
                continue
            if spec.registered:
                failures.append(f"{source.label}: {'; '.join(audit.problems)}")
            else:
                cell_sources.remove(source)
                notes.append(f"{source.label} dropped (exploratory): {'; '.join(audit.problems)}")
    if failures:
        raise ScoringError("passes fail their bounds:\n  " + "\n  ".join(failures))
    return audits, notes


def static_sources(spec: CellSpec, inputs: Inputs) -> list[Source]:
    if spec.draws == 1:
        return [Source(spec.name, Path(inputs.static.replace("{cell}", spec.name)))]
    draws = inputs.static_draws
    labels = [str(d) for d in draws.get("draws", ())]
    if len(labels) != spec.draws:
        raise ScoringError(f"{spec.name} needs {spec.draws} draws in static_draws.draws")
    template = draws["template"].replace("{cell}", spec.name)
    return [Source(f"{spec.name}#{d}", Path(template.replace("{draw}", d))) for d in labels]


# Scoring a cell -----------------------------------------------------------------------


@dataclass
class CellResult:
    spec: CellSpec
    sources: list[str]
    per_case: dict[str, dict[str, float]]
    per_source: list[dict[str, dict[str, float]]]
    costs: dict[str, dict[str, float]] = field(default_factory=dict)
    first_search: list[tuple[str, str, str]] = field(default_factory=list)
    misses: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _rankings(source: Source, spec: CellSpec, case_set: CaseSet) -> dict[str, list[str]]:
    if not source.predictions.is_file():
        raise ScoringError(f"{source.label}: no predictions at {source.predictions}")
    out = {}
    for p in read_predictions(source.predictions):
        if p.case_id not in case_set.cases:
            raise ScoringError(
                f"{source.label}: {p.case_id} isn't a {case_set.names}-name test case"
            )
        if p.universe_size and p.universe_size != spec.size:
            raise ScoringError(f"{source.label}: universe size {p.universe_size}, not {spec.size}")
        out[p.case_id] = p.ranking
    missing = sorted(set(case_set.cases) - set(out))
    if missing and not source.as_written:
        raise ScoringError(f"{source.label}: {len(missing)} test cases have no prediction")
    for case_id in missing:
        out[case_id] = []
    return out


def _agent_case(
    trace: Mapping, events: Path, case: Case, rate: float, root: Path | None, level_open: bool
) -> tuple[dict[str, float], str]:
    usd, tokens, _ = case_cost(dict(trace), PRICES[MODEL], rate)
    costs = {"usd": usd, "tokens": float(tokens), "seconds": float(trace.get("seconds") or 0)}
    if level_open and root is not None:
        requests, size = fetch(root, case.case_id, list(trace.get("opened") or []), "L4")
        costs |= {"fetch_requests": float(requests), "fetch_bytes": float(size)}
    targets = {owner(repo_key(g)) for g in case.gold_repos}
    return costs, first_search(events, targets)


def score_cell(
    spec: CellSpec,
    sources: Sequence[Source],
    case_set: CaseSet,
    universes: Mapping[str, CaseUniverse] | None,
    reviewed: Mapping[str, tuple] | None,
    root: Path | None,
    read_traces: bool = True,
) -> CellResult:
    """Stream each source's rankings into per-case values, then pool them per case."""
    result = CellResult(spec, [s.label for s in sources], {}, [])
    if not sources:
        result.notes.append("no pass to score")
        return result
    costs: list[dict[str, dict[str, float]]] = []
    agent = spec.agent and read_traces
    for source in sources:
        rankings = _rankings(source, spec, case_set)
        traces = {}
        if agent:
            traces = {
                i: json.loads((source.traces / f"{i}.json").read_text(encoding="utf-8"))  # type: ignore[operator]
                for i in case_set.cases
            }
            rate = _rate(list(traces.values()), PRICES[MODEL])[0]
        values, spent = {}, {}
        for own, case in case_set.cases.items():
            real = case_set.real[own]
            ranking = rankings[own]
            universe = universes.get(own) if universes else None
            gold_r = reviewed.get(own) if reviewed else None
            values[real] = ranking_values(case.gold_repos, ranking, universe, gold_r)
            if agent:
                trace = traces[own]
                spent[real], search = _agent_case(
                    trace,
                    source.traces / f"{own}.events.jsonl",  # type: ignore[operator]
                    case,
                    rate,
                    root,
                    spec.method == "l5",
                )
                result.first_search.append((real, source.label, search))
            elif not spec.agent:
                match = _OPEN.fullmatch(spec.method)
                if match and int(match[2]) and root is not None:
                    requests, size = fetch(root, own, list(ranking[: int(match[2])]), "L4")
                    spent[real] = {"fetch_requests": float(requests), "fetch_bytes": float(size)}
            if values[real]["CompleteRecall@10"] < 1:
                ranks = target_ranks(case.gold_repos, ranking)
                miss = {"case_id": real, "source": source.label, "target_ranks": ranks}
                if agent:
                    returned = int(traces[own].get("returned") or 0)
                    miss |= {
                        "status": traces[own].get("status"),
                        "returned": returned,
                        "outside_own_list": sum(
                            r == "-" or int(r) > returned for r in ranks.split(",")
                        ),
                    }
                result.misses.append(miss)
        result.per_source.append(values)
        costs.append(spent)
        del rankings, traces
    result.per_case = pool(result.per_source)
    if any(costs):
        result.costs = pool(costs)
    return result


def pool(parts: Sequence[Mapping[str, Mapping[str, float]]]) -> dict[str, dict[str, float]]:
    """Per case and key, the mean over the parts that have it (item 15)."""
    out: dict[str, dict[str, float]] = {}
    for case_id in parts[0]:
        keys = set.intersection(*(set(p[case_id]) for p in parts))
        out[case_id] = {k: statistics.fmean(p[case_id][k] for p in parts) for k in sorted(keys)}
    return out


def score_all(
    inputs: Inputs,
    cases: Mapping[str, CaseSet],
    sources: Mapping[str, list[Source]],
    cells: Iterable[CellSpec] = CELLS.values(),
) -> tuple[dict[str, CellResult], dict[tuple[int, str], dict[str, float]]]:
    """Every cell, one (names, size) group at a time, holding one group's universes; and
    item 17 (i) per group: each case's expected CR@10 with O first in random order."""
    reviewed = load_reviewed(inputs, cases)
    results, refs = {}, {}
    order = sorted(cells, key=lambda s: (NAMES.index(s.names), s.size, s.name))
    group_key, universes = None, None
    for spec in order:
        if spec.names not in cases:
            continue
        case_set = cases[spec.names]
        root = universe_root(inputs, spec.names, spec.size)
        if (spec.names, spec.size) != group_key:
            group_key = (spec.names, spec.size)
            universes = None
            if root is not None:
                universes = {i: case_universe(root, c) for i, c in case_set.cases.items()}
                refs[(spec.size, spec.names)] = {
                    case_set.real[i]: u.reference for i, u in universes.items()
                }
        cell_sources = sources.get(spec.name) if spec.agent else static_sources(spec, inputs)
        results[spec.name] = score_cell(
            spec, cell_sources or [], case_set, universes, reviewed.get(spec.names), root
        )
    return results, refs


# Summaries ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float
    n: int

    def text(self, digits: int = 3, sign: bool = False) -> str:
        f = f"{{:{'+' if sign else ''}.{digits}f}}"
        if math.isnan(self.mean):
            return "—"
        return f"{f.format(self.mean)} [{f.format(self.low)}, {f.format(self.high)}]"

    def row(self, digits: int) -> list[float]:
        return [round(self.mean, digits), round(self.low, digits), round(self.high, digits)]


def estimate(
    values: Mapping[str, float], ids: Sequence[str], ecosystem: Mapping[str, str]
) -> Interval:
    """The mean over ``ids`` with §4's interval: whole test ecosystems resampled."""
    if not ids:
        return Interval(math.nan, math.nan, math.nan, 0)
    arr = [values[i] for i in ids]
    reps = cluster_replicates(arr, [ecosystem[i] for i in ids], N_BOOT, SEED)
    low, high = percentile_interval(reps, ALPHA)
    return Interval(float(np.mean(arr)), low, high, len(ids))


@dataclass(frozen=True)
class Difference:
    comparison: Comparison
    interval: Interval
    p_one_sided: float | None
    won: int
    lost: int
    tied: int
    p_holm: float | None = None
    reject: bool | None = None


def compare(
    comparison: Comparison,
    results: Mapping[str, CellResult],
    ecosystem: Mapping[str, str],
    ids: Sequence[str] | None = None,
    with_p: bool = False,
    metric: str | None = None,
) -> Difference | None:
    """A paired per-case difference ``a - b``, on the same resamples as every cell."""
    a, b = results.get(comparison.a), results.get(comparison.b)
    if a is None or b is None or not a.per_case or not b.per_case:
        return None
    metric = metric or comparison.metric
    if sorted(a.per_case) != sorted(b.per_case):
        raise ScoringError(f"{comparison.a} and {comparison.b} cover different cases")
    ids = sorted(a.per_case) if ids is None else list(ids)
    diffs = {i: a.per_case[i][metric] - b.per_case[i][metric] for i in ids}
    interval = estimate(diffs, ids, ecosystem)
    p = None
    if with_p:
        reps = cluster_replicates(
            [diffs[i] for i in ids], [ecosystem[i] for i in ids], N_BOOT, SEED
        )
        p = float((reps <= 0).mean())
    d = np.array([diffs[i] for i in ids])
    return Difference(
        comparison, interval, p, int((d > 0).sum()), int((d < 0).sum()), int((d == 0).sum())
    )


def comparisons(
    results: Mapping[str, CellResult], ecosystem: Mapping[str, str]
) -> tuple[list[Difference], list[str]]:
    """§4's comparisons; only the confirmatory family gets p-values and Holm."""
    rows, skipped = [], []
    for c in COMPARISONS:
        row = compare(c, results, ecosystem, with_p=c.family == "confirmatory")
        if row is None:
            skipped.append(f"{c.id}: {c.a} or {c.b} has no scored pass")
        else:
            rows.append(row)
    confirmatory = {
        r.comparison.id: r.p_one_sided for r in rows if r.comparison.family == "confirmatory"
    }
    if len(confirmatory) != 6:
        skipped.append(f"Holm family has {len(confirmatory)} of 6 tests")
    adjusted = holm(confirmatory, ALPHA)  # type: ignore[arg-type]
    out = []
    for r in rows:
        if r.comparison.id in adjusted:
            p_holm, reject = adjusted[r.comparison.id]
            r = replace(r, p_holm=p_holm, reject=reject)
        out.append(r)
    return out, skipped


def stability(
    results: Mapping[str, CellResult], ecosystem: Mapping[str, str], metric: str
) -> list[dict]:
    """§4's agent stability: each pass, the pooled mean, and pass 2 minus pass 1."""
    rows = []
    for name, r in results.items():
        if not r.spec.agent or not r.per_source:
            continue
        ids = sorted(r.per_case)
        passes = [estimate({i: p[i][metric] for i in ids}, ids, ecosystem) for p in r.per_source]
        row = {
            "cell": name,
            "role": r.spec.role,
            "metric": metric,
            "passes": r.sources,
            "per_pass": passes,
            "pooled": estimate({i: r.per_case[i][metric] for i in ids}, ids, ecosystem),
            "p2_minus_p1": None,
        }
        if len(r.per_source) == 2:
            p1, p2 = r.per_source
            row["p2_minus_p1"] = estimate(
                {i: p2[i][metric] - p1[i][metric] for i in ids}, ids, ecosystem
            )
        rows.append(row)
    return rows


def gap(results: Mapping[str, CellResult], ecosystem: Mapping[str, str]) -> dict[str, Interval]:
    """§4: Hit@10 against CR@10, per cell, as the paired per-case gap."""
    out = {}
    for name, r in results.items():
        if r.per_case:
            ids = sorted(r.per_case)
            diffs = {i: r.per_case[i]["Hit@10"] - r.per_case[i]["CompleteRecall@10"] for i in ids}
            out[name] = estimate(diffs, ids, ecosystem)
    return out


# Frontier -----------------------------------------------------------------------------


def selection_cell(spec: CellSpec) -> selection.Cell:
    salt = "test" if spec.names == "hidden" else None
    base = {"size": spec.size, "names": spec.names, "salt": salt}
    if spec.method == "c1":
        return selection.Cell.from_dict(
            {**base, "method": "c1", "shape": "none", "level": spec.level}
        )
    if spec.method == "c2":
        return selection.Cell.from_dict(
            {**base, "method": "c2", "shape": spec.search, "level": "L4", "tool": TOOLS["c2"]}
        )
    if spec.method == "l5":
        return selection.Cell.from_dict(
            {
                **base,
                "method": "l5",
                "shape": "none",
                "level": "L0",
                "budget": spec.budget,
                "opens": "L4",
            }
        )
    match = _OPEN.fullmatch(spec.method)
    if match:
        return selection.Cell.from_dict(
            {
                **base,
                "method": "static-open",
                "shape": match[1],
                "level": "L0",
                "budget": int(match[2]),
                "opens": "L4",
            }
        )
    return selection.Cell.from_dict(
        {**base, "method": "static", "shape": spec.method, "level": spec.level}
    )


def frontier_entry(spec: CellSpec) -> dict:
    if spec.method in FRONTIER_INDEX:
        return {"index": FRONTIER_INDEX[spec.method]}
    if spec.method.startswith("scripted-open"):
        return {"index": ["bm25f@L0"]}
    return {}


def frontier_rows(
    results: Mapping[str, CellResult], ecosystem: Mapping[str, str], tables: selection.CostTables
) -> list[selection.Row]:
    """One frontier row per registered cell, with the dev selection's cost rules."""
    rows = []
    for name, r in results.items():
        if not r.spec.registered or not r.per_case:
            continue
        ids = sorted(r.per_case)
        quality = {}
        for metric in selection.METRICS:
            e = estimate({i: r.per_case[i][metric] for i in ids}, ids, ecosystem)
            quality[metric] = selection.Value(e.mean, e.low, e.high)
        cell = selection_cell(r.spec)
        costs, notes = selection.cell_costs(cell, frontier_entry(r.spec), tables, r.costs or None)
        rows.append(
            selection.Row(
                cell=cell,
                quality=quality,
                backing="predictions",
                costs=costs,
                n_cases=len(ids),
                source=name,
                notes=notes,
                runs=len(r.sources),
            )
        )
    return rows


# S1 -----------------------------------------------------------------------------------


def s1_results(
    inputs: Inputs,
    cases: Mapping[str, CaseSet],
    results: Mapping[str, CellResult],
    allow_pending: bool,
) -> dict[str, CellResult]:
    """S1, off by default: the five concurrency-withdrawn passes scored as written in
    place of their reruns, everything else as registered. Only the cells they touch are
    rescored; item 17's universe values are left out of S1."""
    sources, _ = plan_passes(inputs, allow_pending, s1=True)
    touched = {k.split("/", 1)[1] for k in S1_PASSES}
    rescored = {
        name: score_cell(
            CELLS[name], sources[name], cases[CELLS[name].names], None, None, None, False
        )
        for name in sorted(touched)
        if CELLS[name].names in cases
    }
    return {**results, **rescored}
