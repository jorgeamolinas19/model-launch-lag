#!/usr/bin/env python3
"""Import hand labels and score every classifier against them.

  eval_classifier.py --import labels/sample_v2_worksheet.csv   # load filled worksheet
  eval_classifier.py --split test                              # score on held-out test
  eval_classifier.py --split dev                               # (prompt iteration only)

Reports, per classifier source: overall accuracy, per-category precision/recall, a
confusion matrix, severity accuracy, and Cohen's kappa vs hand labels. If a second hand
pass exists (source='hand_pass2') it reports self-agreement kappa - the ceiling no
classifier can meaningfully beat.

Also writes labels/labels_v2.csv: the PUBLISHED set (url, labels, split - no issue text).
"""
import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
CATS = ["missing_feature", "install_build", "template_tokenizer", "quantization",
        "speculative_decoding", "oom_hardware", "correctness", "performance", "other"]
SEVS = ["blocker", "degraded", "minor"]
GOLD = "hand"   # overridden by --gold


def kappa(a, b):
    """Cohen's kappa for two equal-length label sequences."""
    n = len(a)
    if n == 0:
        return None
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def import_worksheet(con, path, source="hand"):
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = skipped = 0
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            cat = (r.get("category_primary") or "").strip().lower()
            sev = (r.get("severity") or "").strip().lower()
            if cat not in CATS or sev not in SEVS:
                skipped += 1
                continue
            sec = [s.strip().lower() for s in (r.get("category_secondary") or "").split(";") if s.strip() in CATS]
            con.execute("""INSERT OR REPLACE INTO labels(issue_id, source, codebook_version, category_primary,
                           category_secondary, severity, reason, split, labeled_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (int(r["issue_id"]), source, "v2", cat, json.dumps(sec), sev,
                         (r.get("reason") or "")[:200], r.get("split"), now))
            n += 1
    con.commit()
    print(f"imported {n} {source} labels from {path} ({skipped} rows blank or invalid)")


def publish(con):
    out = ROOT / "labels" / "labels_v2.csv"
    out.parent.mkdir(exist_ok=True)
    rows = con.execute("""SELECT i.url, i.framework_id, i.hf_id, l.split, l.category_primary,
                          l.category_secondary, l.severity, l.reason, l.codebook_version
                          FROM labels l JOIN issues i ON i.id=l.issue_id
                          WHERE l.source='hand' AND l.category_primary IS NOT NULL ORDER BY i.url""").fetchall()
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["issue_url", "framework", "model", "split", "category_primary", "category_secondary",
                    "severity", "reason", "codebook_version"])
        for r in rows:
            w.writerow(r)
    print(f"published {len(rows)} hand labels -> {out.relative_to(ROOT)} (urls + labels only; CC BY 4.0)")


def score(con, split, source):
    # split lives on the 'hand' seed rows; the gold source may be a different table slice.
    # Issues excluded AFTER sampling (e.g. by a tightened attribution rule) drop out of
    # the gold set here, so a bad attribution never counts for or against a classifier.
    gold = {r[0]: (r[1], r[2]) for r in con.execute(
        """SELECT g.issue_id, g.category_primary, g.severity FROM labels g
           JOIN labels h ON h.issue_id=g.issue_id AND h.source='hand' AND h.split=?
           WHERE g.source=? AND g.category_primary IS NOT NULL
             AND EXISTS (SELECT 1 FROM issues i WHERE i.id=g.issue_id AND i.excluded=0)""",
        (split, GOLD))}
    dropped = con.execute(
        """SELECT count(*) FROM labels h WHERE h.source='hand' AND h.split=?
           AND NOT EXISTS (SELECT 1 FROM issues i WHERE i.id=h.issue_id AND i.excluded=0)""",
        (split,)).fetchone()[0]
    if dropped:
        print(f"\n  ({dropped} sampled {split} issue(s) excluded after sampling by the cleaning rules; "
              f"not scored)")
    pred = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT issue_id, category_primary, severity FROM labels WHERE source=? AND category_primary IS NOT NULL",
        (source,))}
    ids = sorted(set(gold) & set(pred))
    if not ids:
        print(f"\n[{source}] no overlap with hand '{split}' labels")
        return
    g = [gold[i][0] for i in ids]
    p = [pred[i][0] for i in ids]
    gs = [gold[i][1] for i in ids]
    ps = [pred[i][1] for i in ids]
    acc = sum(x == y for x, y in zip(g, p)) / len(ids)
    print(f"\n=== {source}  vs {GOLD} ({split}, n={len(ids)}) ===")
    print(f"  category accuracy {100*acc:.1f}%   kappa {kappa(g, p):.2f}")
    print(f"  severity accuracy {100*sum(x == y for x, y in zip(gs, ps))/len(ids):.1f}%   kappa {kappa(gs, ps):.2f}")

    print(f"\n  {'category':<22}{'n':>4}{'prec':>7}{'rec':>7}")
    for c in CATS:
        tp = sum(1 for x, y in zip(g, p) if x == c and y == c)
        fp = sum(1 for x, y in zip(g, p) if x != c and y == c)
        fn = sum(1 for x, y in zip(g, p) if x == c and y != c)
        n = tp + fn
        if n == 0 and fp == 0:
            continue
        prec = tp / (tp + fp) if tp + fp else 0
        rec = tp / n if n else 0
        warn = "  (n<10: unreliable)" if n < 10 else ""
        print(f"  {c:<22}{n:>4}{100*prec:>6.0f}%{100*rec:>6.0f}%{warn}")

    print(f"\n  confusion (rows = {GOLD}, cols = predicted):")
    short = [c[:5] for c in CATS]
    print("  " + " " * 22 + "".join(f"{s:>6}" for s in short))
    cm = defaultdict(Counter)
    for x, y in zip(g, p):
        cm[x][y] += 1
    for c in CATS:
        if sum(cm[c].values()) == 0:
            continue
        print(f"  {c:<22}" + "".join(f"{cm[c][d]:>6}" for d in CATS))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--import", dest="imp", help="worksheet CSV to import as hand labels")
    ap.add_argument("--import-pass2", help="second-pass worksheet for self-agreement")
    ap.add_argument("--split", default="test", choices=["dev", "test"])
    ap.add_argument("--sources", default="regex_baseline,llm")
    ap.add_argument("--gold", default="hand",
                    help="reference label source. 'hand' is the human set; 'ref_claude' is a "
                         "disclosed strong-model reference used until hand labels exist")
    a = ap.parse_args()
    global GOLD
    GOLD = a.gold
    con = sqlite3.connect(DB, timeout=60)
    if a.imp:
        import_worksheet(con, a.imp, "hand")
        publish(con)
    if a.import_pass2:
        import_worksheet(con, a.import_pass2, "hand_pass2")

    n_gold = con.execute("SELECT count(*) FROM labels WHERE source=? AND category_primary IS NOT NULL", (GOLD,)).fetchone()[0]
    if not n_gold:
        print(f"\nno '{GOLD}' labels yet - fill labels/sample_v2_worksheet.csv then --import it")
        return
    if GOLD != "hand":
        print(f"\nREFERENCE SET IS '{GOLD}', NOT HUMAN LABELS. Figures below measure agreement with a")
        print("disclosed strong-model reference labelled from the same title+excerpt against codebook")
        print("v2. Replace with hand labels (eval_classifier.py --import ...) before publication.")

    # Self-agreement ceiling
    g2 = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT issue_id, category_primary, severity FROM labels WHERE source='hand_pass2' AND category_primary IS NOT NULL")}
    if g2:
        g1 = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT issue_id, category_primary, severity FROM labels WHERE source='hand' AND category_primary IS NOT NULL")}
        ids = sorted(set(g1) & set(g2))
        print(f"\nSELF-AGREEMENT (n={len(ids)}): category kappa "
              f"{kappa([g1[i][0] for i in ids],[g2[i][0] for i in ids]):.2f}, severity kappa "
              f"{kappa([g1[i][1] for i in ids],[g2[i][1] for i in ids]):.2f}")
        print("  Reference point, not a hard ceiling: it measures the labeler's consistency.")
        print("  A classifier scoring above it is likely fitting the labeler's noise; the gap")
        print("  between them cannot be read as improvement.")
    else:
        print("\n(no hand_pass2 yet: re-label 50 dev issues >=5 days later for the self-agreement reference)")

    for s in a.sources.split(","):
        score(con, a.split, s.strip())
    if a.split == "test":
        print("\nNOTE: test split touched. Do not iterate the prompt against these numbers.")


if __name__ == "__main__":
    main()
