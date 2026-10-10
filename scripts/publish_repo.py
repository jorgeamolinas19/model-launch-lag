#!/usr/bin/env python3
"""Create the GitHub repo and push, using the token in .env. Never logs the token.

Exits with a precise diagnosis if the credential lacks write scope, since a zero-scope
classic token can read public data but cannot create a repo or push.
"""
import json
import os
import re
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import certifi

ROOT = Path(__file__).resolve().parent.parent
NAME = "model-launch-lag"
DESC = ("How fast open-weight model launches become runnable across vLLM, SGLang, "
        "llama.cpp, Ollama, TensorRT-LLM and transformers - and what breaks.")
CTX = ssl.create_default_context(cafile=certifi.where())


def token():
    m = re.search(r"^GITHUB_TOKEN=(\S+)", (ROOT / ".env").read_text(), re.M)
    return m.group(1)


def api(path, method="GET", payload=None, tok=None):
    h = {"Authorization": f"Bearer {tok}", "User-Agent": NAME,
         "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    data = json.dumps(payload).encode() if payload else None
    if data:
        h["Content-Type"] = "application/json"
    r = urllib.request.urlopen(urllib.request.Request(
        f"https://api.github.com/{path}", headers=h, data=data, method=method),
        timeout=60, context=CTX)
    return r.status, json.load(r), r.headers


def git(*args, env=None):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def main():
    tok = token()
    _, me, hdr = api("user", tok=tok)
    login, scopes = me["login"], (hdr.get("X-OAuth-Scopes") or "")
    print(f"account {login} | scopes {scopes!r}")

    # 1. does the repo already exist?
    try:
        _, repo, _ = api(f"repos/{login}/{NAME}", tok=tok)
        print(f"repo already exists: {repo['html_url']}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            sys.exit(f"unexpected HTTP {e.code} checking for the repo")
        print(f"creating {login}/{NAME} (public)...")
        try:
            _, repo, _ = api("user/repos", "POST", {
                "name": NAME, "description": DESC, "private": False,
                "has_issues": True, "has_wiki": False, "auto_init": False}, tok=tok)
            print(f"created: {repo['html_url']}")
        except urllib.error.HTTPError as ce:
            body = ce.read().decode("utf-8", "replace")[:300]
            print(f"\nCANNOT CREATE REPO - HTTP {ce.code}")
            print(f"  scopes on this token: {scopes!r}")
            print(f"  github says: {body}")
            print("\n  A classic token with no scopes can read public data but cannot")
            print("  create repositories or push. Fix either way:")
            print("    A) gh auth login            (browser; credential goes to the keychain)")
            print("    B) new token with public_repo scope, then re-run this script")
            sys.exit(2)

    # 2. remote
    cur = git("remote", "get-url", "origin")
    url = f"https://github.com/{login}/{NAME}.git"
    if cur.returncode == 0:
        print(f"origin already set: {cur.stdout.strip()}")
    else:
        git("remote", "add", "origin", url)
        print(f"origin -> {url}")

    # 3. push, feeding the token through askpass so it never lands in argv or git config
    with tempfile.TemporaryDirectory() as td:
        ap = Path(td) / "askpass.sh"
        ap.write_text("#!/bin/sh\ncase \"$1\" in *sername*) echo x-access-token;; "
                      "*) sed -n 's/^GITHUB_TOKEN=//p' \"$MLL_ENV\";; esac\n")
        ap.chmod(stat.S_IRWXU)
        env = {"GIT_ASKPASS": str(ap), "MLL_ENV": str(ROOT / ".env"), "GIT_TERMINAL_PROMPT": "0"}
        p = git("push", "-u", "origin", "HEAD:main", env=env)
        print((p.stdout + p.stderr).strip()[:900])
        if p.returncode != 0:
            print("\nPUSH FAILED. If this is a 403, the token lacks write scope; see A/B above.")
            sys.exit(3)
    print(f"\npushed: https://github.com/{login}/{NAME}")


if __name__ == "__main__":
    main()
