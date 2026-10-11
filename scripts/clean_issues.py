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

# Cross-model attribution guard. A title that names a DIFFERENT model family while the
# attributed family is absent from it is about that other model; the attributed model
# is a passing mention in the body. Found in audit: "[Bug]: Kimi K2 produces gibberish"
# attributed to DeepSeek-V3.2; "Qwen2.5-VL engine failed" attributed to Qwen3-32B;
# "MiniMax-H3-GGUF fails to load" attributed to Qwen3.8-27B.
FAMILY_TOKENS = {
    "llama": r"\bllama[- ]?[234]|\btinyllama", "qwen": r"\bqwen", "gemma": r"\bgemma",
    "deepseek": r"\bdeepseek|\bdsv\d", "kimi": r"\bkimi|\bk2\b|\bk3\b", "glm": r"\bglm",
    "mistral": r"\bmistral|\bmixtral", "phi": r"\bphi-?\d", "granite": r"\bgranite",
    "olmo": r"\bolmo", "nemotron": r"\bnemotron", "minimax": r"\bminimax",
    "gptoss": r"\bgpt[- ]?oss", "jamba": r"\bjamba",
}
# Finer-than-family distinctions that still mean "a different model": generation numbers.
# Handles lists ("Qwen3.5/3.8", "gemma 2 and 3") and compact forms ("deepseekv32",
# "deepseekv41-flash") - the first version of this parser read those as 3 and 4 and
# excluded issues that were squarely about the attributed model.
GEN_LIST_RE = re.compile(
    r"\b(qwen|gemma|llama|glm|deepseek)[- ]?v?(\d(?:\.\d)?(?:(?:/|,\s*| and )\d(?:\.\d)?)*)(?![\d.])", re.I)
GEN_COMPACT_RE = re.compile(r"\b(deepseek|glm|qwen)[- ]?v?(\d)(\d)\b(?!\.\d)", re.I)


def generations(s):
    out = set()
    for m in GEN_LIST_RE.finditer(s):
        out.update(re.split(r"/|,\s*| and ", m.group(2)))
    for m in GEN_COMPACT_RE.finditer(s):          # deepseekv32 -> 3.2, deepseekv41 -> 4.1
        out.add(f"{m.group(2)}.{m.group(3)}")
    return {g.strip() for g in out if g.strip()}


def title_names_other_model(title, hf_id, family):
    """True if the title clearly names a model that is not the attributed one."""
    t = (title or "").lower()
    fam_key = next((k for k, rx in FAMILY_TOKENS.items() if re.search(rx, family.lower() + " " + hf_id.lower())), None)
    named = {k for k, rx in FAMILY_TOKENS.items() if re.search(rx, t)}
    if not named:
        return False
    if fam_key not in named:
        return True                      # title names other families only
    # Same family, different generation: "Qwen2.5-VL" vs attributed qwen3 / qwen3.5.
    # The attributed model's generation appearing anywhere in the title keeps the row.
    gens_in_title = generations(t)
    gens_attr = generations(hf_id.lower() + " " + family.lower())
    return bool(gens_in_title) and bool(gens_attr) and not (gens_in_title & gens_attr)


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
        elif title_names_other_model(title, i["hf_id"], i["family"]):
            decision[k] = "passing_mention"
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
