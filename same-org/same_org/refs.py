"""Extract cross-references and ticket keys from PR and issue text.

A reference is classified by the words just before it, so "Depends on elastic/kibana#12" and
"Similar to elastic/kibana#12" can be counted as different link methods and hand-checked
separately.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[A-Za-z0-9][\w.-]*)/(?P<repo>[\w.-]+?)"
    r"/(?P<kind>pull|issues)/(?P<num>\d+)(?![\d])"
)
SHORT_RE = re.compile(
    r"(?<![\w/.@-])(?P<owner>[A-Za-z0-9][\w.-]*)/(?P<repo>[\w.-]+?)#(?P<num>\d+)\b"
)
LOCAL_RE = re.compile(r"(?<![\w/#&;])#(?P<num>\d{1,7})\b")
KEY_RE = re.compile(r"(?<![\w/.-])(?P<prefix>[A-Z][A-Z0-9]{1,14})-(?P<num>\d{1,7})\b")

# Prefixes that look like ticket keys but aren't one org's tracker.
NOT_KEYS = {
    "CVE", "GHSA", "CWE", "UTF", "SHA", "ISO", "RFC", "HTTP", "TLS", "SSL", "AES", "PEP", "JSR",
    "JEP", "GH", "PR", "WIP", "TODO", "FIXME", "IPV", "ECMA", "ES", "MD", "RSA", "ECDSA", "X",
    "UTC", "GMT", "CPU", "GPU", "OS", "API", "SDK", "V", "VERSION", "RELEASE", "BUILD", "COVID",
    "TOP", "MAX", "MIN", "NO", "SRE", "IEEE", "ANSI", "ASCII", "CP", "WINDOWS", "WIN", "ARM",
    "AMD", "INTEL", "NODE", "PYTHON", "JAVA", "JDK", "GO", "K", "UI", "PHASE", "STEP", "ITEM",
    "CHAPTER", "SECTION", "PART", "LEVEL", "TIER", "TYPE", "CLASS", "GROUP", "TEAM", "SPRINT",
}

CLOSE_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s*$", re.I)

# Checked in order; the first category whose pattern matches the window before a ref wins.
CONTEXT = [
    ("revert", r"\brevert"),
    ("port", r"\b(?:back-?port|forward-?port|cherry-?pick|port(?:ed)? (?:of|from|to)|"
             r"sync(?:ed)? from|mirror(?:ed)? from|copy of|upstream(?:ed)?(?: in| from)?)\b"),
    ("depends", r"\b(?:depends? on|dependent on|requires|required by|blocked by|blocks|"
                r"needs|prerequisite|must be merged|merge (?:after|before|with)|"
                r"after|before|waiting (?:on|for))\b"),
    ("companion", r"\b(?:companion|counterpart|sibling|paired? with|together with|along ?with|"
                  r"in tandem|coordinated|corresponding|matching|accompan\w*|same change|"
                  r"equivalent|also (?:in|needs?|requires?)|other half|see also)\b"),
    ("partof", r"\b(?:part of|towards?|tracking|tracked (?:in|by)|epic|umbrella|meta|"
               r"parent|sub-?task of|implements|implementation of|for)\b"),
    ("followup", r"\bfollow[- ]?(?:up|on)s?\b"),
    ("supersedes", r"\b(?:supersed\w*|replac\w*|instead of|duplicate of|dupe of)\b"),
    ("relates", r"\b(?:relate[sd]?(?: to)?|ref(?:s|erence[sd]?)?|see|cf\.?|context|similar|"
                r"like|as in|introduced (?:in|by)|caused by|regression)\b"),
]
CONTEXT_RES = [(name, re.compile(p + r"[^.\n]{0,40}$", re.I)) for name, p in CONTEXT]

STRIP_RES = [
    re.compile(r"<!--.*?-->", re.S),
    re.compile(r"```.*?```", re.S),
    re.compile(r"^\s*>.*$", re.M),
]


def clean(text: str | None) -> str:
    """Drop HTML comments (PR templates), fenced code and quoted replies."""
    t = text or ""
    for r in STRIP_RES:
        t = r.sub(" ", t)
    return t


@dataclass(frozen=True)
class Ref:
    owner: str
    repo: str
    num: int
    kind: str  # "pull", "issues" (from a URL) or "any" (short form, could be either)
    closes: bool
    context: str  # one of CONTEXT's names, or "mention"
    form: str  # "url", "short" or "local"

    @property
    def target(self) -> str:
        return f"{self.owner.lower()}/{self.repo.lower()}#{self.num}"


def _classify(before: str) -> tuple[bool, str]:
    tail = SHORT_RE.sub("REF", URL_RE.sub("REF", before[-400:]))
    window = tail[-80:]
    closes = bool(CLOSE_RE.search(window))
    for name, r in CONTEXT_RES:
        if r.search(window):
            return closes, name
    return closes, "mention"


def _strip_repo(repo: str) -> str:
    return re.sub(r"\.git$", "", repo.rstrip("."))


def extract_refs(text: str | None, self_repo: str) -> list[Ref]:
    """All issue/PR references in `text`. `self_repo` is "owner/name" for local `#N` refs."""
    t = clean(text)
    out: list[Ref] = []
    spans: list[tuple[int, int]] = []
    for m in URL_RE.finditer(t):
        closes, ctx = _classify(t[: m.start()])
        out.append(Ref(m["owner"], _strip_repo(m["repo"]), int(m["num"]), m["kind"], closes, ctx,
                       "url"))
        spans.append(m.span())
    for m in SHORT_RE.finditer(t):
        if any(a <= m.start() < b for a, b in spans):
            continue
        closes, ctx = _classify(t[: m.start()])
        out.append(Ref(m["owner"], _strip_repo(m["repo"]), int(m["num"]), "any", closes, ctx,
                       "short"))
        spans.append(m.span())
    so, sr = self_repo.split("/", 1)
    for m in LOCAL_RE.finditer(t):
        if any(a <= m.start() < b for a, b in spans):
            continue
        closes, ctx = _classify(t[: m.start()])
        out.append(Ref(so, sr, int(m["num"]), "any", closes, ctx, "local"))
    return out


def extract_keys(text: str | None) -> list[str]:
    """JIRA-style keys such as FLINK-1234 or OCPBUGS-56, minus common non-ticket prefixes."""
    t = clean(text)
    keys = []
    for m in KEY_RE.finditer(t):
        if m["prefix"] in NOT_KEYS or m["num"].startswith("0") and len(m["num"]) > 1:
            continue
        if re.fullmatch(r"(?:19|20)\d\d", m["num"]) and len(m["prefix"]) <= 2:
            continue
        keys.append(f"{m['prefix']}-{int(m['num'])}")
    return list(dict.fromkeys(keys))


PORT_TITLE = re.compile(
    r"^\s*(?:\[[^\]]*(?:backport|cherry|release-|\d+\.\d+)[^\]]*\]|backport|cherry-?pick|"
    r"revert\b|\[revert|automated cherry pick|.*\(backport\b|.*\bbackport (?:of|to)\b)",
    re.I,
)

# Contexts that link copies or undo a change rather than parts of one change.
EXCLUDED_CTX = {"port", "revert", "supersedes"}


GENERIC_BRANCHES = re.compile(
    r"^(?:main|master|develop|dev|trunk|patch-\d+|fix|bugfix|hotfix|feature|update|test|wip|"
    r"release|release-\d.*|v?\d+(?:\.\d+)*(?:\.x)?|backport.*|dependabot/.*|renovate/.*|"
    r"release-please.*|changeset-release/.*|update-.*-to-.*|bump.*|auto.*|sync.*|.*automation.*)$",
    re.I,
)


def is_generic_branch(name: str | None) -> bool:
    n = (name or "").strip()
    if not n or GENERIC_BRANCHES.match(n):
        return True
    tail = n.split("/")[-1]
    return len(tail) < 6 or bool(GENERIC_BRANCHES.match(tail))


BOT_LOGINS = re.compile(
    r"(?:\[bot\]$|^dependabot|^renovate|^github-actions|^mergify|^kodiak|^copybara|^release-please|"
    r"^k8s-ci-robot|^k8s-infra-cherrypick|^elasticmachine|^elastic-vault|^apmmachine|^mergify|"
    r"^grafanabot|^hashicorp-tsccr|^hc-github-team|^dotnet-maestro|^dotnet-bot|^azure-sdk|"
    r"^openshift-bot|^openshift-ci|^openshift-merge|^microsoft-github-policy|^msftbot|^snyk-bot|"
    r"^pre-commit-ci|^greenkeeper|^google-cloud-policy|^yoshi-automation|^gcf-|^forking-renovate|"
    r"bot$|-bot\b|-automation$|^svc-|^service-account)",
    re.I,
)


def is_bot(login: str | None, typename: str | None = None) -> bool:
    if typename == "Bot":
        return True
    return bool(login and BOT_LOGINS.search(login))
