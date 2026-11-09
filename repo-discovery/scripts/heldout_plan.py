"""The frozen plan for scoring the held-out test run: cells, comparisons, passes and bounds.

Everything here comes from PREREGISTRATION.md §3 and §4, entries 6 and 7, and the addendum to
entry 7. Where they leave a choice open, the value used is in ``CHOICES``, and
TEST_ANALYSIS.md lists each with its alternatives. Nothing here reads a file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REGISTRATION = "76882feff7c84eb5fafea3cd404bebc5b109411f"
RERUN_COMMIT = "c4b458f"
KEPT_COMMIT = "f85b205"
N_CASES, N_ECOSYSTEMS = 59, 30
SIZES = (50, 250, 1000, 5000, 10000)
NAMES = ("real", "hidden")
KS = (3, 5, 10, 20, 50, 100)
PRIMARY = "CompleteRecall@10"
KEY_SECONDARY = "CompleteRecall@20"
METRICS = (PRIMARY, KEY_SECONDARY, "Hit@10", "RequiredRecall@10", "LastRequiredRank")
LAST_RANK_CAP = max(KS) + 1
N_BOOT, SEED, ALPHA = 2000, 0, 0.05
DIGITS = 4
MEMORY_CUTOFF = "2026-03-01"
MEMORY_SPLIT = {"before": 25, "after": 34}

TEST_AREA = "test"
PRED_FILE = "pred.jsonl"
RUN_ENV = "run.env"
AGENT_RANKER = "cursor-agent"
AGENT_METHODS = ("c1", "c2", "l5")
TOOLS = {"c2": "search_repos", "l5": "open_repo"}
SEARCH_SHAPES = {"hybrid": "hybrid-rrf", "bm25f": "bm25f"}


@dataclass(frozen=True)
class CellSpec:
    """One test cell. ``level`` is the packet level the cell reads, where §3 fixes it."""

    name: str
    size: int
    names: str
    method: str
    role: str
    level: str | None = None
    budget: int | None = None
    search: str | None = None
    draws: int = 1

    @property
    def agent(self) -> bool:
        return self.method in AGENT_METHODS

    @property
    def ranker(self) -> str:
        """The ``ranker`` field its prediction files must carry."""
        return AGENT_RANKER if self.agent else self.method

    @property
    def tool(self) -> str | None:
        return TOOLS.get(self.method)

    @property
    def registered(self) -> bool:
        return self.role != "exploratory"


_AGENT_NAME = re.compile(
    r"u(?P<size>\d+)-(?P<names>real|hidden)-"
    r"(?:c1-(?P<c1>L[0-5])|c2-(?P<shape>hybrid|bm25f)-L4|l5-n(?P<budget>\d+))"
)


def agent_cell(name: str, role: str) -> CellSpec:
    m = _AGENT_NAME.fullmatch(name)
    if m is None:
        raise ValueError(f"not an agent cell name: {name}")
    size, names = int(m["size"]), m["names"]
    if m["c1"]:
        return CellSpec(name, size, names, "c1", role, level=m["c1"])
    if m["shape"]:
        return CellSpec(name, size, names, "c2", role, level="L4", search=SEARCH_SHAPES[m["shape"]])
    return CellSpec(name, size, names, "l5", role, level="L0", budget=int(m["budget"]))


# §3's table. Two secondary picks are static cells.
PRIMARY_PICKS = {
    (50, "real"): "u50-real-c1-L2",
    (50, "hidden"): "u50-hidden-c1-L2",
    (250, "real"): "u250-real-c1-L3",
    (250, "hidden"): "u250-hidden-c1-L2",
    (1000, "real"): "u1000-real-c1-L3",
    (1000, "hidden"): "u1000-hidden-c1-L4",
    (5000, "real"): "u5000-real-c2-hybrid-L4",
    (5000, "hidden"): "u5000-hidden-c2-bm25f-L4",
    (10000, "real"): "u10000-real-c2-bm25f-L4",
    (10000, "hidden"): "u10000-hidden-c2-bm25f-L4",
}
SECONDARY_PICKS = {
    (50, "real"): "u50-real-hybrid-rrf-L0",
    (50, "hidden"): "u50-hidden-name-match",
    (250, "real"): "u250-real-l5-n10",
    (250, "hidden"): "u250-hidden-bm25f-open50",
    (1000, "real"): "u1000-real-l5-n50",
    (1000, "hidden"): "u1000-hidden-l5-n50",
    (5000, "real"): "u5000-real-l5-n20",
    (5000, "hidden"): "u5000-hidden-l5-n50",
    (10000, "real"): "u10000-real-l5-n20",
    (10000, "hidden"): "u10000-hidden-l5-n20",
}
# Entry 6, item 14: exploratory, outside H1-H3 and §4's secondary analyses.
EXPLORATORY_AGENT = ("u5000-real-l5-n50", "u10000-real-l5-n50")

OPEN_BUDGETS = (0, 5, 10, 20, 50)
SCRIPTED_BUDGETS = (5, 10, 20, 50)
STATIC_RANKERS = (
    "random",
    "name-match",
    "bm25f",
    "bm25-cards",
    "dense-cards",
    "hybrid-rrf",
    "bm25f-deps",
    "bm25f-deps-random",
    "contract-joins",
    "bm25f-contract-text",
    *(f"bm25f-open{n}" for n in OPEN_BUDGETS),
    "scripted-search",
    *(f"scripted-open{n}" for n in SCRIPTED_BUDGETS),
)
DEPS_RANDOM_DRAWS = 5
NAMES_ONLY = ("random", "name-match")


def static_cell(size: int, names: str, ranker: str, role: str = "baseline") -> CellSpec:
    budget = re.fullmatch(r"(?:bm25f|scripted)-open(\d+)", ranker)
    level = "L0" if budget or ranker in NAMES_ONLY else "L4"
    draws = DEPS_RANDOM_DRAWS if ranker == "bm25f-deps-random" else 1
    return CellSpec(
        f"u{size}-{names}-{ranker}",
        size,
        names,
        ranker,
        role,
        level=level,
        budget=int(budget[1]) if budget else None,
        draws=draws,
    )


def _cells() -> dict[str, CellSpec]:
    cells: dict[str, CellSpec] = {}
    for name in PRIMARY_PICKS.values():
        cells[name] = agent_cell(name, "primary")
    for name in SECONDARY_PICKS.values():
        if _AGENT_NAME.fullmatch(name):
            cells[name] = agent_cell(name, "secondary")
    for name in EXPLORATORY_AGENT:
        cells[name] = agent_cell(name, "exploratory")
    for size in SIZES:
        for names in NAMES:
            for ranker in STATIC_RANKERS:
                cell = static_cell(size, names, ranker)
                if cell.name in SECONDARY_PICKS.values():
                    cell = static_cell(size, names, ranker, "secondary")
                cells[cell.name] = cell
    cells["u50-real-hybrid-rrf-L0"] = CellSpec(
        "u50-real-hybrid-rrf-L0", 50, "real", "hybrid-rrf", "secondary", level="L0"
    )
    return cells


CELLS = _cells()
AGENT_CELLS = tuple(c.name for c in CELLS.values() if c.agent)
REGISTERED_AGENT_CELLS = tuple(n for n in AGENT_CELLS if CELLS[n].registered)


@dataclass(frozen=True)
class Comparison:
    """``a`` minus ``b`` on ``metric``, paired per case."""

    id: str
    a: str
    b: str
    metric: str
    family: str
    question: str


def _hypotheses(size: int, metric: str, family: str, tag: str) -> list[Comparison]:
    out = []
    for h in ("H1", "H2", "H3"):
        for names in NAMES:
            pick, l5 = PRIMARY_PICKS[(size, names)], SECONDARY_PICKS[(size, names)]
            if h == "H1":
                a, b, q = pick, f"u{size}-{names}-bm25f", "primary pick vs bm25f at L4"
            elif h == "H2":
                a, b, q = (
                    pick,
                    f"u{size}-{names}-scripted-search",
                    "primary pick vs scripted-search",
                )
            else:
                n = CELLS[l5].budget
                a, b, q = l5, f"u{size}-{names}-scripted-open{n}", f"agent L5 vs scripted-open{n}"
            out.append(Comparison(f"{h}-{names}{tag}", a, b, metric, family, q))
    return out


MECHANISMS = (
    ("M1", "hybrid-rrf", "bm25f", "fusion: hybrid-rrf vs bm25f"),
    ("M2", "dense-cards", "bm25-cards", "dense vs lexical, same card text"),
    ("M3", "bm25f-deps", "bm25f-deps-random", "declared vs random dependency expansion"),
    ("M4", "contract-joins", "bm25f-contract-text", "contract joins vs contract text"),
)

CONFIRMATORY = tuple(_hypotheses(5000, PRIMARY, "confirmatory", ""))
SECONDARY = (
    *_hypotheses(1000, PRIMARY, "secondary", "@U1000"),
    *_hypotheses(10000, PRIMARY, "secondary", "@U10000"),
    *(
        c
        for size in (1000, 5000, 10000)
        for c in _hypotheses(size, KEY_SECONDARY, "secondary", f"@U{size}:CR@20")
    ),
    *(
        Comparison(
            f"{m}-{names}", f"u5000-{names}-{a}", f"u5000-{names}-{b}", PRIMARY, "secondary", q
        )
        for m, a, b, q in MECHANISMS
        for names in NAMES
    ),
)
EXPLORATORY = tuple(
    Comparison(f"N50-{versus}@U{size}", f"u{size}-real-l5-n50", b, PRIMARY, "exploratory", q)
    for size in (5000, 10000)
    for versus, b, q in (
        ("vs-N20", f"u{size}-real-l5-n20", "agent L5 at N=50 vs the registered N=20"),
        ("vs-scripted", f"u{size}-real-scripted-open50", "agent L5 at N=50 vs scripted-open50"),
    )
)
COMPARISONS = (*CONFIRMATORY, *SECONDARY, *EXPLORATORY)


# The addendum to entry 7, item 12, as written: pass, accepted run, host, pre-turn
# retries, non-provider fallbacks, withdrawn copies (unscored) and counted tries.
ITEM_12 = """
| p1/u50-real-c1-L2 | none yet; rerun pending (item 13) | – | – | – | kept 11-01 copy (`15ec4ed` by reflog), withdrawn 11-08 | pending |
| p1/u50-hidden-c1-L2 | reruns-a, 11-05 05:54 | MBP | 0 | 0 | appledouble; concurrency | 1 |
| p1/u250-hidden-c1-L2 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
| p1/u250-real-c1-L3 | reruns-a, 11-05 08:38 | MBP | 0 | 0 | appledouble; unpushed-commit | 1 |
| p1/u250-real-l5-n10 | reruns-a, 11-05 06:39 | MBP | 0 | 0 | appledouble; unpushed-commit | 1 |
| p1/u1000-hidden-c1-L4 | kept, 11-01 (`f85b205`) | laptop | 0 | 2 | appledouble | 1 |
| p1/u1000-hidden-l5-n50 | reruns-a, 11-05 04:59 | MBP | 0 | 0 | appledouble; concurrency† | 1 |
| p1/u1000-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 2 | appledouble | 1 |
| p1/u1000-real-l5-n50 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
| p1/u5000-hidden-c2-bm25f-L4 | reruns-a, 11-05 01:50 | MBP | 0 | 0 | invalid-key† | 1 |
| p1/u5000-hidden-l5-n50 | reruns-g, 11-07 23:30 | mbp-1 | 0 | 1 | appledouble; concurrency†; tool† (reruns-a) | 1 |
| p1/u5000-real-c2-hybrid-L4 | list 12b, 11-07 12:42 | mbp-1 | 1 | 1 | appledouble (4 cases); unpushed-commit†; tool† (reruns-a) | 1 |
| p1/u5000-real-l5-n20 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
| p1/u10000-hidden-l5-n20 | reruns-a, 11-05 07:02 | MBP | 0 | 1 | appledouble; invalid-key | 1 |
| p1/u10000-real-l5-n20 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
| p1/u10000-hidden-c2-bm25f-L4 | reruns-g, 11-08 01:21 | mbp-1 | 0 | 0 | invalid-key†; deadline† (reruns-b); timeouts† (reruns-c); timeouts-g (reruns-f, cell 3) | 2 |
| p1/u10000-real-c2-bm25f-L4 | reruns-f, 11-07 02:31 | mbp-1 | 1 | 0 | appledouble (2 cases); invalid-key†; provider† (reruns-c) | 1 |
| p2/u50-real-c1-L2 | none yet; rerun pending (item 13) | – | – | – | kept 11-01 copy (`45f673c` by reflog, before its push), withdrawn 11-08 | pending |
| p2/u50-hidden-c1-L2 | reruns-a, 11-05 06:17 | MBP | 0 | 0 | invalid-key | 1 |
| p2/u250-hidden-c1-L2 | reruns-a, 11-05 09:48 | MBP | 0 | 0 | invalid-key | 1 |
| p2/u250-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
| p2/u250-real-l5-n10 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble | 1 |
| p2/u1000-hidden-c1-L4 | reruns-a, 11-05 09:09 | MBP | 0 | 4 | invalid-key | 1 |
| p2/u1000-hidden-l5-n50 | reruns-a, 11-05 05:26 | MBP | 0 | 2 | invalid-key | 1 |
| p2/u1000-real-c1-L3 | kept, 11-01 (`f85b205`) | laptop | 0 | 1 | appledouble | 1 |
| p2/u1000-real-l5-n50 | kept, 11-01 (`f85b205`) | laptop | 0 | 0 | appledouble (5 cases) | 1 |
| p2/u5000-hidden-c2-bm25f-L4 | reruns-a, 11-05 03:20 | MBP | 0 | 0 | invalid-key | 1 |
| p2/u5000-hidden-l5-n50 | reruns-g, 11-08 00:07 | mbp-1 | 0 | 0 | invalid-key; tool† (reruns-a) | 1 |
| p2/u5000-real-c2-hybrid-L4 | list 12b, 11-07 14:09 | mbp-1 | 0 | 1 | invalid-key†; tool† (reruns-a) | 1 |
| p2/u5000-real-l5-n20 | reruns-g, 11-08 00:46 | mbp-1 | 0 | 0 | appledouble (4 cases); concurrency†; tool† (reruns-a) | 1 |
| p2/u10000-hidden-l5-n20 | reruns-a, 11-05 07:34 | MBP | 0 | 0 | invalid-key | 1 |
| p2/u10000-real-l5-n20 | reruns-a, 11-05 08:07 | MBP | 1 | 0 | concurrency† | 1 |
| p2/u10000-hidden-c2-bm25f-L4 | reruns-g, 11-08 03:41 | mbp-1 | 1 (3 attempts, item 9) | 1 | invalid-key; tool† (reruns-c); timeouts-g (list 12a) | 2 |
| p2/u10000-real-c2-bm25f-L4 | list 10, 11-07 07:39 | mbp-1 | 0 | 1 | invalid-key; timeouts† (reruns-e); timeouts-f (reruns-f) | 2 |
"""  # noqa: E501, RUF001
ITEM_14_LIST = "n50-real-2026-11-08.txt"
ITEM_14_SHA256 = "39ec2e29af535a0c8b558450c611a03347a3585d9fdb25cc016d3ec83d6839af"


@dataclass(frozen=True)
class RegisteredPass:
    """One registered pass and the commit it ran from (item 16). Kept passes ran from
    ``f85b205`` before ``run.env`` existed; every rerun's ``run.env`` should name its commit."""

    number: int
    cell: str
    status: str
    commit: str | None
    accepted_run: str = ""
    host: str = ""
    pre_turn_retries: str = ""
    fallbacks: str = ""
    withdrawn: str = ""
    tries: str = ""

    @property
    def key(self) -> str:
        return f"p{self.number}/{self.cell}"

    @property
    def kept(self) -> bool:
        return self.accepted_run.startswith("kept")


def _item_12() -> dict[str, RegisteredPass]:
    out = {}
    for line in ITEM_12.strip().splitlines():
        key, run, host, retries, fallbacks, withdrawn, tries = (
            part.strip() for part in line.strip().strip("|").split("|")
        )
        number, cell = key.split("/")
        status = "pending" if tries == "pending" else "accepted"
        kept = run.startswith("kept")
        out[key] = RegisteredPass(
            int(number[1:]),
            cell,
            status,
            KEPT_COMMIT if kept else RERUN_COMMIT,
            run,
            host,
            retries,
            fallbacks,
            withdrawn,
            tries,
        )
    return out


def _passes() -> dict[str, RegisteredPass]:
    passes = _item_12()
    for cell in EXPLORATORY_AGENT:
        for number in (1, 2):
            p = RegisteredPass(
                number, cell, "exploratory", RERUN_COMMIT, f"item 14, {ITEM_14_LIST}"
            )
            passes[p.key] = p
    return passes


PASSES = _passes()

# Item 4: 0 timeout and 0 provider-error cases per pass, but u1000-hidden-c1-L4 allows 29
# provider errors. Item 1: in a pass whose method gives the agent an MCP tool, (a) no case
# in which the CLI recorded tool calls and the server logged none, and (b) at most 2 cases
# with no tool call at all.
MAX_TIMEOUT_CASES = 0
PROVIDER_ERROR_ALLOWANCE = {"u1000-hidden-c1-L4": 29}
MAX_NO_CALL_CASES = 2

# Sensitivity analysis S1, off by default: the five passes withdrawn under entry 7's
# concurrency rule, scored as written in place of their reruns.
S1_AREA = "withdrawn-concurrency"
S1_PASSES = tuple(k for k, p in PASSES.items() if re.search(r"\bconcurrency\b", p.withdrawn))
S1_TOOL_BROKEN = tuple(k for k in S1_PASSES if "concurrency†" in PASSES[k].withdrawn)


def provider_error_allowance(cell: str) -> int:
    return PROVIDER_ERROR_ALLOWANCE.get(cell, 0)


# Open choices, with the value this code uses. TEST_ANALYSIS.md explains each.
CHOICES = {
    "pooling": "per case, the mean over both passes (and over the 5 bm25f-deps-random draws); "
    "a deviation (addendum item 15), kept as the primary analysis",
    "s1": "off unless --s1",
    "bootstrap": f"{N_BOOT} resamples of the 30 test ecosystems, seed {SEED}, numpy's "
    "default linear quantile; every cell and comparison reuses the same draws",
    "subgroups": "a subgroup's interval resamples its own ecosystems (same count and seed); "
    "the change-memory after-minus-before gap takes both groups from the all-case draws",
    "p-value": "share of resamples with a difference <= 0, no +1 correction; 0 is shown "
    f"as < 1/{N_BOOT}",
    "won-lost": "on pass-pooled per-case values; ties counted separately",
    "cr20-sizes": "CR@20 comparisons at U1000, U5000 and U10000",
    "mechanisms": "at U5000, under both name conditions, on CR@10",
    "secondary-adjustment": "none; only the 6 confirmatory tests are Holm-adjusted",
    "missing": "a missing prediction stops scoring; no imputation",
    "pending": "scoring stops while a registered pass is pending; the reported run lists the "
    "audited u50-real-c1-L2 reruns under accept and doesn't use --allow-pending",
    "run-env-commit": "a run.env naming no commit is scored and noted; one naming another "
    "commit, or a rerun pass without a run.env, stops scoring",
    "required-inputs": "the reported run needs costs and merge_dates",
    "reviewed-labels": "computed only from adjudicated test labels; none are recorded",
    "rounding": f"{DIGITS} decimals in JSON and CSV, 3 in markdown",
}
