#!/usr/bin/env python3
"""Draw the stratified hand-labeling sample and assign the dev/test split.

Codebook v2, labeling protocol:
  - stratify by framework x category-guess (regex baseline) so rare categories are not
    left with two examples; speculative_decoding is deliberately oversampled
  - assign dev (40%) / test (60%) AT SAMPLE TIME and store it on the hand-label rows,
    so prompt iteration can only ever touch dev
  - the worksheet carries the excerpt the classifier sees (local only, gitignored);
    the published label set carries url + labels only

Writes labels/sample_v2_worksheet.csv (local) and seeds labels rows with source='hand',
category NULL, split set. Fill the worksheet; import_hand_labels.py loads it back.
"""
import csv
import json
import random
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
OUT = ROOT / "labels" / "sample_v2_worksheet.csv"
TARGET = 340
MIN_PER_CAT = 20
DEV_FRAC = 0.40
SEED = 20261010


def main():
    rng = random.Random(SEED)
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT i.id, i.framework_id fw, i.hf_id, i.url, i.title, i.body_excerpt, i.labels,
               l.category_primary guess
        FROM issues i JOIN labels l ON l.issue_id=i.id AND l.source='regex_baseline'
        WHERE i.excluded=0""")]
    if not rows:
        raise SystemExit("run baseline_regex.py first - the sample stratifies on its guesses")

    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["guess"], []).append(r)
    for v in by_cat.values():
        rng.shuffle(v)

    # Guarantee the floor per category first, then fill proportionally by framework.
    picked, seen = [], set()
    for cat, pool in by_cat.items():
        for r in pool[:MIN_PER_CAT]:
            picked.append(r); seen.add(r["id"])
    rest = [r for r in rows if r["id"] not in seen]
    rng.shuffle(rest)
    by_fw = {}
    for r in rest:
        by_fw.setdefault(r["fw"], []).append(r)
    need = TARGET - len(picked)
    total_rest = len(rest) or 1
    for fw, pool in by_fw.items():
        k = round(need * len(pool) / total_rest)
        for r in pool[:k]:
            picked.append(r); seen.add(r["id"])
    picked = picked[:TARGET]
    rng.shuffle(picked)
    n_dev = round(len(picked) * DEV_FRAC)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["issue_id", "split", "framework", "model", "url", "title", "maintainer_labels",
                    "regex_guess", "excerpt", "category_primary", "category_secondary", "severity", "reason"])
        for n, r in enumerate(picked):
            split = "dev" if n < n_dev else "test"
            w.writerow([r["id"], split, r["fw"], r["hf_id"], r["url"], r["title"], r["labels"],
                        r["guess"], (r["body_excerpt"] or "")[:2500], "", "", "", ""])
            con.execute("""INSERT OR REPLACE INTO labels(issue_id, source, codebook_version, split, labeled_at)
                           VALUES(?,?,?,?,?)""", (r["id"], "hand", "v2", split, now))
    con.commit()

    print(f"sampled {len(picked)} issues -> {OUT.relative_to(ROOT)}  (dev {n_dev}, test {len(picked)-n_dev})\n")
    print("by regex guess (stratum):")
    dist = {}
    for r in picked:
        dist[r["guess"]] = dist.get(r["guess"], 0) + 1
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
        flag = "  <- under floor, merge into other for reporting" if v < 10 else ""
        print(f"  {k:<22}{v:>4}{flag}")
    print("\nby framework:")
    d2 = {}
    for r in picked:
        d2[r["fw"]] = d2.get(r["fw"], 0) + 1
    for k, v in sorted(d2.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<14}{v:>4}")
    print("\nLabel from title + excerpt ONLY (what the classifier sees). Do not open the issue")
    print("thread first - maintainer replies leak the resolution into the label.")


if __name__ == "__main__":
    main()
