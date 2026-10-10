#!/usr/bin/env python3
"""Date architecture support exactly, by bisecting file history for the arch string.

Closes the class-A evidence gap. llama.cpp and TensorRT-LLM have no per-architecture
implementation file, so they could only be dated by PR search (fidelity 'good') - which
left them with ZERO exact observations and made their apparent slowness a measurement
artifact rather than a finding.

But both DECLARE architectures in a known file: llama.cpp via @Model.register(...)
decorators in convert_hf_to_gguf.py, TensorRT-LLM via its model __init__. Presence of
the string at a given commit is checkable, and monotonic once added - so the addition
date can be bisected.

Method: coarse monthly scan of the declaring file (one fetch resolves every cohort
architecture at once, since the whole file is read), then per-architecture refinement
inside the bracketing month to day resolution. Blob SHAs are cached, so commits sharing
an unchanged file cost nothing.
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
SNAP = datetime.now(timezone.utc).date()

# Files that declare supported architectures, for frameworks lacking a per-arch path.
DECL = {
    # llama.cpp: @ModelBase.register(...) decorators. NOTE this verifies the CONVERSION
    # half only - the evidence rule requires conversion AND graph build, so results are
    # recorded as `partial`, not `supported`. The date is exact; the claim is narrower.
    "llamacpp": "convert_hf_to_gguf.py",
    # TensorRT-LLM: an explicit supported-architecture allowlist. The first file tried,
    # tensorrt_llm/models/__init__.py, declared only 2 of 22 cohort architectures and
    # wrongly marked 19 pairs unsupported - a wrong-file artifact, now reverted.
    "trtllm": "tensorrt_llm/usage/architecture_allowlist.py",
}
# What a declaration in that file actually proves, per framework.
DECL_STATE = {"llamacpp": "partial", "trtllm": "supported"}
INHERIT_WINDOW = 240   # days before release beyond which a declaration is pre-existing

_sha_cache = {}    # (repo, day) -> commit sha
_text_cache = {}   # (repo, path, sha) -> text


def sha_at(repo, day):
    key = (repo, day)
    if key not in _sha_cache:
        try:
            _, c = gh.get(f"repos/{repo}/commits?until={day}T23:59:59Z&per_page=1")
            _sha_cache[key] = c[0]["sha"] if c else None
        except urllib.error.HTTPError:
            _sha_cache[key] = None
    return _sha_cache[key]


def text_at(repo, path, sha):
    key = (repo, path, sha)
    if key not in _text_cache:
        _text_cache[key] = gh.raw_file(repo, path, ref=sha) or ""
    return _text_cache[key]


def present(repo, path, term, day):
    sha = sha_at(repo, day)
    return bool(sha) and term in text_at(repo, path, sha)


def bisect_first_present(repo, path, term, lo, hi):
    """Earliest day in (lo, hi] where term is present. Assumes absent at lo."""
    while (hi - lo).days > 1:
        mid = lo + timedelta(days=(hi - lo).days // 2)
        if present(repo, path, term, mid.isoformat()):
            hi = mid
        else:
            lo = mid
    return hi


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    repos = {r[0]: r[1] for r in con.execute("SELECT id, repo FROM frameworks")}
    models = [dict(r) for r in con.execute("""
        SELECT hf_id, architecture arch, release_date rel FROM models
        WHERE architecture IS NOT NULL ORDER BY release_date""")]
    oldest = date.fromisoformat(min(m["rel"] for m in models)) - timedelta(days=400)
    # Earliest cohort model per architecture: a later model on the same arch inherits.
    earliest_for_arch = {}
    for m in models:
        d = date.fromisoformat(m["rel"])
        if m["arch"] not in earliest_for_arch or d < earliest_for_arch[m["arch"]]:
            earliest_for_arch[m["arch"]] = d

    for fw, path in DECL.items():
        repo = repos.get(fw)
        if not repo:
            continue
        print(f"\n=== {fw}  {repo}:{path} ===")
        if gh.exists(repo, path) != "file":
            print(f"  declaring file not found at HEAD - cannot upgrade {fw}")
            continue

        # Coarse scan: one fetch per month resolves every architecture at once.
        months, d = [], oldest.replace(day=1)
        while d <= SNAP:
            months.append(d)
            d = (d.replace(day=28) + timedelta(days=5)).replace(day=1)
        print(f"  coarse scan over {len(months)} monthly checkpoints...")
        seen = {}
        for mo in months:
            sha = sha_at(repo, mo.isoformat())
            if not sha:
                continue
            txt = text_at(repo, path, sha)
            if not txt:
                continue
            for m in models:
                if m["arch"] in txt and m["arch"] not in seen:
                    seen[m["arch"]] = mo
        print(f"  architectures ever declared: {len(seen)}/{len(models)}")

        for m in models:
            arch, rel = m["arch"], date.fromisoformat(m["rel"])
            first_month = seen.get(arch)
            if not first_month:
                con.execute("""UPDATE support_events SET state='unsupported',
                    event_date=NULL, days_to_support=NULL, fidelity='exact',
                    evidence_rule=? WHERE framework_id=? AND hf_id=?""",
                    (f"{fw}:arch-never-declared({path})", fw, m["hf_id"]))
                continue
            lo = first_month - timedelta(days=35)
            if present(repo, path, arch, lo.isoformat()):
                lo = oldest   # declared before the scan window began
            exact = bisect_first_present(repo, path, arch, lo, first_month)
            days = (exact - rel).days
            sha = sha_at(repo, exact.isoformat())
            url = [f"https://github.com/{repo}/blob/{sha}/{path}"] if sha else []

            # An architecture declared long before this model, or shared with an
            # earlier cohort model, is INHERITED - the declaration date is not this
            # model's support date. granite-4.1-3b came back at -566d from Granite's
            # 2024 entry, and Qwen3.8-27B at -185d from Qwen3.5's. Both are day-0
            # architecture compatibility, not 18 months of early access.
            inherited = days < -INHERIT_WINDOW or (
                arch in earliest_for_arch and earliest_for_arch[arch] < rel)
            if inherited:
                print(f"    {m['hf_id'][:42]:<43} arch_compatible (declared {exact}, "
                      f"inherited)")
                con.execute("""UPDATE support_events SET state='arch_compatible',
                    event_date=?, days_to_support=0, fidelity='exact', evidence_rule=?,
                    evidence_urls=? WHERE framework_id=? AND hf_id=?""",
                    (rel.isoformat(),
                     f"{fw}:inherited(arch declared {exact} in {path}, predates model)",
                     json.dumps(url), fw, m["hf_id"]))
                con.commit()
                continue

            state = DECL_STATE[fw]
            tag = "DAY 0" if days == 0 else (f"{days:+d}d EARLY" if days < 0 else f"{days:+d}d")
            print(f"    {m['hf_id'][:42]:<43} {exact}  {tag:<12} {state}")
            con.execute("""UPDATE support_events SET state=?, event_date=?,
                days_to_support=?, fidelity='exact', evidence_rule=?, evidence_urls=?
                WHERE framework_id=? AND hf_id=?""",
                (state, exact.isoformat(), days,
                 f"{fw}:arch-declared-bisect({path})", json.dumps(url),
                 fw, m["hf_id"]))
            con.commit()
    con.commit()
    print("\nfidelity after upgrade:")
    for r in con.execute("""SELECT framework_id, fidelity, count(*) FROM support_events
                            GROUP BY 1,2 ORDER BY 1,2"""):
        print(f"  {r[0]:<14}{r[1]:<8}{r[2]}")


if __name__ == "__main__":
    main()
