#!/usr/bin/env python3
"""Collect first-30-day issues per (framework, model) and match them to models.

Question 2 input. For each cohort model and each framework repo, searches issues created
in [release_date, release_date + 30d] for the model's aliases, highest-confidence first:

  arch_class  the HF architecture string - appears verbatim in "architecture not
              supported" errors and registry entries; near-zero false positives
  slug        the repo short name, e.g. "Qwen3.5-27B"
  loose       the family name, e.g. "qwen3.5" - high recall, catches passing mentions

match_kind records which alias matched, so the cleaning step can exclude weak matches
and the writeup can state the confidence mix. Raw search responses are stored gzipped
per (framework, model) so matching can be redone without re-fetching.

Resumable: pairs with a raw file for this snapshot are skipped.
"""
import argparse
import gzip
import json
import re
import sqlite3
import sys
import time
import tomllib
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
SNAP = datetime.now(timezone.utc).date().isoformat()
RAW = ROOT / "raw" / "github" / SNAP / "issues"
DB = ROOT / "db" / "launch_lag.sqlite"
WINDOW_DAYS = 30
SEARCH_PAUSE = 2.1          # 30 searches/min authenticated
BOT_RE = re.compile(r"\[bot\]$|^(dependabot|github-actions|stale|mergify|codecov|renovate)", re.I)
TRACEBACK_RE = re.compile(r"(Traceback \(most recent call last\):.*?)(?:\n\n|\Z)", re.S)


def aliases(m):
    """(term, match_kind) highest-confidence first."""
    out = []
    if m["architecture"]:
        out.append((m["architecture"], "arch_class"))
    short = m["hf_id"].split("/", 1)[1]
    out.append((short, "slug"))
    base = re.sub(r"-(instruct|it|base|chat|think|bf16|fp8)$", "", short, flags=re.I)
    if base.lower() != short.lower():
        out.append((base, "slug"))
    fam = m["family"]
    if fam.lower() not in {t.lower() for t, _ in out}:
        out.append((fam, "loose"))
    return out


def search_all(q, cap=1000):
    """Walk every page of a search; GitHub caps at 1000 results."""
    items, page = [], 1
    while len(items) < cap:
        url = f"search/issues?q={urllib.parse.quote(q)}&per_page=100&page={page}&sort=created&order=asc"
        try:
            _, d = gh.get(url)
        except urllib.error.HTTPError as e:
            if e.code == 422:        # past page 10 / malformed
                break
            raise
        time.sleep(SEARCH_PAUSE)
        batch = d.get("items", [])
        items += batch
        if len(batch) < 100:
            break
        page += 1
    return items


def excerpt(body, limit=2000):
    """What the classifier sees: first traceback plus the first `limit` chars."""
    body = body or ""
    tb = TRACEBACK_RE.search(body)
    head = body[:limit]
    if tb and tb.group(1) not in head:
        return (head + "\n\n[traceback]\n" + tb.group(1)[:1500]).strip()
    return head.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="")
    ap.add_argument("--frameworks", default="")
    a = ap.parse_args()

    cohort = tomllib.loads((ROOT / "cohort.toml").read_text())
    repos = {k: v["repo"] for k, v in cohort["frameworks"].items()}
    con = sqlite3.connect(DB, timeout=60)
    con.execute("PRAGMA busy_timeout=60000")   # a concurrent reader killed a 2h run once
    con.row_factory = sqlite3.Row
    models = [dict(r) for r in con.execute(
        "SELECT hf_id, family, architecture, release_date FROM models ORDER BY release_date")]
    if a.models:
        models = [m for m in models if a.models.lower() in (m["hf_id"] + m["family"]).lower()]
    fws = [f for f in repos if not a.frameworks or a.frameworks in f]

    lim, rem0 = gh.rate()
    total_new = 0
    for m in models:
        rel = date.fromisoformat(m["release_date"])
        end = rel + timedelta(days=WINDOW_DAYS)
        if end > date.fromisoformat(SNAP):
            print(f"\n{m['hf_id']}  window not yet closed ({end}) - skipped", flush=True)
            continue
        print(f"\n{m['hf_id']}  window {rel}..{end}", flush=True)
        for fw in fws:
            rawf = RAW / f"{fw}__{m['hf_id'].replace('/', '__')}.json.gz"
            if rawf.is_file():
                hits = json.load(gzip.open(rawf, "rt"))
            else:
                hits = {}   # issue id -> (item, best match_kind, matched_term)
                rank = {"arch_class": 0, "slug": 1, "loose": 2}
                for term, kind in aliases(m):
                    q = f'repo:{repos[fw]} is:issue created:{rel}..{end} "{term}"'
                    for it in search_all(q):
                        k = str(it["id"])
                        if k not in hits or rank[kind] < rank[hits[k]["kind"]]:
                            hits[k] = {"item": it, "kind": kind, "term": term}
                rawf.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(rawf, "wt", encoding="utf-8") as fh:
                    json.dump(hits, fh)

            n = 0
            for k, h in hits.items():
                it = h["item"]
                if "pull_request" in it:
                    continue
                user = it.get("user") or {}
                is_bot = int(user.get("type") == "Bot" or bool(BOT_RE.search(user.get("login") or "")))
                body = it.get("body") or ""
                con.execute("""INSERT OR REPLACE INTO issues(id, framework_id, number, url, title,
                    body_excerpt, is_pr, author_login, author_is_bot, labels, created_at,
                    closed_at, state_reason, has_traceback, comment_count, reactions, hf_id,
                    family, match_kind, snapshot_date)
                    VALUES(?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (it["id"], fw, it["number"], it["html_url"], it.get("title"),
                     excerpt(body), user.get("login"), is_bot,
                     json.dumps([l["name"] for l in it.get("labels", [])]),
                     it.get("created_at"), it.get("closed_at"), it.get("state_reason"),
                     int("Traceback (most recent call last)" in body or "Error:" in body),
                     it.get("comments", 0), (it.get("reactions") or {}).get("total_count", 0),
                     m["hf_id"], m["family"], h["kind"], SNAP))
                n += 1
            con.commit()
            total_new += n
            kinds = {}
            for h in hits.values():
                kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
            print(f"   {fw:<13} {n:>4} issues  {kinds}", flush=True)

    lim, rem = gh.rate()
    print(f"\nissues written: {total_new} | api calls {rem0 - rem} | remaining {rem}/{lim}")


if __name__ == "__main__":
    main()
