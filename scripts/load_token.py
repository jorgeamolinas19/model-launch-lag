#!/usr/bin/env python3
"""Extract a GitHub token from a local file into .env, without ever printing it.

Reads the file on disk, strips RTF control words, writes .env mode 0600 (gitignored),
then verifies against the API. Only the scopes, the rate limit, and a masked
fingerprint are printed - never the secret.
"""
import json
import os
import re
import ssl
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
NAME = "git-launch-key.rtf"
TOKEN_RE = re.compile(r"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|gho_[A-Za-z0-9]{30,})")


def find_file():
    for d in (HOME / "Downloads", HOME / "Desktop", HOME / "Documents", HOME):
        p = d / NAME
        if p.is_file():
            return p
    hits = [p for d in (HOME / "Downloads", HOME / "Desktop") if d.is_dir()
            for p in d.glob("*.rtf") if "key" in p.name.lower() or "token" in p.name.lower()]
    return hits[0] if hits else None


def extract(p: Path):
    raw = p.read_text(errors="replace")
    # RTF: drop control words and grouping so a wrapped token reassembles.
    flat = re.sub(r"\\[a-zA-Z]+-?\d*\s?", " ", raw).replace("{", " ").replace("}", " ")
    for hay in (raw, flat, re.sub(r"\s+", "", flat)):
        m = TOKEN_RE.search(hay)
        if m:
            return m.group(0)
    return None


def verify(tok):
    ctx = ssl.create_default_context(cafile=certifi.where())
    h = {"Authorization": f"Bearer {tok}", "User-Agent": "model-launch-lag",
         "Accept": "application/vnd.github+json"}
    r = urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/rate_limit", headers=h), timeout=30, context=ctx)
    limit = json.load(r)["resources"]["core"]["limit"]
    scopes = r.headers.get("X-OAuth-Scopes")
    login = None
    try:
        u = urllib.request.urlopen(urllib.request.Request(
            "https://api.github.com/user", headers=h), timeout=30, context=ctx)
        login = json.load(u).get("login")
    except urllib.error.HTTPError:
        pass
    return limit, scopes, login


def main():
    p = find_file()
    if not p:
        sys.exit(f"could not find {NAME} in Downloads, Desktop, Documents or home")
    print(f"source file : {p}")
    tok = extract(p)
    if not tok:
        sys.exit("no GitHub token pattern found in that file")
    print(f"token       : {tok[:4]}...{tok[-4:]} (len {len(tok)}) - value not logged")

    env = ROOT / ".env"
    env.write_text(f"GITHUB_TOKEN={tok}\n")
    env.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    print(f"wrote       : {env.relative_to(ROOT)} mode {oct(env.stat().st_mode & 0o777)}")

    try:
        limit, scopes, login = verify(tok)
    except urllib.error.HTTPError as e:
        sys.exit(f"token rejected by GitHub: HTTP {e.code} - revoke it and use `gh auth login`")
    print(f"rate limit  : {limit}/hr  ({'authenticated' if limit > 60 else 'STILL ANONYMOUS'})")
    print(f"scopes      : {scopes!r}  (empty string = read-only public, the safe case)")
    print(f"account     : {login}")
    if scopes:
        print("\nNOTE: this token carries write scopes and is already exposed in a chat\n"
              "transcript and in a file on disk. Rotate it after this session.")


if __name__ == "__main__":
    main()
