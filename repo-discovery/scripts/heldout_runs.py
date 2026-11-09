"""Where each test pass lives, what its ``run.env`` names, whether its traces meet the
addendum's bounds, and which passes a registered run list would have scored.

Nothing here opens a prediction file. ``audit_pass`` reads trace status fields only, as
the run audits did; ``dry_run`` reads the run lists and ``run.env`` stamps, and only
checks that the other files exist.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from heldout_plan import (
    CELLS,
    MAX_NO_CALL_CASES,
    MAX_TIMEOUT_CASES,
    PASSES,
    PRED_FILE,
    REGISTRATION,
    RUN_ENV,
    S1_AREA,
    S1_PASSES,
    S1_TOOL_BROKEN,
    TEST_AREA,
    CellSpec,
    RegisteredPass,
    provider_error_allowance,
)

# Only these run.env keys (and keys naming a commit) are kept; other lines are dropped
# as they're parsed, never stored or printed.
RUN_ENV_KEYS = ("started", "finished", "complete", "host", "cursor_agent", "tools")
_COMMIT_KEY = re.compile(r"commit", re.IGNORECASE)
_HEX = re.compile(r"[0-9a-f]{7,40}")


def pass_dir(runs_root: Path, key: str, area: str = TEST_AREA) -> Path:
    return runs_root / area / key


def trace_dir(directory: Path, template: str = "{pass}") -> Path:
    return Path(template.replace("{pass}", str(directory)))


def read_run_env(path: Path, commit_key: str | None = None) -> dict[str, str]:
    """The whitelisted ``key=value`` lines of ``run.env``, plus every key naming a commit
    (or ``commit_key``). Other lines are dropped without being kept or printed."""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep:
            continue
        if key in RUN_ENV_KEYS or key == commit_key or _COMMIT_KEY.search(key):
            out[key] = value.strip()
    return out


def named_commits(env: Mapping[str, str] | None) -> list[str]:
    return [
        v.lower()
        for k, v in (env or {}).items()
        if k not in RUN_ENV_KEYS and _HEX.fullmatch(v.lower())
    ]


def commit_problem(env: Mapping[str, str] | None, registered: RegisteredPass | None) -> str | None:
    """Why a pass's ``run.env`` contradicts the registry's commit, or None. Kept passes
    have no ``run.env``. One that names no commit leaves it unverified, which reports show."""
    if registered is None or registered.kept:
        return None
    expected = registered.commit
    if env is None:
        return f"no {RUN_ENV}; every rerun pass has one, and the registry expects {expected}"
    wrong = [
        c for c in named_commits(env) if not (c.startswith(expected) or expected.startswith(c))
    ]
    if wrong:
        return f"{RUN_ENV} names commit {wrong[0][:12]}, not {expected}"
    return None


def commit_label(env: Mapping[str, str] | None, registered: RegisteredPass | None) -> str:
    if registered is None:
        return ""
    if registered.kept:
        return f"{registered.commit} (kept; no {RUN_ENV} by design)"
    verified = "checked in run.env" if named_commits(env) else "run.env names no commit"
    return f"{registered.commit} ({verified})"


def provider_error_case(trace: Mapping) -> bool:
    """Item 4: rerun whole after a provider error, or a final ``error`` status."""
    statuses = (trace.get("status"), trace.get("follow_up_status"))
    return bool(trace.get("provider_error_rerun")) or "error" in statuses


def server_calls(trace: Mapping, tool: str) -> int:
    return (
        len(trace.get("searches") or [])
        if tool == "search_repos"
        else len(trace.get("opens") or [])
    )


@dataclass
class PassAudit:
    key: str
    directory: Path
    predictions: bool
    traces: int
    missing_traces: list[str] = field(default_factory=list)
    timeouts: list[str] = field(default_factory=list)
    provider_errors: list[str] = field(default_factory=list)
    cli_not_server: list[str] = field(default_factory=list)
    no_call: list[str] = field(default_factory=list)
    run_env: dict[str, str] | None = None
    commit: str = ""
    problems: list[str] = field(default_factory=list)

    def row(self) -> dict:
        return {
            "pass": self.key,
            "directory": str(self.directory),
            "commit": self.commit,
            "traces": self.traces,
            "timeout_cases": len(self.timeouts),
            "provider_error_cases": len(self.provider_errors),
            "cli_calls_server_none": len(self.cli_not_server),
            "no_tool_call": len(self.no_call),
            "host": (self.run_env or {}).get("host"),
            "problems": "; ".join(self.problems),
        }


def audit_pass(
    spec: CellSpec,
    registered: RegisteredPass | None,
    directory: Path,
    traces: Path,
    case_ids: Sequence[str],
    commit_key: str | None = None,
) -> PassAudit:
    """Item 4's bound and, for a tool method, item 1's, from trace status fields only."""
    audit = PassAudit(
        f"{directory.parent.name}/{directory.name}",
        directory,
        (directory / PRED_FILE).is_file(),
        0,
    )
    if not audit.predictions:
        audit.problems.append(f"no {PRED_FILE}")
    env_path = directory / RUN_ENV
    audit.run_env = read_run_env(env_path, commit_key) if env_path.is_file() else None
    audit.commit = commit_label(audit.run_env, registered)
    problem = commit_problem(audit.run_env, registered)
    if problem:
        audit.problems.append(problem)
    for case_id in case_ids:
        path = traces / f"{case_id}.json"
        if not path.is_file():
            audit.missing_traces.append(case_id)
            continue
        audit.traces += 1
        trace = json.loads(path.read_text(encoding="utf-8"))
        if trace.get("status") == "timeout":
            audit.timeouts.append(case_id)
        if provider_error_case(trace):
            audit.provider_errors.append(case_id)
        if spec.tool:
            cli = int((trace.get("tools") or {}).get("mcpToolCall", 0))
            server = server_calls(trace, spec.tool)
            if cli and not server:
                audit.cli_not_server.append(case_id)
            if not cli and not server:
                audit.no_call.append(case_id)
    if audit.missing_traces:
        audit.problems.append(f"{len(audit.missing_traces)} cases have no trace")
    if len(audit.timeouts) > MAX_TIMEOUT_CASES:
        audit.problems.append(f"{len(audit.timeouts)} timeout cases")
    allowed = provider_error_allowance(spec.name)
    if len(audit.provider_errors) > allowed:
        audit.problems.append(
            f"{len(audit.provider_errors)} provider-error cases (bound {allowed})"
        )
    if audit.cli_not_server:
        audit.problems.append(
            f"tool bound (a): {len(audit.cli_not_server)} cases "
            "with CLI calls the server never logged"
        )
    if len(audit.no_call) > MAX_NO_CALL_CASES:
        audit.problems.append(f"tool bound (b): {len(audit.no_call)} cases with no tool call")
    return audit


# Run lists ----------------------------------------------------------------------------


@dataclass
class ListedRun:
    where: str
    tokens: list[str]
    flags: dict[str, str | bool]
    out: Path | None = None
    runs_root: Path | None = None
    area: str | None = None
    key: str | None = None
    problems: list[str] = field(default_factory=list)


_AREA = re.compile(r"test|withdrawn-[A-Za-z0-9_.-]+")
_PASS = re.compile(r"p\d+")
_LEVEL = re.compile(r"(?<![A-Za-z0-9])L[0-5](?![0-9])")


def parse_flags(tokens: Sequence[str]) -> dict[str, str | bool]:
    flags: dict[str, str | bool] = {}
    for i, token in enumerate(tokens):
        if not token.startswith("--"):
            continue
        name, sep, value = token[2:].partition("=")
        if sep:
            flags[name] = value
        elif i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
            flags[name] = tokens[i + 1]
        else:
            flags[name] = True
    return flags


def parse_run_list(path: Path) -> list[ListedRun]:
    """Each line that runs a pass (has ``--out``); blank and comment lines are skipped."""
    runs = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        run = ListedRun(f"{path.name}:{number}", tokens, parse_flags(tokens))
        out = run.flags.get("out")
        if not isinstance(out, str):
            run.problems.append("no --out; not a pass line")
            runs.append(run)
            continue
        run.out = Path(out)
        parts = run.out.parts
        for i in range(len(parts) - 3, -1, -1):
            if _AREA.fullmatch(parts[i]) and _PASS.fullmatch(parts[i + 1]):
                run.runs_root, run.area = Path(*parts[:i]), parts[i]
                run.key = f"{parts[i + 1]}/{parts[i + 2]}"
                break
        if run.key is None:
            run.problems.append(f"--out {out} isn't <root>/<area>/p<N>/<cell>/{PRED_FILE}")
        elif run.out.name != PRED_FILE:
            run.problems.append(f"--out names {run.out.name}, not {PRED_FILE}")
        runs.append(run)
    return runs


def flag_problems(spec: CellSpec, run: ListedRun) -> list[str]:
    """Where a run line's flags differ from its registered cell."""
    f, problems = run.flags, []

    def expect(name: str, wanted: object) -> None:
        got = f.get(name)
        if wanted is None and got is not None:
            problems.append(f"--{name} {got} on a cell that has none")
        elif wanted is not None and str(got) != str(wanted):
            problems.append(f"--{name} is {got}, the cell needs {wanted}")

    if not any(t.endswith("v5_dev_run.py") for t in run.tokens):
        problems.append("doesn't run scripts/v5_dev_run.py")
    expect("split", "test")
    registered = f.get("registered")
    if (
        not isinstance(registered, str)
        or len(registered) < 7
        or not REGISTRATION.startswith(registered.lower())
    ):
        problems.append(f"--registered is {registered}, not the registration {REGISTRATION[:7]}")
    evidence = f.get("evidence", "packets")
    wanted = "on-demand" if spec.method == "l5" else "packets"
    if evidence != wanted:
        problems.append(f"--evidence is {evidence}, the cell needs {wanted}")
    expect("open-budget", spec.budget if spec.method == "l5" else None)
    expect("search", spec.search)
    expect("anonymized", "everywhere" if spec.names == "hidden" else None)
    universes = Path(str(f.get("universes", "")))
    if f"u{spec.size}" not in universes.parts:
        problems.append(f"--universes {universes} has no u{spec.size} component")
    levels = set(_LEVEL.findall(str(universes)))
    if spec.method == "c1" and levels and levels != {spec.level}:
        problems.append(f"--universes names level {', '.join(sorted(levels))}, not {spec.level}")
    traces = f.get("trace-dir")
    if run.out is not None and isinstance(traces, str):
        parent = run.out.parent
        if Path(traces) != parent and parent not in Path(traces).parents:
            problems.append(f"--trace-dir {traces} is outside the pass directory {parent}")
    return problems


# Dry run ------------------------------------------------------------------------------


@dataclass
class Decision:
    run: ListedRun
    status: str
    decision: str
    files: str


def _files(
    directory: Path,
    registered: RegisteredPass | None,
    commit_key: str | None,
    traces_dir: Path | None = None,
) -> tuple[str, list[str]]:
    """What a pass directory holds, by file name only, and its ``run.env`` commit check."""
    if not directory.is_dir():
        return "directory absent", []
    names = [p.name for p in directory.iterdir()]
    where = traces_dir or directory
    traces = sum(p.name.endswith(".json") for p in where.iterdir()) if where.is_dir() else 0
    parts = [f"{PRED_FILE} {'present' if PRED_FILE in names else 'absent'}", f"{traces} traces"]
    env = read_run_env(directory / RUN_ENV, commit_key) if RUN_ENV in names else None
    if env is None:
        parts.append(f"no {RUN_ENV}")
    else:
        parts.append(f"host {env.get('host', '?')}, complete {env.get('complete', '?')}")
    parts.append(f"commit {commit_label(env, registered)}" if registered else "")
    problem = commit_problem(env, registered)
    return ", ".join(p for p in parts if p), [problem] if problem else []


def decide(
    run: ListedRun, accept: Mapping[str, object], s1: bool, commit_key: str | None = None
) -> Decision:
    if run.key is None:
        return Decision(run, "-", "not a pass line; never scored", "")
    cell = run.key.split("/", 1)[1]
    spec = CELLS.get(cell)
    registered = PASSES.get(run.key)
    if spec is not None and spec.agent:
        run.problems += flag_problems(spec, run)
    directory = (run.runs_root or Path()) / (run.area or "") / run.key
    if run.area != TEST_AREA:
        s1_pass = run.area == S1_AREA and run.key in S1_PASSES
        decision = (
            ("read by S1 (on)" if s1 else "S1 only; S1 is off")
            if s1_pass
            else "withdrawn; never scored"
        )
        exists = "present" if directory.is_dir() else "absent"
        return Decision(run, "withdrawn", decision, f"directory {exists} (not opened)")
    listed = run.flags.get("trace-dir")
    files, problems = _files(
        directory, registered, commit_key, Path(listed) if isinstance(listed, str) else None
    )
    run.problems += problems
    if registered is None:
        return Decision(run, "unregistered", "not registered; never scored", files)
    if registered.status == "pending" and run.key not in accept:
        return Decision(
            run, "pending", "pending (item 13); scored once the inputs accept it", files
        )
    if run.problems:
        return Decision(run, registered.status, "line differs from its cell; check first", files)
    if registered.status == "exploratory":
        return Decision(run, "exploratory", "scored as exploratory (item 14)", files)
    return Decision(run, registered.status, "scored", files)


def dry_run(
    lists: Sequence[Path],
    runs_root: Path,
    accept: Mapping[str, object] = {},
    s1: bool = False,
    commit_key: str | None = None,
) -> tuple[str, dict]:
    """A markdown report of which passes each run list would have scored, and the same as
    JSON. No prediction or trace is opened; S1's directories are only checked to exist."""
    decisions = [
        decide(run, accept, s1, commit_key) for path in lists for run in parse_run_list(path)
    ]
    lines = [
        "# Dry run: which listed passes would be scored",
        "",
        f"Run lists: {', '.join(str(p) for p in lists)}. No prediction or trace was opened.",
        "",
        "| Line | Pass | Area | Registry | Decision | Files | Problems |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in decisions:
        lines.append(
            f"| {d.run.where} | {d.run.key or ''} | {d.run.area or ''} | {d.status} | "
            f"{d.decision} | {d.files} | {'; '.join(d.run.problems)} |"
        )
    listed = {d.run.key for d in decisions if d.run.area == TEST_AREA}
    unlisted = [k for k in PASSES if k not in listed]
    lines += ["", f"## Registered passes in no list ({len(unlisted)})", ""]
    for key in unlisted:
        p = PASSES[key]
        directory = pass_dir(runs_root, key)
        exists = "present" if directory.is_dir() else "absent"
        lines.append(f"- {key} ({p.status}, accepted run: {p.accepted_run}); directory {exists}")
    scored = [d.run.key for d in decisions if d.decision == "scored"]
    lines += [
        "",
        f"**Would score {len(set(scored))} registered passes** of "
        f"{sum(p.status != 'exploratory' for p in PASSES.values())}; "
        f"{sum(d.status == 'exploratory' and d.decision.startswith('scored') for d in decisions)} "
        "exploratory.",
        "",
        f"## S1 ({'on' if s1 else 'off, the default'}): withdrawn passes it would read",
        "",
        "Scored as written in place of their reruns; never opened by this dry run.",
        "",
    ]
    s1_rows = []
    for key in S1_PASSES:
        directory = pass_dir(runs_root, key, S1_AREA)
        broken = " (tool never reached its server in item 12: †)" if key in S1_TOOL_BROKEN else ""
        exists = "present" if directory.is_dir() else "absent"
        lines.append(f"- `{directory}/` ({exists}){broken}")
        s1_rows.append({"pass": key, "path": str(directory), "exists": directory.is_dir()})
    record = {
        "lines": [
            {
                "where": d.run.where,
                "pass": d.run.key,
                "area": d.run.area,
                "registry": d.status,
                "decision": d.decision,
                "files": d.files,
                "problems": d.run.problems,
            }
            for d in decisions
        ],
        "unlisted": unlisted,
        "s1": {"enabled": s1, "passes": s1_rows},
    }
    return "\n".join(lines) + "\n", record
