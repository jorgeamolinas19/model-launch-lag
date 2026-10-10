#!/usr/bin/env python3
"""Apply release_dates_hand.csv over API-derived dates, and report the API rule's error.

Run after verify_cohort.py. Overrides live in the CSV rather than the database so a
re-verification cannot silently revert them.
"""
import csv
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_columns(con):
    cols = {r[1] for r in con.execute("PRAGMA table_info(models)")}
    for name, decl in (("announced_at", "TEXT"), ("release_source_url", "TEXT"),
                       ("release_note", "TEXT")):
        if name not in cols:
            con.execute(f"ALTER TABLE models ADD COLUMN {name} {decl}")
    con.commit()


def main():
    lines = [l for l in (ROOT / "release_dates_hand.csv").read_text().splitlines()
             if not l.startswith("#")]
    rows = list(csv.DictReader(lines))
    con = sqlite3.connect(ROOT / "db" / "launch_lag.sqlite")
    ensure_columns(con)

    print(f"{'model':<34} {'api-derived':<12} {'hand':<12} {'delta':>7}  prior method")
    print("-" * 88)
    deltas, missing_src = [], []
    for r in rows:
        cur = con.execute(
            "SELECT release_date, release_date_method FROM models WHERE hf_id=?",
            (r["hf_id"],)).fetchone()
        if not cur:
            print(f"  !! not in cohort: {r['hf_id']}")
            continue
        d = (date.fromisoformat(r["release_date"]) - date.fromisoformat(cur[0])).days
        deltas.append(abs(d))
        print(f"{r['hf_id']:<34} {cur[0]:<12} {r['release_date']:<12} {d:>+7}  {cur[1]}")
        if not r.get("source_url"):
            missing_src.append(r["hf_id"])
        con.execute("""UPDATE models SET release_date=?, announced_at=?,
                       release_source_url=?, release_note=?,
                       release_date_method='hand_resolved', release_date_uncertain=0
                       WHERE hf_id=?""",
                    (r["release_date"], r.get("announced_at") or r["release_date"],
                     r.get("source_url") or None, r.get("note") or None, r["hf_id"]))
    con.commit()

    # Announced-before-weights gaps: hosted or announced availability ahead of a
    # downloadable checkpoint. A framework cannot act on weights that do not exist, so
    # this gap belongs in the writeup rather than inside days_to_support.
    gaps = list(con.execute("""SELECT hf_id, announced_at, release_date,
                   julianday(release_date) - julianday(announced_at) g
                   FROM models WHERE announced_at IS NOT NULL AND g > 0 ORDER BY g DESC"""))
    if gaps:
        print("\nANNOUNCED BEFORE WEIGHTS (reported separately, not folded into latency)")
        for hf_id, ann, rel, g in gaps:
            print(f"  {hf_id:<46} announced {ann} -> weights {rel}  (+{int(g)}d)")

    if deltas:
        deltas.sort()
        print(f"\nAPI-rule error on the flagged subset: median {deltas[len(deltas)//2]} d, "
              f"max {max(deltas)} d, n={len(deltas)}")
    n = con.execute("SELECT count(*) FROM models WHERE release_date_uncertain=1").fetchone()[0]
    tot, hand = con.execute(
        "SELECT count(*), sum(release_date_method='hand_resolved') FROM models").fetchone()
    print(f"still flagged uncertain: {n} | hand_resolved: {hand}/{tot}")
    if missing_src:
        print("\nBLOCKS PUBLICATION - no source_url yet (methods page must cite each):")
        for m in missing_src:
            print(f"  {m}")


if __name__ == "__main__":
    main()
