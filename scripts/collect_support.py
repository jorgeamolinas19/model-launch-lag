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


# Frameworks with a per-architecture file or directory. For these, the first commit
# touching that path IS the support date - exact, and immune to search ranking.
PER_MODEL_DIR = {
    "transformers": "src/transformers/models",
    "vllm": "vllm/model_executor/models",
    "sglang": "python/sglang/srt/models",
    # TensorRT-LLM DOES have per-architecture files (modeling_qwen3.py, ...), 75 of
    # them. Missing this is why trtllm had zero exact-fidelity observations and looked
    # like the slowest framework by +52d - a measurement artifact, not a finding.
    "trtllm": "tensorrt_llm/_torch/models",
}
_DIR_CACHE = {}
_ARCH_SUFFIX = re.compile(
    r"(ForConditionalGeneration|ForCausalLM|ForBlockDiffusion|ForSequenceClassification"
    r"|MoeModelLM|ModelLM|DraftModel|Model|LM)$")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def arch_candidates(arch):
    """Normalized name fragments an implementation path is likely to use."""
    base = _ARCH_SUFFIX.sub("", arch or "")
    if not base:
        return []
    snake = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", base).lower()
    return list(dict.fromkeys(_norm(x) for x in (base, snake, snake.replace("_", "")) if x))


def list_model_dir(repo, path):
    key = (repo, path)
    if key not in _DIR_CACHE:
        try:
            _, d = gh.get(f"repos/{repo}/contents/{urllib.parse.quote(path)}")
            _DIR_CACHE[key] = {
                _norm(e["name"].removesuffix(".py").removeprefix("modeling_")):
                    f"{path}/{e['name']}" for e in d}
        except urllib.error.HTTPError:
            _DIR_CACHE[key] = {}
    return _DIR_CACHE[key]


def first_commit_for_path(repo, path, cap=12):
    """Oldest commit touching a path. Paginates to the end of its history."""
    page, oldest = 1, None
    while page <= cap:
        _, c = gh.get(f"repos/{repo}/commits?path={urllib.parse.quote(path)}"
                      f"&per_page=100&page={page}")
        if not c:
            break
        oldest = c[-1]
        if len(c) < 100:
            break
        page += 1
    if not oldest:
        return None
    return (oldest["commit"]["committer"]["date"][:10],
            oldest.get("html_url"),
            oldest["commit"]["message"].splitlines()[0][:70])


def collect_by_path(fw, repo, m, verbose):
    """Date support by the first commit to the architecture's own implementation path."""
    entries = list_model_dir(repo, PER_MODEL_DIR[fw])
    if not entries:
        return None
    hit = None
    for cand in arch_candidates(m["architecture"]):
        if cand in entries:
            hit = entries[cand]
            break
    if not hit:  # longest-prefix fallback: 'qwen3_5' dir for 'Qwen3_5Moe...'
        for cand in arch_candidates(m["architecture"]):
            matches = sorted((k for k in entries if k and (cand.startswith(k) or k.startswith(cand))),
                             key=len, reverse=True)
            if matches:
                hit = entries[matches[0]]
                break
    if not hit:
        return None
    fc = first_commit_for_path(repo, hit)
    if not fc:
        return None
    d, url, msg = fc
    if verbose:
        print(f"      {hit} first commit {d}  {msg}")
    # Guard: a path far older than the model is a SHARED implementation (e.g. one
    # 'qwen' dir covering several generations), so its age says nothing about this
    # model. Fall back to PR search rather than report an inherited date.
    if (date.fromisoformat(m["release_date"]) - date.fromisoformat(d)).days > 240:
        if verbose:
            print(f"      ({hit} predates release by >240d - shared path, falling back)")
        return None
    return dict(state="supported", event_date=d, urls=[url],
                rule=f"{fw}:first-commit({hit})", fidelity="exact")


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
        # MUST paginate past the oldest cohort release date. A single page of 100
        # releases reaches only ~2025-11, which silently floor-clamps every older
        # model to the cache boundary: DeepSeek-V3 came back at exactly the floor
        # date and looked like a plausible +329d result.
        oldest_needed = min(m["release_date"] for m in models)
        rels, page = [], 1
        while page <= 30:
            _, batch = gh.get(f"repos/ollama/ollama/releases?per_page=100&page={page}")
            if not batch:
                break
            rels += batch
            got = min((r.get("published_at") or "9999")[:10] for r in batch)
            if got < oldest_needed:
                break
            page += 1
        gh.save_raw(rels, RAW / "releases", "ollama")
        rel_cache["ollama"] = rels
        floor = min((r.get("published_at") or "9999")[:10] for r in rels) if rels else "?"
        print(f"cached {len(rels)} ollama releases over {page} page(s); "
              f"oldest {floor} (need <= {oldest_needed})")
        if floor > oldest_needed:
            print(f"  WARNING: release history does not reach {oldest_needed}; "
                  f"models released before {floor} will be floor-clamped and must be "
                  f"recorded as unsupported-or-earlier, not as a date")

    lim, start_rem = gh.rate()
    rows = []
    # Resume support: a pair already collected for this snapshot is skipped, so an
    # interrupted run continues instead of restarting. Writes are per-pair below.
    done = {(r[0], r[1]) for r in con.execute(
        "SELECT framework_id, hf_id FROM support_events WHERE snapshot_date=?", (SNAP,))}
    if done:
        print(f"resuming: {len(done)} pairs already collected for {SNAP}")

    for m in models:
        print(f"\n{m['hf_id']}  (released {m['release_date']}, {m['support_kind']})", flush=True)
        for fw in fws:
            if (fw, m["hf_id"]) in done:
                print(f"   {fw:<13} (cached)", flush=True)
                continue
            try:
                if fw == "ollama":
                    r = collect_ollama(m, rel_cache["ollama"], a.verbose)
                else:
                    # Path history first (exact); PR search only as fallback, because
                    # search ranking over a popular term is unreliable - it put Qwen3
                    # in transformers at +530d when the real answer was -27d.
                    r = (collect_by_path(fw, repos[fw], m, a.verbose)
                         if fw in PER_MODEL_DIR else None)
                    if r is None and fw not in PER_MODEL_DIR:
                        # llama.cpp and TensorRT-LLM have no per-architecture file, so
                        # PR search is the only available method. Graded 'good'.
                        r = collect_code(fw, repos[fw], m, a.verbose)
                        if r:
                            r["fidelity"] = "good"
                    elif r is None:
                        # Path matched nothing, or matched a SHARED implementation whose
                        # age predates this model. PR search was tried here and proved
                        # actively harmful: it dated DeepSeek-V3.2 in SGLang from a
                        # GLM-5 MXFP4 pull request. A confident wrong date is worse
                        # than an admitted gap, so this is its own state and is
                        # excluded from metrics until a human resolves it.
                        hints = []
                        for term in search_terms(m)[:2]:
                            hints += [p["html_url"] for p in find_prs(repos[fw], term)[:3]]
                        r = dict(state="undetermined", event_date=None, urls=hints[:5],
                                 rule=f"{fw}:no-arch-path-match(needs hand resolution)",
                                 fidelity="none")
                        print(f"   {fw:<13} UNDETERMINED  no arch path; "
                              f"{len(hints)} PR hint(s) stored", flush=True)
                        rows.append((fw, m["hf_id"], r, None))
                        con.execute("""INSERT OR REPLACE INTO support_events(framework_id,
                            hf_id,state,event_date,days_to_support,evidence_rule,fidelity,
                            evidence_urls,snapshot_date) VALUES(?,?,?,?,?,?,?,?,?)""",
                            (fw, m["hf_id"], r["state"], None, None, r["rule"],
                             r["fidelity"], json.dumps(r["urls"]), SNAP))
                        con.commit()
                        continue
            except urllib.error.HTTPError as e:
                print(f"   {fw:<13} ERROR HTTP {e.code}", flush=True)
                continue
            if r is None:
                days = (date.fromisoformat(SNAP) - date.fromisoformat(m["release_date"])).days
                r = dict(state="unsupported", event_date=None, urls=[],
                         rule=f"{fw}:no-qualifying-artifact", fidelity="exact")
                print(f"   {fw:<13} unsupported  (censored at {days}d)", flush=True)
                d = None
            else:
                d = (date.fromisoformat(r["event_date"]) - date.fromisoformat(m["release_date"])).days
                tag = "DAY 0" if d == 0 else (f"{d:+d}d EARLY" if d < 0 else f"{d:+d}d")
                print(f"   {fw:<13} {r['state']:<10} {r['event_date']}  {tag:<10} {r['fidelity']}",
                      flush=True)
            rows.append((fw, m["hf_id"], r, d))
            if not a.dry_run:
                con.execute("""INSERT OR REPLACE INTO support_events(framework_id,hf_id,state,
                    event_date,days_to_support,evidence_rule,fidelity,evidence_urls,snapshot_date)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (fw, m["hf_id"], r["state"], r["event_date"], d, r["rule"], r["fidelity"],
                     json.dumps(r["urls"]), SNAP))
                con.commit()   # per pair: a 20-minute job must not lose everything on a crash

    if not a.dry_run:
        print(f"\nwrote {len(rows)} support_events this run")
    lim, rem = gh.rate()
    print(f"api calls used: {start_rem - rem} | remaining {rem}/{lim}")


if __name__ == "__main__":
    main()
