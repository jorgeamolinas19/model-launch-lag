#!/usr/bin/env python3
"""Apply support_events_hand.csv over the collected support_events.

Hand (or disclosed assistant) adjudications are authoritative over automated results.
Lives in the CSV so a re-collection cannot silently revert them. Rows with state
`undetermined` are applied too, so their evidence URL and note are preserved.
"""
import csv
import json
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
CSV = ROOT / "support_events_hand.csv"


def main():
    rows = list(csv.DictReader(l for l in CSV.read_text().splitlines() if not l.startswith("#")))
    con = sqlite3.connect(DB, timeout=60)
    n = 0
    for r in rows:
        if not r.get("state"):
            continue
        rel = con.execute("SELECT release_date FROM models WHERE hf_id=?", (r["hf_id"],)).fetchone()
        if not rel:
            print(f"  !! unknown model {r['hf_id']}")
            continue
        ev = r.get("event_date") or None
        days = (date.fromisoformat(ev) - date.fromisoformat(rel[0])).days if ev else None
        if r["state"] == "arch_compatible":
            days = None   # architecture presence carries no latency value
        con.execute("""UPDATE support_events SET state=?, event_date=?, days_to_support=?,
            fidelity=?, evidence_rule=?, evidence_urls=?, verified_by=?, verified_at=?
            WHERE framework_id=? AND hf_id=?""",
            (r["state"], ev, days, r.get("fidelity") or "none",
             f"{r['framework_id']}:hand({r.get('confidence','?')} confidence) {r.get('conflict','')[:160]}",
             json.dumps([r["source_url"]] if r.get("source_url") else []),
             r.get("resolved_by"), r.get("resolved_at"), r["framework_id"], r["hf_id"]))
        tag = (f"{days:+d}d" if days is not None else "")
        print(f"  {r['framework_id']:<13}{r['hf_id'][:42]:<43}{r['state']:<16}{ev or '':<11}{tag}")
        n += 1
    con.commit()
    print(f"\napplied {n} adjudications")
    for s, c in con.execute("SELECT state, count(*) FROM support_events GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {s:<16}{c}")


if __name__ == "__main__":
    main()
