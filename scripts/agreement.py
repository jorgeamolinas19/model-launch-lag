#!/usr/bin/env python3
"""Inter-classifier agreement when no gold labels exist yet.

Compares two label sources on the issues both have labelled: raw agreement, Cohen's
kappa, and where they disagree. This is NOT accuracy - neither side is ground truth -
but it bounds how much the LLM is adding over keyword rules, and it shows which
category boundaries the two methods read differently, which is exactly where hand
labels are worth the most.

  agreement.py --a regex_baseline --b llm
"""
import argparse
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
CATS = ["missing_feature", "install_build", "template_tokenizer", "quantization",
        "speculative_decoding", "oom_hardware", "correctness", "performance", "other"]


def kappa(a, b):
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="regex_baseline")
    ap.add_argument("--b", default="llm")
    a = ap.parse_args()
    con = sqlite3.connect(DB, timeout=60)
    la = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT issue_id, category_primary, severity FROM labels WHERE source=? AND category_primary IS NOT NULL", (a.a,))}
    lb = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT issue_id, category_primary, severity FROM labels WHERE source=? AND category_primary IS NOT NULL", (a.b,))}
    ids = sorted(set(la) & set(lb))
    if not ids:
        raise SystemExit("no overlap")
    ca = [la[i][0] for i in ids]; cb = [lb[i][0] for i in ids]
    sa = [la[i][1] for i in ids]; sb = [lb[i][1] for i in ids]
    print(f"{a.a} vs {a.b}: n={len(ids)}")
    print(f"  category agreement {100*sum(x==y for x,y in zip(ca,cb))/len(ids):.1f}%  kappa {kappa(ca,cb):.2f}")
    print(f"  severity agreement {100*sum(x==y for x,y in zip(sa,sb))/len(ids):.1f}%  kappa {kappa(sa,sb):.2f}")
    print(f"\n  {'category':<22}{a.a[:8]:>9}{a.b[:8]:>9}")
    da, db_ = Counter(ca), Counter(cb)
    for c in CATS:
        print(f"  {c:<22}{da[c]:>9}{db_[c]:>9}")
    print("\n  largest disagreements (A -> B):")
    cm = Counter((x, y) for x, y in zip(ca, cb) if x != y)
    for (x, y), n in cm.most_common(8):
        print(f"    {x:<20} -> {y:<20} {n}")
    run = con.execute("SELECT notes FROM runs WHERE run_id LIKE ? ORDER BY started_at DESC LIMIT 1",
                      (f"{a.b}-%",)).fetchone()
    if run:
        print(f"\n  run notes: {run[0][-160:]}")


if __name__ == "__main__":
    main()
