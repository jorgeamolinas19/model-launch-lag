#!/usr/bin/env python3
"""Classify issues with an open model through any OpenAI-compatible endpoint.

Works unchanged against Ollama (local CPU dev loop), vLLM on a rented/free GPU (full
batch), or a NIM endpoint. The prompt is pinned in prompts/classifier_<ver>.md and the
exact model tag is recorded per run, so any label can be reproduced.

  classify_llm.py --model qwen3:4b --split dev            # dev loop only
  classify_llm.py --model qwen3:4b --all                   # full batch
  classify_llm.py --base-url http://host:8000/v1 --model Qwen/Qwen3-8B --all

Writes labels with source='llm' and the run_id; a second model can be stored under
source='llm:<model>' for the classifier benchmark.
"""
import argparse
import json
import os
import re
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
CODEBOOK = "v2"
CATS = {"missing_feature", "install_build", "template_tokenizer", "quantization",
        "speculative_decoding", "oom_hardware", "correctness", "performance", "other"}
SEVS = {"blocker", "degraded", "minor"}


def load_prompt(ver):
    text = (ROOT / "prompts" / f"classifier_{ver}.md").read_text()
    return text.split("---", 1)[1].strip()   # drop the header block


def chat(base_url, model, prompt, api_key, timeout=600):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "temperature": 0, "max_tokens": 300,
            "response_format": {"type": "json_object"}}
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key or 'none'}"}
    req = urllib.request.Request(f"{base_url.rstrip('/')}/chat/completions",
                                 data=json.dumps(body).encode(), headers=h)
    r = urllib.request.urlopen(req, timeout=timeout)
    d = json.load(r)
    return d["choices"][0]["message"]["content"], d.get("usage", {})


def parse(text):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    p = str(d.get("category_primary", "")).strip().lower()
    if p not in CATS:
        return None
    sev = str(d.get("severity", "")).strip().lower()
    if sev not in SEVS:
        return None
    sec = [s for s in (d.get("category_secondary") or []) if s in CATS and s != p][:2]
    return p, sec, sev, str(d.get("reason", ""))[:200]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"))
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", ""))
    ap.add_argument("--prompt-version", default="v1")
    ap.add_argument("--split", choices=["dev", "test"], help="only issues in this labeled split")
    ap.add_argument("--all", action="store_true", help="every non-excluded issue")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--source", default="llm", help="labels.source to write under")
    a = ap.parse_args()

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    tmpl = load_prompt(a.prompt_version)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    run_id = f"{a.source}-{a.model.replace('/', '_').replace(':', '-')}-{a.prompt_version}-{now[:16]}"
    con.execute("""INSERT OR REPLACE INTO runs(run_id, started_at, snapshot_date, codebook_version,
                   classifier_model, prompt_version, repo_commit, notes) VALUES(?,?,?,?,?,?,?,?)""",
                (run_id, now, now[:10], CODEBOOK, a.model, a.prompt_version, sha, a.base_url))
    con.commit()

    if a.split:
        q = """SELECT i.* FROM issues i JOIN labels l ON l.issue_id=i.id AND l.source='hand'
               AND l.split=? WHERE i.excluded=0 ORDER BY i.id"""
        issues = [dict(r) for r in con.execute(q, (a.split,))]
    elif a.all:
        issues = [dict(r) for r in con.execute("SELECT * FROM issues WHERE excluded=0 ORDER BY id")]
    else:
        sys.exit("pass --split dev|test or --all")
    done = {r[0] for r in con.execute(
        "SELECT issue_id FROM labels WHERE source=? AND codebook_version=?", (a.source, CODEBOOK))}
    issues = [i for i in issues if i["id"] not in done]
    if a.limit:
        issues = issues[:a.limit]
    print(f"run {run_id}\n{len(issues)} issues to classify via {a.base_url} ({a.model})\n", flush=True)

    ok = bad = 0
    t0 = time.time()
    tok_in = tok_out = 0
    for n, i in enumerate(issues, 1):
        prompt = tmpl.format(framework=i["framework_id"], model=i["hf_id"], title=i["title"] or "",
                             labels=i["labels"] or "[]", body=(i["body_excerpt"] or "")[:3500])
        try:
            text, usage = chat(a.base_url, a.model, prompt, a.api_key)
        except (urllib.error.URLError, TimeoutError, KeyError) as e:
            print(f"  [{n}] #{i['number']} endpoint error: {e}", flush=True)
            time.sleep(3)
            continue
        tok_in += usage.get("prompt_tokens", 0)
        tok_out += usage.get("completion_tokens", 0)
        parsed = parse(text)
        if not parsed:
            bad += 1
            print(f"  [{n}] #{i['number']} unparseable: {text[:80]!r}", flush=True)
            continue
        p, sec, sev, reason = parsed
        con.execute("""INSERT OR REPLACE INTO labels(issue_id, source, codebook_version, category_primary,
                       category_secondary, severity, reason, labeled_at, run_id) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (i["id"], a.source, CODEBOOK, p, json.dumps(sec), sev, reason,
                     datetime.now(timezone.utc).isoformat(timespec="seconds"), run_id))
        con.commit()
        ok += 1
        if n % 10 == 0 or n == len(issues):
            el = time.time() - t0
            print(f"  [{n}/{len(issues)}] {ok} ok, {bad} bad | {el/ n:.1f}s/issue | "
                  f"{tok_in/ max(el,1):.0f} in-tok/s", flush=True)

    el = time.time() - t0
    con.execute("UPDATE runs SET notes = notes || ? WHERE run_id=?",
                (f" | {ok} labelled, {bad} unparseable, {el:.0f}s, {tok_in} in / {tok_out} out tokens", run_id))
    con.commit()
    print(f"\ndone: {ok} labelled, {bad} unparseable, {el:.0f}s total, "
          f"{(el/ok if ok else 0):.1f}s per issue")


if __name__ == "__main__":
    main()
