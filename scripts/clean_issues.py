#!/usr/bin/env python3
"""Apply the codebook's exclusion rules to collected issues (docs/codebook-v2.md).

Exclusions stay in the table with a reason code, so the filtering is auditable and
reversible, and every published denominator can be reconstructed.

  bot               author is a bot
  duplicate         closed as duplicate
  maintainer_task   tracking / release checklist / roadmap issue
  passing_mention   model named only in passing, or this row is the weaker of several
                    attributions of the same issue to sibling models
  non_english       body not predominantly Latin-script (recorded, never silently dropped)

Decisions are computed in memory and written in one batch, so this never contends with
a running collector for the write lock.
"""
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"

# Maintainer artifacts that name a model in passing. Widened after labeling: RFCs, CI
# failures, test-suite additions, perf roadmap sub-tasks and benchmark contributions
# were leaking through and landing in `other` (docs/codebook-v2.md, gaps section).
TASK_RE = re.compile(r"\b(tracking|roadmap|release checklist|release notes|umbrella|meta[- ]issue|"
                     r"sub-?task|test suite)\b|"
                     r"\[(RFC|Roadmap|Tracker|Test|CI Failure|CI|Perf|Benchmark|Feature\] update CIs)\]|"
                     r"^\s*(Benchmark|\[Benchmark\]|\[Test\]|\[Perf\])\b", re.I)
RANK = {"arch_class": 0, "slug": 1, "loose": 2}


def flat(s):
    return re.sub(r"[-_.\s]", "", (s or "").lower())


def non_english(text):
    letters = re.findall(r"[^\W\d_]", text or "")
    if len(letters) < 40:
        return False
    return sum(1 for ch in letters if ord(ch) > 0x024F) / len(letters) > 0.5


def main():
    con = sqlite3.connect(DB, timeout=60)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM issues")]
    decision = {}   # (id, hf_id) -> reason

    # Same GitHub issue attributed to several cohort models: keep the strongest
    # attribution (match kind, then model named in title); the rest are, for those
    # models, passing mentions.
    by_issue = {}
    for i in rows:
        by_issue.setdefault(i["id"], []).append(i)
    for attrs in by_issue.values():
        if len(attrs) < 2:
            continue
        attrs.sort(key=lambda x: (RANK[x["match_kind"]],
                                  0 if flat(x["hf_id"].split("/")[1]) in flat(x["title"]) else 1))
        for weaker in attrs[1:]:
            decision[(weaker["id"], weaker["hf_id"])] = "passing_mention"

    for i in rows:
        k = (i["id"], i["hf_id"])
        if k in decision:
            continue
        title, body = i["title"] or "", i["body_excerpt"] or ""
        if i["author_is_bot"]:
            decision[k] = "bot"
        elif (i["state_reason"] or "") == "duplicate":
            decision[k] = "duplicate"
        elif TASK_RE.search(title):
            decision[k] = "maintainer_task"
        elif non_english(title + " " + body):
            decision[k] = "non_english"
        elif i["match_kind"] == "loose":
            key = flat(i["family"])
            # Named once in the body and absent from the title: not ABOUT this model.
            if key not in flat(title) and flat(body).count(key) <= 1:
                decision[k] = "passing_mention"

    con.execute("UPDATE issues SET excluded=0, exclude_reason=NULL")
    con.executemany("UPDATE issues SET excluded=1, exclude_reason=? WHERE id=? AND hf_id=?",
                    [(r, i, h) for (i, h), r in decision.items()])
    con.commit()

    kept = len(rows) - len(decision)
    print(f"issues: {len(rows)} attributed rows ({len(by_issue)} distinct issues) -> "
          f"{kept} kept, {len(decision)} excluded\n")
    counts = {}
    for r in decision.values():
        counts[r] = counts.get(r, 0) + 1
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<18}{v}")
    print("\nkept, by match confidence:")
    for r in con.execute("SELECT match_kind, count(*) FROM issues WHERE excluded=0 GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {r[0]:<12}{r[1]}")
    print("\nkept, by framework:")
    for r in con.execute("SELECT framework_id, count(*) FROM issues WHERE excluded=0 GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {r[0]:<13}{r[1]}")


if __name__ == "__main__":
    main()
