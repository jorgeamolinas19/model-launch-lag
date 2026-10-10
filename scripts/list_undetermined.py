#!/usr/bin/env python3
"""Emit the hand-resolution worklist for `undetermined` support pairs.

Writes support_events_hand.csv (fillable) and prints a readable table with the stored
PR candidates and why the automated method declined. Mirrors release_dates_hand.csv:
overrides live in the CSV so a re-collection cannot silently revert them.
"""
import csv
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
OUT = ROOT / "support_events_hand.csv"

HEADER = ["framework_id", "hf_id", "architecture", "release_date", "event_date",
          "state", "source_url", "confidence", "conflict", "resolved_by", "resolved_at"]


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT s.framework_id, s.hf_id, s.evidence_rule, s.evidence_urls,
               m.architecture, m.release_date, m.support_kind, m.band
        FROM support_events s JOIN models m USING(hf_id)
        WHERE s.state='undetermined'
        ORDER BY m.release_date, s.framework_id""")]
    if not rows:
        print("no undetermined pairs")
        return

    existing = {}
    if OUT.is_file():
        for r in csv.DictReader(l for l in OUT.read_text().splitlines()
                                if not l.startswith("#")):
            existing[(r["framework_id"], r["hf_id"])] = r

    with OUT.open("w", newline="") as fh:
        fh.write("# Hand-resolution worklist for undetermined support pairs.\n")
        fh.write("# Fill event_date (YYYY-MM-DD) + source_url + confidence "
                 "(high|medium|low).\n")
        fh.write("# Set state to: supported | partial | unsupported | not_applicable\n")
        fh.write("#   not_applicable = the framework structurally cannot serve this "
                 "model class.\n")
        fh.write("#   unsupported    = genuinely absent (becomes a censored observation).\n")
        fh.write("# Leave a row blank to keep it excluded from all metrics.\n")
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            prev = existing.get((r["framework_id"], r["hf_id"]), {})
            w.writerow({"framework_id": r["framework_id"], "hf_id": r["hf_id"],
                        "architecture": r["architecture"] or "",
                        "release_date": r["release_date"],
                        "event_date": prev.get("event_date", ""),
                        "state": prev.get("state", ""),
                        "source_url": prev.get("source_url", ""),
                        "confidence": prev.get("confidence", ""),
                        "conflict": prev.get("conflict", ""),
                        "resolved_by": prev.get("resolved_by", ""),
                        "resolved_at": prev.get("resolved_at", "")})

    print(f"UNDETERMINED PAIRS - {len(rows)} needing hand resolution")
    print(f"worklist written to {OUT.name}\n")
    by_model = {}
    for r in rows:
        by_model.setdefault((r["release_date"], r["hf_id"], r["architecture"]), []).append(r)
    for (rd, hf, arch), rs in sorted(by_model.items()):
        print(f"{hf}   released {rd}   {arch}")
        for r in rs:
            hints = json.loads(r["evidence_urls"] or "[]")
            why = ("no file or directory in the framework matching this architecture"
                   if "no-arch-path-match" in (r["evidence_rule"] or "") else r["evidence_rule"])
            print(f"   {r['framework_id']:<13} {why}")
            for h in hints:
                print(f"        candidate: {h}")
            if not hints:
                print("        (no candidate PRs found by search either)")
        print()
    print("Likely reasons a pair lands here, for triage:")
    print("  1. Shared implementation - one file covers several model generations, so")
    print("     its first commit predates this model and says nothing about it.")
    print("  2. Architecture genuinely unsupported - the honest answer is 'unsupported',")
    print("     which becomes a censored observation rather than a missing row.")
    print("  3. Structurally out of scope - e.g. a diffusion LM in an autoregressive-only")
    print("     server, or a draft model where the framework has no speculative path.")
    print("     Mark these not_applicable so they leave the denominator with a reason.")


if __name__ == "__main__":
    main()
