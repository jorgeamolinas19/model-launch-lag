#!/usr/bin/env python3
"""Resolve `undetermined` support pairs by blaming the line that declares the architecture.

Most undetermined pairs are SHARED implementations: DeepSeek-V3 registered inside
deepseek_v2.py, or granite.py covering every Granite generation. The file's first
commit is then meaningless for a specific model - but the commit that added that
model's architecture STRING is exactly right, and blame answers it at line level.

Method: code-search the arch string in the repo -> pick the best file -> find the lines
containing it -> GraphQL blame -> earliest commit among those lines.
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
from datetime import date
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
SNAP = datetime.now(timezone.utc).date().isoformat()

BLAME_Q = """
query($owner:String!,$name:String!,$ref:String!,$path:String!){
  repository(owner:$owner,name:$name){
    object(expression:$ref){ ... on Commit { blame(path:$path){ ranges {
      startingLine endingLine
      commit { committedDate url messageHeadline }
    } } } }
  }
}"""
# Prefer a registry/declaration site over a test or doc mention.
PREF = ("registry.py", "modeling_auto.py", "configuration_auto.py", "__init__.py")
SKIP = ("test", "docs/", "benchmark", "examples/", ".md", "conftest")


def code_search(repo, term):
    q = urllib.parse.quote(f'"{term}" repo:{repo}')
    try:
        _, d = gh.get(f"search/code?q={q}&per_page=20")
    except (urllib.error.HTTPError, RuntimeError):
        return []
    time.sleep(2.5)  # code search is rate-limited harder than core
    return [i["path"] for i in d.get("items", [])]


def pick_file(paths):
    cand = [p for p in paths if not any(s in p.lower() for s in SKIP)]
    if not cand:
        return None
    for pref in PREF:
        for p in cand:
            if p.endswith(pref):
                return p
    cand.sort(key=len)
    return cand[0]


def blame_lines(repo, path, term):
    """Earliest commit among the lines containing `term`."""
    text = gh.raw_file(repo, path)
    if not text:
        return None
    lines = [i + 1 for i, l in enumerate(text.splitlines()) if term in l]
    if not lines:
        return None
    owner, name = repo.split("/")
    try:
        d = gh.graphql(BLAME_Q, owner=owner, name=name, ref="HEAD", path=path)
    except (RuntimeError, urllib.error.HTTPError) as e:
        print(f"      blame failed: {e}")
        return None
    obj = ((d.get("repository") or {}).get("object") or {})
    ranges = ((obj.get("blame") or {}).get("ranges") or [])
    hits = [r for r in ranges
            if any(r["startingLine"] <= n <= r["endingLine"] for n in lines)]
    if not hits:
        return None
    best = min(hits, key=lambda r: r["commit"]["committedDate"])
    c = best["commit"]
    return c["committedDate"][:10], c["url"], c["messageHeadline"][:70], len(lines)


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT s.framework_id, s.hf_id, m.architecture, m.release_date
        FROM support_events s JOIN models m USING(hf_id)
        WHERE s.state='undetermined' ORDER BY m.release_date""")]
    repos = {r[0]: r[1] for r in con.execute("SELECT id, repo FROM frameworks")}
    print(f"resolving {len(rows)} undetermined pairs by blame\n")

    fixed = 0
    for r in rows:
        arch, repo = r["architecture"], repos[r["framework_id"]]
        if not arch:
            continue
        print(f"{r['hf_id']} / {r['framework_id']}  ({arch})")
        paths = code_search(repo, arch)
        path = pick_file(paths)
        if not path:
            print(f"   arch string not found in {repo} -> genuinely unsupported\n")
            con.execute("""UPDATE support_events SET state='unsupported',
                evidence_rule=?, fidelity='exact' WHERE framework_id=? AND hf_id=?""",
                (f"{r['framework_id']}:arch-absent-from-codebase(code-search)",
                 r["framework_id"], r["hf_id"]))
            con.commit()
            continue
        b = blame_lines(repo, path, arch)
        if not b:
            print(f"   found in {path} but blame inconclusive\n")
            continue
        d, url, msg, n = b
        days = (date.fromisoformat(d) - date.fromisoformat(r["release_date"])).days
        tag = "DAY 0" if days == 0 else (f"{days:+d}d EARLY" if days < 0 else f"{days:+d}d")
        print(f"   {path}:{n} line(s) -> {d}  {tag}")
        print(f"   {msg}\n")
        con.execute("""UPDATE support_events SET state='supported', event_date=?,
            days_to_support=?, evidence_rule=?, fidelity='exact', evidence_urls=?
            WHERE framework_id=? AND hf_id=?""",
            (d, days, f"{r['framework_id']}:blame({path})", json.dumps([url]),
             r["framework_id"], r["hf_id"]))
        con.commit()
        fixed += 1

    left = con.execute("SELECT count(*) FROM support_events WHERE state='undetermined'").fetchone()[0]
    print(f"resolved {fixed} by blame | {left} still undetermined")


if __name__ == "__main__":
    main()
