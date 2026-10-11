#!/usr/bin/env python3
"""Apply the codebook's exclusion rules to collected issues (docs/codebook-v2.md).

Exclusions stay in the table with a reason code, so the filtering is auditable and
reversible, and every published denominator can be reconstructed.

  bot               author is a bot
  duplicate         closed as duplicate
  maintainer_task   tracking / release checklist / roadmap issue
  passing_mention   model named only in passing, or this row is the weaker of two
                    attributions of the same issue to sibling models
  non_english       body not predominantly ASCII-Latin (recorded, never silently dropped)
"""
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"

TASK_RE = re.compile(r"\b(tracking|roadmap|release checklist|release notes|umbrella|meta[- ]issue|"
                     r"\[RFC\]|\[Roadmap\]|\[Tracker\])\b", re.I)
RANK = {"arch_class": 0, "slug": 1, "loose": 2}


def non_english(text):
    letters = re.findall(r"[^\W\d_]", text or "")
    if len(letters) < 40:
        return False
    non_latin = sum(1 for ch in letters if ord(ch) > 0x024F)
    return non_latin / len(letters) > 0.5


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("UPDATE issues SET excluded=0, exclude_reason=NULL")
    rows = [dict(r) for r in con.execute("SELECT * FROM issues")]
    reasons = {}

    def exclude(i, reason):
        con.execute("UPDATE issues SET excluded=1, exclude_reason=? WHERE id=? AND hf_id=?",
                    (reason, i["id"], i["hf_id"]))
        reasons[reason] = reasons.get(reason, 0) + 1

    # The same GitHub issue can be attributed to several cohort models (loose family
    # aliases hit every sibling). Keep the strongest attribution; the rest are, for
    # those models, passing mentions.
    by_issue = {}
    for i in rows:
        by_issue.setdefault(i["id"], []).append(i)
    for iid, attrs in by_issue.items():
        if len(attrs) < 2:
            continue
        attrs.sort(key=lambda x: (RANK[x["match_kind"]],
                                  0 if x["hf_id"].split("/")[1].lower() in (x["title"] or "").lower() else 1))
        for weaker in attrs[1:]:
            exclude(weaker, "passing_mention")

    for i in rows:
        if i["exclude_reason"]:
            continue
        cur = con.execute("SELECT excluded FROM issues WHERE id=? AND hf_id=?",
                          (i["id"], i["hf_id"])).fetchone()
        if cur and cur[0]:
            continue
        title, body = i["title"] or "", i["body_excerpt"] or ""
        if i["author_is_bot"]:
            exclude(i, "bot"); continue
        if (i["state_reason"] or "") == "duplicate":
            exclude(i, "duplicate"); continue
        if TASK_RE.search(title):
            exclude(i, "maintainer_task"); continue
        if non_english(title + " " + body):
            exclude(i, "non_english"); continue
        # Loose-only match, model absent from the title, named once in the body: the
        # issue is not ABOUT this model.
        if i["match_kind"] == "loose":
            fam = i["family"].lower()
            flat_title = re.sub(r"[-_.\s]", "", title.lower())
            flat_body = re.sub(r"[-_.\s]", "", body.lower())
            key = re.sub(r"[-_.\s]", "", fam)
            if key not in flat_title and flat_body.count(key) <= 1:
                exclude(i, "passing_mention"); continue
    con.commit()

    total = len(rows)
    kept = con.execute("SELECT count(*) FROM issues WHERE excluded=0").fetchone()[0]
    print(f"issues: {total} attributed rows -> {kept} kept, {total - kept} excluded\n")
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<18}{v}")
    print("\nkept, by match confidence:")
    for r in con.execute("SELECT match_kind, count(*) FROM issues WHERE excluded=0 GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {r[0]:<12}{r[1]}")
    print("\nkept, by framework:")
    for r in con.execute("SELECT framework_id, count(*) FROM issues WHERE excluded=0 GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {r[0]:<13}{r[1]}")


if __name__ == "__main__":
    main()
