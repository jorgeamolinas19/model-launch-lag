"""Doc-vs-data consistency check. Recomputes the headline figures from the database and
the generated reports and fails if a document does not contain them.

Exists because the memo was written in passes over several snapshots, and figures from
the pre-guard issue set (2,856) and from earlier adjudications (TensorRT-LLM +17) sat
beside current ones for days. Run after any re-collection, re-adjudication or doc edit:

    python3 scripts/check_docs.py
"""
import csv, re, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
DOCS = {n: (ROOT / p).read_text() for n, p in
        {"memo": "docs/memo.md", "readme": "README.md", "deck": "docs/deck.md",
         "checklist": "docs/readiness-checklist.md"}.items()}
con = sqlite3.connect(DB)
q = lambda sql: con.execute(sql).fetchone()[0]
fails = []


def expect(docs, *needles, label=""):
    """Every needle must appear in every named doc (plain substrings)."""
    for d in docs.split():
        for n in needles:
            if str(n) not in DOCS[d]:
                fails.append(f"{d:<9} missing {n!r:<28} {label}")


def expect_re(docs, pattern, label=""):
    for d in docs.split():
        if not re.search(pattern, DOCS[d]):
            fails.append(f"{d:<9} missing /{pattern}/  {label}")


# --- cohort and issue counts
kept = q("SELECT count(distinct id) FROM issues WHERE excluded=0")
distinct = q("SELECT count(distinct id) FROM issues")
expect("memo readme deck", f"{distinct:,}", f"{kept:,}", label="issue counts")
scored = q("""SELECT count(*) FROM labels l JOIN issues i ON i.id=l.issue_id
              WHERE l.source='hand' AND i.excluded=0 AND l.category_primary IS NOT NULL""")
expect("memo readme deck", scored, label="scored hand-labelled sample")
for fw, n in con.execute("SELECT framework_id, count(distinct id) FROM issues WHERE excluded=0 GROUP BY 1"):
    expect("memo", f"| {n} |", label=f"{fw} first-30-day volume")

# --- hand-label category counts and blocker counts (memo tables)
for cat, n, blk in con.execute("""SELECT l.category_primary, count(*), sum(l.severity='blocker')
        FROM labels l JOIN issues i ON i.id=l.issue_id WHERE l.source='hand' AND i.excluded=0
        AND l.category_primary IS NOT NULL GROUP BY 1"""):
    expect("memo", f"| {cat} | {n} |", label="hand category row")
    if cat in ("quantization", "missing_feature", "speculative_decoding"):
        expect_re("memo", rf"\b{blk} of {n}\b|{n} scored, {blk} were|\| {cat} \| {n} \| \d+% \| \**{blk}\**",
                  label=f"{cat} blocker count")

# --- close reason
closed = q("SELECT count(distinct id) FROM issues WHERE excluded=0 AND closed_at IS NOT NULL")
byfix = q("SELECT count(distinct id) FROM issues WHERE excluded=0 AND closed_by_fix=1")
compl = q("SELECT count(distinct id) FROM issues WHERE excluded=0 AND state_reason='completed'")
expect("memo", f"{closed:,} closed", f"**{100 * byfix // closed}%**", f"**{round(100 * compl / closed)}%**",
       label="closed_by_fix vs completed")

# --- hardware and quant-format mentions (from the regex metrics report, labels-free)
rep = (ROOT / "reports" / "metrics_regex.txt").read_text()
m = re.search(r"datacenter (\d+), consumer (\d+), workstation (\d+), apple_silicon (\d+)", rep)
expect("memo", *m.groups(), label="gpu class counts")
m = re.search(r"nvfp4 (\d+)", rep); nvfp4 = m.group(1)
expect("memo", f"NVFP4 {nvfp4}", label="nvfp4 mentions")
expect("deck", f"({nvfp4})", label="nvfp4 mentions")
m = re.search(r"of (\d+) oom_hardware issues, (\d+) report VRAM;\s*(\d+)/(\d+)", rep)
expect_re("memo deck checklist", rf"{m.group(3)} of (those )?{m.group(4)}", label="capability gap")

# --- Q1: evidence-class table and TRT-LLM headline from the support report
sup = (ROOT / "reports" / "support_new_arch.txt").read_text()
for line in sup.split("SENSITIVITY BY EVIDENCE CLASS")[1].splitlines():
    cells = line.split()
    if len(cells) == 9 and cells[0] in ("transformers", "vllm", "sglang", "llamacpp", "ollama", "trtllm"):
        name = {"vllm": "vLLM", "sglang": "SGLang", "llamacpp": "llama.cpp", "ollama": "Ollama",
                "trtllm": "TensorRT-LLM"}.get(cells[0], cells[0])
        row = f"| {name} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} | {cells[5]} | {cells[6]} | {cells[7]} | {cells[8]} |"
        expect("memo", row, label="evidence-class table row")
        if cells[0] == "trtllm":
            expect_re("memo deck", rf"verified \**\+{cells[1].lstrip('+')}", label="TRT-LLM headline")
# pre-release shares per band
for band, n, early in con.execute("""SELECT m.band, count(*), sum(s.days_to_support<0) FROM support_events s
        JOIN models m ON m.hf_id=s.hf_id WHERE s.state IN ('supported','partial') AND s.days_to_support IS NOT NULL
        GROUP BY 1"""):
    expect("memo checklist", f"{early} of {n}", label=f"{band} pre-release merges")

# --- hand files
n_ref = sum(1 for r in (ROOT / "support_events_hand.csv").read_text().splitlines()
            if not r.startswith("#") and "claude-ref" in r)
expect("memo readme deck", f"{n_ref} ", label="assistant-adjudicated support pairs")
n_dates = sum(1 for r in (ROOT / "release_dates_hand.csv").read_text().splitlines()
              if r and not r.startswith("#") and not r.startswith("hf_id"))
expect("memo readme deck", f"{n_dates} ", label="hand-resolved release dates")
remote = q("SELECT count(*) FROM models WHERE in_cohort=1 AND ships_remote_code=1")
expect("memo deck checklist", f"{remote} ", label="remote-code models")

if fails:
    print("\n".join(fails)); sys.exit(f"\n{len(fails)} doc/data mismatch(es)")
print("check_docs ok")
