"""Minimal GitHub API client. stdlib only; token read from .env, never logged."""
import gzip
import json
import re
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import certifi

API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
_CTX = ssl.create_default_context(cafile=certifi.where())


def _token():
    """Prefer the gh CLI's keychain credential; fall back to .env, then anonymous.

    Keychain first so no plaintext token is needed on disk at all.
    """
    try:
        p = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    env = ROOT / ".env"
    if env.is_file():
        m = re.search(r"^GITHUB_TOKEN=(\S+)", env.read_text(), re.M)
        if m:
            return m.group(1)
    return None


_TOK = _token()


def _headers():
    h = {"User-Agent": "model-launch-lag/0.1 (research)",
         "Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28"}
    if _TOK:
        h["Authorization"] = f"Bearer {_TOK}"
    return h


def get(path, tries=4):
    """GET an API path. Returns (headers, parsed). Sleeps through secondary rate limits."""
    url = path if path.startswith("http") else f"{API}/{path.lstrip('/')}"
    for n in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=_headers()),
                                       timeout=60, context=_CTX)
            return r.headers, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):  # primary or secondary rate limit
                reset = e.headers.get("X-RateLimit-Reset")
                wait = max(2 ** n, min(60, int(reset) - int(time.time())) if reset else 2 ** n)
                if n < tries - 1:
                    time.sleep(max(1, wait))
                    continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if n < tries - 1:
                time.sleep(2 ** n * 2)
                continue
            raise


def graphql(query, **variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    h = _headers()
    h["Content-Type"] = "application/json"
    r = urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/graphql", headers=h, data=body, method="POST"),
        timeout=60, context=_CTX)
    d = json.load(r)
    if d.get("errors"):
        raise RuntimeError(d["errors"][0].get("message", "graphql error"))
    return d["data"]


def raw_file(repo, path, ref="HEAD"):
    """File contents as text, or None."""
    try:
        _, d = get(f"repos/{repo}/contents/{urllib.parse.quote(path)}?ref={ref}")
    except urllib.error.HTTPError:
        return None
    import base64
    if isinstance(d, list) or d.get("encoding") != "base64":
        return None
    return base64.b64decode(d["content"]).decode("utf-8", "replace")


def exists(repo, path):
    """Does a path exist at the repo's default-branch HEAD? Returns 'file'|'dir'|None."""
    try:
        _, d = get(f"repos/{repo}/contents/{urllib.parse.quote(path)}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return "dir" if isinstance(d, list) else "file"


def repo_info(repo):
    """Resolve a repo slug, following renames. Returns (canonical_name, meta) or None."""
    try:
        _, d = get(f"repos/{repo}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return d.get("full_name"), d


def rate():
    _, d = get("rate_limit")
    c = d["resources"]["core"]
    return c["limit"], c["remaining"]


def save_raw(obj, root: Path, name: str):
    f = root / f"{name.replace('/', '__')}.json.gz"
    f.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(f, "wt", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return f
