#!/usr/bin/env python3
"""Collect support_events: when each model became runnable in each framework.

Applies the per-framework evidence rules in docs/evidence-rules.md. Writes one row per
(framework, model) pair - including `unsupported` pairs, which are right-censored
observations rather than missing data (docs/metrics.md §1).

Usage:
  collect_support.py                      # all pairs
  collect_support.py --models qwen3.5 --frameworks vllm    # substring filters
  collect_support.py --dry-run            # search only, write nothing
"""
import argparse
import json
import re
import sqlite3
import sys
import time
import tomllib
import urllib.error
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
SNAP = datetime.now(timezone.utc).date().isoformat()
RAW = ROOT / "raw" / "github" / SNAP
DB = ROOT / "db" / "launch_lag.sqlite"

# Evidence paths per framework, from docs/evidence-rules.md. A PR qualifies only if it
# touches one of these: naming a model in a test fixture or docs table is not support.
EVIDENCE = {
    "transformers": {"impl": ["src/transformers/models/"]},
    "vllm": {"impl": ["vllm/model_executor/models/"]},
    "sglang": {"impl": ["python/sglang/srt/models/"]},
    # Multi-part: unusable until BOTH convert mapping and graph build land, so the
    # event date is the LATER of them (evidence-rules.md, llama.cpp).
    "llamacpp": {"convert": ["convert_hf_to_gguf.py"],
                 "graph": ["src/llama-model.cpp", "src/llama-arch.cpp", "src/llama-vocab.cpp"]},
    "trtllm": {"impl": ["tensorrt_llm/models/", "tensorrt_llm/_torch/models/", "examples/"]},
}
CODE_FWS = list(EVIDENCE)
MAX_CANDIDATES = 12          # earliest-first; a true impl PR is never 13 deep
SEARCH_PAUSE = 2.2           # search API allows 30/min authenticated


def search_terms(m):
    """Highest-confidence first. An arch class name appears verbatim in registry
    entries and in 'architecture not supported' errors."""
    t = []
    if m["architecture"]:
        t.append(m["architecture"])
    short = m["hf_id"].split("/", 1)[1]
    t.append(short)
    base = re.sub(r"-(instruct|it|base|chat|think|bf16|fp8)$", "", short, flags=re.I)
    if base != short:
        t.append(base)
    if m["family"] not in [x.lower() for x in t]:
        t.append(m["family"])
    return list(dict.fromkeys(t))


def find_prs(repo, term):
    q = f'repo:{repo} is:pr is:merged "{term}"'
    try:
        _, d = gh.get(f"search/issues?q={urllib.parse.quote(q)}&sort=created&order=asc&per_page=20")
    except urllib.error.HTTPError as e:
        if e.code == 422:
            return []
        raise
    time.sleep(SEARCH_PAUSE)
    return d.get("items", [])


def pr_paths(repo, number):
    try:
        _, files = gh.get(f"repos/{repo}/pulls/{number}/files?per_page=100")
    except urllib.error.HTTPError:
        return []
    return [f["filename"] for f in files]


def classify_pr(fw, paths):
    """Which evidence groups does this PR satisfy?"""
    hit = set()
    for group, prefixes in EVIDENCE[fw].items():
        if any(p.startswith(tuple(prefixes)) for p in paths):
            hit.add(group)
    return hit


def merged_at(pr):
    return (pr.get("pull_request") or {}).get("merged_at") or pr.get("closed_at")


def collect_code(fw, repo, m, verbose):
    """Earliest qualifying merged PR per evidence group."""
    earliest, seen = {}, set()
    for term in search_terms(m):
        for pr in find_prs(repo, term)[:MAX_CANDIDATES]:
            n = pr["number"]
            if n in seen:
                continue
            seen.add(n)
            ma = merged_at(pr)
            if not ma:
                continue
            groups = classify_pr(fw, pr_paths(repo, n))
            if verbose and groups:
                print(f"      PR #{n} {ma[:10]} -> {sorted(groups)}  {pr['title'][:52]}")
            for g in groups:
                if g not in earliest or ma < earliest[g][0]:
                    earliest[g] = (ma, pr["html_url"], n)
        if set(EVIDENCE[fw]) <= set(earliest):
            break
    need = set(EVIDENCE[fw])
    if not earliest:
        return None
    if need <= set(earliest):
        # Later of all required parts: the model is not runnable until the last lands.
        g, (ma, url, _) = max(earliest.items(), key=lambda kv: kv[1][0])
        return dict(state="supported", event_date=ma[:10],
                    urls=[v[1] for v in earliest.values()],
                    rule=f"{fw}:impl-pr(latest of {','.join(sorted(earliest))})", fidelity="exact")
    ma, url, _ = min(earliest.values(), key=lambda v: v[0])
    return dict(state="partial", event_date=ma[:10], urls=[v[1] for v in earliest.values()],
                rule=f"{fw}:partial(have {','.join(sorted(earliest))}; need {','.join(sorted(need - set(earliest)))})",
                fidelity="exact")


def collect_ollama(m, releases, verbose):
    """Earliest ollama/ollama release whose notes name the model (evidence-rules.md)."""
    cands = {m["family"].lower(), m["hf_id"].split("/", 1)[1].lower()}
    base = re.sub(r"[-_.]", "", m["family"].lower())
    for rel in sorted(releases, key=lambda r: r.get("published_at") or ""):
        body = ((rel.get("body") or "") + " " + (rel.get("name") or "")).lower()
        flat = re.sub(r"[-_.\s]", "", body)
        if any(c in body for c in cands) or (len(base) > 4 and base in flat):
            if verbose:
                print(f"      {rel['tag_name']} {rel['published_at'][:10]}  {(rel.get('name') or '')[:46]}")
            return dict(state="supported", event_date=rel["published_at"][:10],
                        urls=[rel["html_url"]], rule="ollama:release-notes", fidelity="good")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--frameworks", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    cohort = tomllib.loads((ROOT / "cohort.toml").read_text())
    repos = {k: v["repo"] for k, v in cohort["frameworks"].items()}
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    models = [dict(r) for r in con.execute(
        "SELECT hf_id,family,architecture,release_date,support_kind,band FROM models ORDER BY release_date")]
    if a.models:
        models = [m for m in models if a.models.lower() in m["hf_id"].lower()
                  or a.models.lower() in m["family"].lower()]
    fws = [f for f in (CODE_FWS + ["ollama"]) if not a.frameworks or a.frameworks in f]

    rel_cache = {}
    if "ollama" in fws:
        _, rels = gh.get("repos/ollama/ollama/releases?per_page=100")
        gh.save_raw(rels, RAW / "releases", "ollama")
        rel_cache["ollama"] = rels
        print(f"cached {len(rels)} ollama releases")

    lim, start_rem = gh.rate()
    rows = []
    for m in models:
        print(f"\n{m['hf_id']}  (released {m['release_date']}, {m['support_kind']})")
        for fw in fws:
            try:
                r = (collect_ollama(m, rel_cache["ollama"], a.verbose) if fw == "ollama"
                     else collect_code(fw, repos[fw], m, a.verbose))
            except urllib.error.HTTPError as e:
                print(f"   {fw:<13} ERROR HTTP {e.code}")
                continue
            if r is None:
                days = (date.fromisoformat(SNAP) - date.fromisoformat(m["release_date"])).days
                r = dict(state="unsupported", event_date=None, urls=[],
                         rule=f"{fw}:no-qualifying-artifact", fidelity="exact")
                print(f"   {fw:<13} unsupported  (censored at {days}d)")
                d = None
            else:
                d = (date.fromisoformat(r["event_date"]) - date.fromisoformat(m["release_date"])).days
                tag = "DAY 0" if d == 0 else (f"{d:+d}d EARLY" if d < 0 else f"{d:+d}d")
                print(f"   {fw:<13} {r['state']:<10} {r['event_date']}  {tag:<10} {r['fidelity']}")
            rows.append((fw, m["hf_id"], r, d))

    if not a.dry_run:
        for fw, hf_id, r, d in rows:
            con.execute("""INSERT OR REPLACE INTO support_events(framework_id,hf_id,state,
                event_date,days_to_support,evidence_rule,fidelity,evidence_urls,snapshot_date)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (fw, hf_id, r["state"], r["event_date"], d, r["rule"], r["fidelity"],
                 json.dumps(r["urls"]), SNAP))
        con.commit()
        print(f"\nwrote {len(rows)} support_events")
    lim, rem = gh.rate()
    print(f"api calls used: {start_rem - rem} | remaining {rem}/{lim}")


if __name__ == "__main__":
    main()
