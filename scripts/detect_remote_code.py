#!/usr/bin/env python3
"""Does each model ship its own modeling code (trust_remote_code)?

This is the companion to native `transformers` support. A model that ships
modeling_*.py plus an auto_map is runnable in transformers on DAY 0, so reporting only
the native-support date overstates the real wait: DeepSeek-V3 reads as +93 days to
transformers support when it was in fact usable at release, just not natively.

Reads the cached raw Hub responses, so it needs no network and no credentials.
"""
import gzip
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"


def detect(meta):
    """Return (ships_remote_code, evidence)."""
    cfg = meta.get("config") or {}
    if cfg.get("auto_map"):
        return 1, "config.auto_map"
    sibs = [s.get("rfilename", "") for s in (meta.get("siblings") or [])]
    mods = [s for s in sibs if s.startswith("modeling_") and s.endswith(".py")]
    if mods:
        return 1, f"ships {mods[0]}"
    # A custom code repo may also carry configuration_*.py / processing_*.py
    customs = [s for s in sibs if s.endswith(".py") and s.split("/")[-1].startswith(
        ("configuration_", "processing_", "image_processing_", "tokenization_"))]
    if customs:
        return 1, f"ships {customs[0]}"
    return 0, "no custom modeling code"


def ensure_column(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(models)")}
    for name, decl in (("ships_remote_code", "INTEGER"), ("remote_code_evidence", "TEXT")):
        if name not in cols:
            con.execute(f"ALTER TABLE models ADD COLUMN {name} {decl}")
    con.commit()


def run():
    snaps = sorted((ROOT / "raw" / "hub").glob("*/models"))
    if not snaps:
        sys.exit("no cached hub responses; run verify_cohort.py first")
    raw_dir = snaps[-1]
    con = sqlite3.connect(DB)
    ensure_column(con)

    rows = []
    for hf_id, in con.execute("SELECT hf_id FROM models ORDER BY release_date"):
        f = raw_dir / f"{hf_id.replace('/', '__')}.json.gz"
        if not f.is_file():
            print(f"  (no cached metadata for {hf_id})")
            continue
        meta = json.load(gzip.open(f, "rt"))
        flag, ev = detect(meta)
        con.execute("UPDATE models SET ships_remote_code=?, remote_code_evidence=? WHERE hf_id=?",
                    (flag, ev, hf_id))
        rows.append((hf_id, flag, ev))
    con.commit()

    n = sum(f for _, f, _ in rows)
    print(f"{'model':<46}{'remote_code':>12}  evidence")
    print("-" * 92)
    for hf_id, flag, ev in rows:
        print(f"{hf_id[:45]:<46}{('DAY 0' if flag else 'no'):>12}  {ev}")
    print(f"\n{n}/{len(rows)} models runnable in transformers at release via trust_remote_code")

    # The headline this closes: native-only latency overstates the real wait.
    q = """SELECT m.hf_id, s.days_to_support FROM models m
           JOIN support_events s ON s.hf_id=m.hf_id AND s.framework_id='transformers'
           WHERE m.ships_remote_code=1 AND s.days_to_support > 14
           ORDER BY s.days_to_support DESC"""
    over = list(con.execute(q))
    if over:
        print("\nMODELS WHERE NATIVE-ONLY LATENCY IS MISLEADING")
        print("(usable at release via remote code; the native date is a separate milestone)")
        for hf_id, d in over:
            print(f"  {hf_id:<46} native +{d}d, but remote_code day 0")


if __name__ == "__main__":
    run()
