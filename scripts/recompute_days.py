#!/usr/bin/env python3
"""Recompute support_events.days_to_support from current release dates.

Required after any change to a release date (a verify_cohort re-run, or a new row in
release_dates_hand.csv). days_to_support is stored, so a changed release date leaves
stale derived values behind - and a one-day drift is enough to turn a day-0 launch into
a +1d lag in the headline.

Run order after any date change:
  verify_cohort.py  ->  apply_hand_dates.py  ->  recompute_days.py
"""
import sqlite3
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"


def main():
    con = sqlite3.connect(DB)
    rows = list(con.execute("""
        SELECT s.framework_id, s.hf_id, s.event_date, s.days_to_support, m.release_date, s.state
        FROM support_events s JOIN models m USING(hf_id)"""))
    changed = 0
    for fw, hf_id, event, stored, rel, state in rows:
        want = None
        # arch_compatible carries NO latency value by adjudication standard (a declared
        # architecture is not proof the checkpoint ran); never re-derive one for it.
        if event and rel and state != "arch_compatible":
            want = (date.fromisoformat(event) - date.fromisoformat(rel)).days
        if want != stored:
            con.execute("UPDATE support_events SET days_to_support=? "
                        "WHERE framework_id=? AND hf_id=?", (want, fw, hf_id))
            changed += 1
            print(f"  {fw:<14}{hf_id:<46}{stored} -> {want}")
    con.commit()
    print(f"\n{changed} of {len(rows)} support_events updated")
    if not changed:
        print("  (all derived values already consistent with release dates)")


if __name__ == "__main__":
    main()
