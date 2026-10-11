#!/usr/bin/env python3
"""For each undetermined support pair, list MERGED PRs whose TITLE names the model.

This is the search the adjudication standard calls for - a model-specific integration
artifact with a verified merge date - narrowed to titles so a passing mention in a body
cannot qualify. Output is a candidate list for human adjudication, not a decision: it is
written to support_events_hand.csv's companion file for review.
"""
import re
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"


def terms(hf_id, family, arch):
    short = hf_id.split("/", 1)[1]
    base = re.sub(r"-(instruct|it|base|chat|think|bf16|fp8|flash)$", "", short, flags=re.I)
    out = [short, base, family, family.replace("-", " "), family.replace("-", "")]
    if arch:
        out.append(arch)
    return list(dict.fromkeys(t for t in out if len(t) > 2))


def main():
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
    repos = {r[0]: r[1] for r in con.execute("SELECT id, repo FROM frameworks")}
    rows = con.execute("""SELECT s.framework_id fw, s.hf_id, m.family, m.architecture, m.release_date
        FROM support_events s JOIN models m USING(hf_id) WHERE s.state='undetermined'
        ORDER BY m.release_date""").fetchall()
    print(f"{len(rows)} undetermined pairs\n")
    out = []
    for r in rows:
        repo = repos[r["fw"]]
        seen = {}
        for t in terms(r["hf_id"], r["family"], r["architecture"]):
            q = f'repo:{repo} is:pr is:merged in:title "{t}"'
            try:
                _, d = gh.get(f"search/issues?q={urllib.parse.quote(q)}&sort=created&order=asc&per_page=15")
            except Exception as e:
                continue
            time.sleep(2.2)
            for it in d.get("items", []):
                seen[it["number"]] = it
        cands = sorted(seen.values(), key=lambda it: (it.get("pull_request") or {}).get("merged_at") or "9")
        print(f"{r['fw']:<13} {r['hf_id']}  (released {r['release_date']})")
        if not cands:
            print("    no merged PR with the model in the title")
        for it in cands[:6]:
            ma = ((it.get("pull_request") or {}).get("merged_at") or "")[:10]
            print(f"    {ma}  #{it['number']:<6} {it['title'][:70]}")
            out.append((r["fw"], r["hf_id"], r["release_date"], ma, it["number"], it["title"], it["html_url"]))
        print()
    p = ROOT / "undetermined_pr_candidates.csv"
    with p.open("w") as f:
        f.write("framework,hf_id,release_date,merged_at,pr,title,url\n")
        for row in out:
            f.write(",".join('"' + str(x).replace('"', "'") + '"' for x in row) + "\n")
    print(f"candidates -> {p.name}")


if __name__ == "__main__":
    main()
