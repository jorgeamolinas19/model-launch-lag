#!/usr/bin/env python3
"""Apply negative_offsets_adjudicated.csv, and enforce the standard it establishes.

The standard: architecture presence is not proof of checkpoint compatibility, and a
negative offset is never silently converted to zero. Zero asserts the model was
runnable at launch; that needs its own evidence.

Consequence applied globally here: every `arch_compatible` pair has
days_to_support set to NULL rather than 0. Those pairs still count toward coverage,
but they contribute NO latency value to any median - previously they entered as day 0,
which quietly asserted launch-day support for 25 pairs on architecture evidence alone.
"""
import csv
import json
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
CSV_PATH = ROOT / "negative_offsets_adjudicated.csv"


def main():
    rows = list(csv.DictReader(
        l for l in CSV_PATH.read_text().splitlines() if not l.startswith("#")))
    con = sqlite3.connect(DB)

    print("APPLYING ADJUDICATIONS\n")
    for r in rows:
        fw, hf = r["framework"], r["hf_id"]
        rel = con.execute("SELECT release_date FROM models WHERE hf_id=?", (hf,)).fetchone()
        if not rel:
            print(f"  !! unknown model {hf}")
            continue
        rel = rel[0]
        dec = r["decision"]
        url = json.dumps([r["evidence_url"]]) if r["evidence_url"] else "[]"

        if dec == "predecessor_architecture":
            con.execute("""UPDATE support_events SET state='arch_compatible',
                event_date=NULL, days_to_support=NULL, fidelity='exact',
                evidence_rule=?, evidence_urls=? WHERE framework_id=? AND hf_id=?""",
                (f"{fw}:predecessor-architecture(adjudicated; not checkpoint support)",
                 url, fw, hf))
            print(f"  {fw:<13}{hf[:40]:<41} arch_compatible, no latency value")
        elif dec == "model_specific_merge":
            ev = r["corrected_event_date"]
            d = (date.fromisoformat(ev) - date.fromisoformat(rel)).days
            con.execute("""UPDATE support_events SET state='supported', event_date=?,
                days_to_support=?, fidelity='exact', evidence_rule=?, evidence_urls=?
                WHERE framework_id=? AND hf_id=?""",
                (ev, d, f"{fw}:model-specific-pr(adjudicated, merge date verified)",
                 url, fw, hf))
            print(f"  {fw:<13}{hf[:40]:<41} supported {ev}  {d:+d}d "
                  f"(vs release_date {rel})")
        elif dec == "reject_pending_merge":
            con.execute("""UPDATE support_events SET state='undetermined',
                event_date=NULL, days_to_support=NULL, fidelity='none',
                evidence_rule=?, evidence_urls=? WHERE framework_id=? AND hf_id=?""",
                (f"{fw}:negative-offset-rejected(adjudicated; awaiting merge evidence)",
                 url, fw, hf))
            print(f"  {fw:<13}{hf[:40]:<41} undetermined (negative offset rejected)")
    con.commit()

    # Enforce the standard globally.
    n = con.execute("""UPDATE support_events SET days_to_support=NULL
                       WHERE state='arch_compatible' AND days_to_support IS NOT NULL""").rowcount
    con.commit()
    print(f"\ncleared day-0 latency claims from {n} arch_compatible pairs")
    print("  (architecture presence counts toward coverage, never toward a median)")

    print("\nstate distribution:")
    for s, f, c in con.execute(
            "SELECT state, fidelity, count(*) FROM support_events GROUP BY 1,2 ORDER BY 3 DESC"):
        print(f"  {s:<16}{f:<8}{c}")


if __name__ == "__main__":
    main()
