"""Minimal GitHub REST and GraphQL client: standard library only, rate-limit aware, cached.

Every response is cached on disk under a key that hashes the full request (method, URL and
body), so reruns are free and a changed query never reads a stale answer. Calls are counted
per resource so every script can report what it spent.
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

API = "https://api.github.com"
REQUEST_DEADLINE_S = float(os.environ.get("SAME_ORG_REQUEST_DEADLINE_S", "300"))


def read_body(r, deadline: float, clock=time.monotonic) -> bytes:
    """Read a response body by chunks, failing once `clock()` passes `deadline`.

    The socket timeout bounds each read, not the body, so a body that trickles in can hold
    a worker for good. read(amt) also returns short instead of raising when a body with a
    Content-Length is cut off, so the remaining length is checked here.
    """
    chunks = []
    while chunk := r.read(1 << 16):
        chunks.append(chunk)
        if clock() > deadline:
            raise TimeoutError(f"response body still incomplete after the deadline "
                               f"({sum(map(len, chunks))} bytes)")
    if r.length:
        raise http.client.IncompleteRead(b"".join(chunks), r.length)
    return b"".join(chunks)


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        try:
            tok = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            tok = ""
    if not tok:
        sys.exit("no GitHub token: set GITHUB_TOKEN or log in with `gh auth login`")
    return tok


@dataclass
class Spend:
    rest: int = 0
    graphql_calls: int = 0
    graphql_points: int = 0
    cache_hits: int = 0
    bytes_in: int = 0
    waits_s: float = 0.0
    request_s: float = 0.0
    retries: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, **kw) -> None:
        with self.lock:
            for k, v in kw.items():
                if k == "kind":
                    self.by_kind[v] = self.by_kind.get(v, 0) + 1
                else:
                    setattr(self, k, getattr(self, k) + v)

    def as_dict(self) -> dict:
        return {
            "rest": self.rest,
            "graphql_calls": self.graphql_calls,
            "graphql_points": self.graphql_points,
            "cache_hits": self.cache_hits,
            "bytes_in": self.bytes_in,
            "waits_s": round(self.waits_s, 1),
            "request_s": round(self.request_s, 1),
            "retries": self.retries,
            "by_kind": dict(sorted(self.by_kind.items())),
        }


class GitHub:
    """Thread-safe client. `min_remaining` keeps a reserve so other work on the token isn't starved."""

    def __init__(self, cache_dir: str | Path, min_remaining: int = 200, verbose: bool = False,
                 max_5xx_retries: int = 4):
        self.cache = Path(cache_dir).expanduser()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.tok = _token()
        self.min_remaining = min_remaining
        self.verbose = verbose
        # A query too heavy for GitHub's timeout 502s on every retry; callers that can split
        # the query should retry less.
        self.max_5xx_retries = max_5xx_retries
        self.spend = Spend()
        self.auth_failures = 0
        self.max_auth_wait_min = int(os.environ.get("SAME_ORG_MAX_AUTH_WAIT_MIN", "30"))

    def _key(self, method: str, url: str, body: bytes | None) -> Path:
        h = hashlib.sha256(method.encode() + b"\0" + url.encode() + b"\0" + (body or b""))
        d = h.hexdigest()
        return self.cache / d[:2] / f"{d}.json.gz"

    def _read_cache(self, p: Path):
        if p.exists():
            self.spend.add(cache_hits=1)
            with gzip.open(p, "rt") as f:
                return json.load(f)
        return None

    def _write_cache(self, p: Path, obj) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with gzip.open(tmp, "wt") as f:
            json.dump(obj, f)
        tmp.replace(p)

    def _wait_reset(self, headers, why: str) -> None:
        reset = int(headers.get("x-ratelimit-reset") or 0)
        retry_after = headers.get("retry-after")
        if retry_after:
            delay = float(retry_after) + 1
        else:
            delay = max(5.0, reset - time.time() + 2)
        print(f"[gh] {why}: waiting {delay:.0f}s", file=sys.stderr, flush=True)
        self.spend.add(waits_s=delay)
        time.sleep(delay)

    def _do(self, method: str, url: str, body: bytes | None, accept: str):
        attempt = 0
        while True:
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Authorization", f"Bearer {self.tok}")
            req.add_header("Accept", accept)
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            req.add_header("User-Agent", "neverfield-experiments-same-org")
            if body is not None:
                req.add_header("Content-Type", "application/json")
            t0 = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    raw = read_body(r, t0 + REQUEST_DEADLINE_S)
                    self.auth_failures = 0
                    self.spend.add(bytes_in=len(raw), request_s=time.monotonic() - t0)
                    rem = r.headers.get("x-ratelimit-remaining")
                    if rem is not None and int(rem) < self.min_remaining:
                        self._wait_reset(r.headers, f"remaining {rem} below reserve")
                    return r.status, dict(r.headers), raw
            except urllib.error.HTTPError as e:
                raw = e.read()
                hdrs = dict(e.headers)
                if e.code == 401:
                    # Installation tokens rotate; the new one appears in gh's config.
                    self.auth_failures += 1
                    if self.auth_failures > self.max_auth_wait_min:
                        raise RuntimeError("GitHub token rejected for too long") from e
                    print("[gh] 401: re-reading token in 60s", file=sys.stderr, flush=True)
                    self.spend.add(waits_s=60)
                    time.sleep(60)
                    self.tok = _token()
                    continue
                if e.code in (403, 429) and (
                    hdrs.get("x-ratelimit-remaining") == "0" or "retry-after" in hdrs
                    or b"secondary rate limit" in raw.lower()
                ):
                    if hdrs.get("x-ratelimit-remaining") != "0" and "retry-after" not in hdrs:
                        # GitHub asks for at least a minute after a secondary limit.
                        hdrs = {"retry-after": "60"}
                    self._wait_reset(hdrs, f"HTTP {e.code} rate limited")
                    continue
                if e.code in (500, 502, 503, 504) and attempt < self.max_5xx_retries:
                    attempt += 1
                    self.spend.add(retries=1)
                    time.sleep(4 * 2**attempt)
                    continue
                return e.code, hdrs, raw
            except (urllib.error.URLError, TimeoutError, ConnectionError,
                    http.client.HTTPException) as e:
                # HTTPException covers IncompleteRead, a body cut off mid-transfer.
                if attempt < 4:
                    attempt += 1
                    self.spend.add(retries=1)
                    print(f"[gh] network error {e!r:.200}; retry {attempt}", file=sys.stderr)
                    time.sleep(4 * 2**attempt)
                    continue
                raise

    def rest(self, path: str, kind: str = "rest", cache: bool = True):
        """GET a REST path. Returns (status, json-or-None). 404s are cached as None."""
        url = path if path.startswith("http") else API + path
        p = self._key("GET", url, None)
        if cache:
            hit = self._read_cache(p)
            if hit is not None:
                return hit["status"], hit["data"]
        status, _, raw = self._do("GET", url, None, "application/vnd.github+json")
        self.spend.add(rest=1, kind=kind)
        data = json.loads(raw) if raw and status < 400 else None
        if status < 400 or status in (404, 409, 451):
            if cache:
                self._write_cache(p, {"status": status, "data": data})
        else:
            print(f"[gh] GET {url} -> {status}: {raw[:200]!r}", file=sys.stderr)
        return status, data

    def rest_pages(self, path: str, kind: str = "rest", per_page: int = 100):
        sep = "&" if "?" in path else "?"
        page = 1
        while True:
            status, data = self.rest(f"{path}{sep}per_page={per_page}&page={page}", kind=kind)
            if status != 200:
                raise RuntimeError(f"GET {path} page {page} -> {status}; listing incomplete")
            if not data:
                return
            items = data if isinstance(data, list) else data.get("items", [])
            yield from items
            if len(items) < per_page:
                return
            page += 1

    def graphql(self, query: str, variables: dict | None = None, kind: str = "graphql",
                cache: bool = True) -> dict:
        """POST a GraphQL query. Adds `rateLimit { cost remaining resetAt }` to the spend log."""
        if "rateLimit" not in query:
            i = query.rindex("}")
            query = query[:i] + " rateLimit { cost remaining resetAt } }"
        body = json.dumps({"query": query, "variables": variables or {}}, sort_keys=True).encode()
        p = self._key("POST", API + "/graphql", body)
        if cache:
            hit = self._read_cache(p)
            if hit is not None:
                return hit
        attempt = 0
        while True:
            status, hdrs, raw = self._do("POST", API + "/graphql", body, "application/json")
            self.spend.add(graphql_calls=1, kind=kind)
            try:
                out = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                out = {}
            errs = out.get("errors") or []
            # A 200 with errors and no data is a server-side timeout; retry it like a 502.
            transient = status in (502, 504) or (status == 200 and errs and not out.get("data"))
            limited = any(e.get("type") == "RATE_LIMITED" for e in errs)
            if transient or limited:
                self.spend.add(retries=1)
                attempt += 1
                if attempt > (5 if limited else self.max_5xx_retries + 1):
                    raise RuntimeError(f"graphql failed after retries: {raw[:300]!r}")
                if limited:
                    self._wait_reset(hdrs, "graphql RATE_LIMITED")
                else:
                    time.sleep(4 * 2**attempt)
                continue
            break
        rl = (out.get("data") or {}).get("rateLimit") or {}
        self.spend.add(graphql_points=int(rl.get("cost") or 0))
        if rl and int(rl.get("remaining") or 10**6) < self.min_remaining:
            self._wait_reset({"x-ratelimit-reset": _iso_to_epoch(rl.get("resetAt"))},
                             f"graphql remaining {rl.get('remaining')} below reserve")
        if status == 200 and not errs and cache:
            self._write_cache(p, out)
        elif errs:
            fatal = [e for e in errs if e.get("type") not in ("NOT_FOUND",)]
            if fatal:
                print(f"[gh] graphql errors: {json.dumps(fatal)[:400]}", file=sys.stderr)
            elif cache:
                self._write_cache(p, out)
        return out


def _iso_to_epoch(s: str | None) -> int:
    if not s:
        return int(time.time()) + 60
    from datetime import datetime

    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
