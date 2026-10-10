#!/usr/bin/env python3
"""Was the architecture ALREADY registered on the day the weights dropped?

This replaces a blame-based attempt that failed three ways: blame reports the
last commit to touch a line rather than the one that added it (DeepSeek-V3 in vLLM came
back attributed to a later de-duplication refactor), code search matches the
architecture string in unrelated files (DeepSeek-V3.2 matched an expert-parallel load
balancer), and for a genuinely reused architecture it answered the wrong question
entirely - granite-4.1-3b was dated to Granite 1.0's original PR, 587 days before the
model existed.

That last failure is the useful one. For an INHERITED architecture there is no support
date distinct from the architecture's own: the model was runnable the moment it shipped.
So the question is not "when was this added" but the binary, checkable:

    at the commit immediately before release_date, did the repo already declare
    this architecture?

Yes  -> supported, day 0 by inheritance (exact, and the honest figure)
No   -> the architecture arrived later; left undetermined for hand resolution
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
SNAP = datetime.now(timezone.utc).date().isoformat()

# Files that DECLARE supported architectures, in priority order per framework.
DECL = {
    "vllm": ["vllm/model_executor/models/registry.py"],
    "sglang": ["python/sglang/srt/models/registry.py",
               "python/sglang/srt/configs/model_config.py"],
    "transformers": ["src/transformers/models/auto/modeling_auto.py",
                     "src/transformers/models/auto/configuration_auto.py"],
    "llamacpp": ["convert_hf_to_gguf.py"],
    "trtllm": ["tensorrt_llm/models/__init__.py"],
}


def commit_before(repo, day):
    """SHA of the last commit on or before `day`."""
    try:
        _, c = gh.get(f"repos/{repo}/commits?until={day}T23:59:59Z&per_page=1")
    except urllib.error.HTTPError:
        return None
    return c[0]["sha"] if c else None


def declared_at(repo, fw, arch, sha):
    """Is `arch` present in any declaration file at that commit?"""
    for path in DECL.get(fw, []):
        text = gh.raw_file(repo, path, ref=sha)
        if text and arch in text:
            return path
    return None


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # Revert the unreliable blame results before doing anything else.
    n = con.execute("""UPDATE support_events SET state='undetermined', event_date=NULL,
        days_to_support=NULL, fidelity='none',
        evidence_rule=framework_id||':reverted-blame(unreliable)'
        WHERE evidence_rule LIKE '%:blame(%'""").rowcount
    con.commit()
    if n:
        print(f"reverted {n} blame-derived events\n")

    rows = [dict(r) for r in con.execute("""
        SELECT s.framework_id fw, s.hf_id, m.architecture arch, m.release_date rel,
               m.support_kind
        FROM support_events s JOIN models m USING(hf_id)
        WHERE s.state='undetermined' AND m.architecture IS NOT NULL
        ORDER BY m.release_date""")]
    print(f"testing {len(rows)} undetermined pairs for architecture-at-release\n")

    inherited = late = 0
    for r in rows:
        repo = con.execute("SELECT repo FROM frameworks WHERE id=?", (r["fw"],)).fetchone()[0]
        sha = commit_before(repo, r["rel"])
        if not sha:
            print(f"  {r['hf_id']:<44} {r['fw']:<13} no commit before release")
            continue
        path = declared_at(repo, r["fw"], r["arch"], sha)
        if path:
            inherited += 1
            print(f"  {r['hf_id']:<44} {r['fw']:<13} DAY 0 (already declared in {path.split('/')[-1]})")
            con.execute("""UPDATE support_events SET state='supported', event_date=?,
                days_to_support=0, fidelity='exact', evidence_rule=?, evidence_urls=?
                WHERE framework_id=? AND hf_id=?""",
                (r["rel"], f"{r['fw']}:inherited(arch declared at {sha[:8]} in {path})",
                 json.dumps([f"https://github.com/{repo}/blob/{sha}/{path}"]),
                 r["fw"], r["hf_id"]))
            con.commit()
        else:
            late += 1
            print(f"  {r['hf_id']:<44} {r['fw']:<13} arch absent at release -> added later")

    left = con.execute(
        "SELECT count(*) FROM support_events WHERE state='undetermined'").fetchone()[0]
    print(f"\nday-0 by inheritance: {inherited} | arrived later (hand resolution): {late}")
    print(f"still undetermined: {left}")


if __name__ == "__main__":
    main()
