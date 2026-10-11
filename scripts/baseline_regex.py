#!/usr/bin/env python3
"""Keyword baseline classifier. Exists so the LLM's accuracy number means something.

If regex scores 70% and an 8B model scores 74%, that IS the finding. Rules follow the
codebook v2 precedence ladder: first matching category wins, top to bottom. Severity is
derived from structural signals, not vocabulary, because vocabulary is how issue authors
inflate it.

Writes labels with source='regex_baseline', codebook_version='v2'.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
VERSION = "v2"

# Precedence order matters: evaluated top to bottom (docs/codebook-v2.md).
RULES = [
    ("missing_feature", r"not (yet )?supported|unsupported (model|architecture)|architectures?.{0,40}not (recognized|registered|found)|"
                        r"please (add|support)|add support for|feature request|\[feature\]|is not in the list of|"
                        r"no module named .*model|model type .* is not supported|unknown (model|architecture)"),
    ("install_build", r"pip install|wheel|cmake|ninja|compil(e|ation)|build(ing)? fail|no kernel image|"
                      r"undefined symbol|ImportError|ModuleNotFoundError|libcuda|cuda (version|toolkit|driver)|"
                      r"glibc|dockerfile|docker image|segmentation fault|illegal instruction|nvcc|torch version"),
    ("template_tokenizer", r"chat.?template|jinja|tokeniz|special token|eos|bos|<\|im_end\|>|stop token|"
                           r"never stops|doesn'?t stop|keeps generating|tool.?call (format|pars)|reasoning parser|"
                           r"pre-?tokenizer|vocab(ulary)? (size|mismatch)|added_tokens"),
    ("quantization", r"gguf|awq|gptq|fp8|nvfp4|mxfp4|int4|int8|bitsandbytes|bnb|quantiz|q4_k|q5_k|q8_0|"
                     r"marlin|kv.?cache (quant|fp8)|exl2|mlx"),
    ("speculative_decoding", r"speculative|draft model|eagle|medusa|mtp\b|multi.?token prediction|acceptance rate|ngram spec"),
    ("oom_hardware", r"out of memory|\boom\b|cuda error: out of memory|torch\.outofmemoryerror|killed|"
                     r"vram|gpu memory|memory usage|insufficient memory|not enough (memory|gpu)|"
                     r"tensor parallel.{0,30}(not divisible|must be)|sm_\d\d|compute capability|unsupported gpu"),
    ("correctness", r"garbage|gibberish|wrong (output|answer|result)|incorrect|repeat(s|ing) (itself|the same)|"
                    r"nonsens|hallucinat|degrad(ed|ation) (quality|accuracy)|accuracy (drop|loss)|"
                    r"different (output|result) (from|than)|mismatch(ed)? (output|logits)|nan\b|inf\b"),
    ("performance", r"slow|throughput|tokens?/s|tok/s|latency|ttft|performance (regression|drop|issue)|"
                    r"\d+x (slower|faster)|low (gpu )?utilization|speed"),
]
COMPILED = [(c, re.compile(p, re.I)) for c, p in RULES]


def classify(title, body):
    text = f"{title}\n{body}"
    cats = [c for c, rx in COMPILED if rx.search(text)]
    primary = cats[0] if cats else "other"
    secondary = cats[1:3]
    return primary, secondary


def severity(i, primary):
    """Structural signals only (codebook v2, severity table)."""
    t = (i["title"] or "").lower()
    if primary in ("other",) or re.search(r"\?$|how (to|do|can)|is it possible|question", t):
        return "minor"
    if i["has_traceback"] and primary in ("install_build", "missing_feature", "oom_hardware",
                                          "quantization", "template_tokenizer", "speculative_decoding"):
        return "blocker"
    if re.search(r"cannot|can'?t|unable|fail|crash|error|not work", t):
        return "blocker" if primary != "performance" else "degraded"
    if primary in ("performance", "correctness"):
        return "degraded"
    return "degraded"


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = f"regex-{VERSION}-{now[:10]}"
    con.execute("""INSERT OR REPLACE INTO runs(run_id, started_at, snapshot_date, codebook_version,
                   classifier_model, prompt_version, notes) VALUES(?,?,?,?,?,?,?)""",
                (run_id, now, now[:10], VERSION, "regex_baseline", "rules-v1",
                 "keyword precedence-ladder baseline; severity from structural signals"))
    n, dist = 0, {}
    for i in con.execute("SELECT * FROM issues WHERE excluded=0"):
        p, s = classify(i["title"], i["body_excerpt"])
        sev = severity(i, p)
        con.execute("""INSERT OR REPLACE INTO labels(issue_id, source, codebook_version, category_primary,
                       category_secondary, severity, reason, labeled_at, run_id)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (i["id"], "regex_baseline", VERSION, p, json.dumps(s), sev,
                     "keyword rule", now, run_id))
        dist[p] = dist.get(p, 0) + 1
        n += 1
    con.commit()
    print(f"regex baseline labelled {n} issues (run {run_id})\n")
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<22}{v:>5}  {100*v/n:5.1f}%")


if __name__ == "__main__":
    main()
