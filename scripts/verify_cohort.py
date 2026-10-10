#!/usr/bin/env python3
"""Verify cohort ids against the Hub and resolve release dates (docs/metrics.md §0).

Reads cohort.toml, fetches Hub metadata + full commit history, stores raw responses,
writes models/download_snapshots, and prints a report naming every row that needs hand
resolution. Needs no credentials: Hub metadata is public even for gated repos.
"""
import re, sqlite3, sys, tomllib
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hub

ROOT = Path(__file__).resolve().parent.parent
SNAP = datetime.now(timezone.utc).date().isoformat()
RAW = ROOT / "raw" / "hub" / SNAP
DB = ROOT / "db" / "launch_lag.sqlite"

# A weight upload is the earliest point the repo could possibly be runnable; an
# "initial commit" is often just a README/.gitattributes placeholder.
WEIGHTY = re.compile(r"safetensors|\.bin|upload|weights|shard|model-0|gguf", re.I)
# fp16 floor -> smallest widely-available card that clears it
CARDS = [(16, "T4/V100-16GB"), (24, "RTX 3090/4090, A10"), (40, "A100-40GB"),
         (48, "L40S/A6000"), (80, "A100-80GB/H100"), (141, "H200"), (1128, "multi-GPU (1 node)"),
         (10**9, "MULTI-NODE required")]


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def resolve_release(meta, commits):
    """Return (date, method, uncertain, created, first, weights). Candidates per metrics §0."""
    created = meta.get("createdAt")
    first = commits[-1]["date"] if commits else None
    weights = next((c["date"] for c in reversed(commits) if WEIGHTY.search(c.get("title") or "")), None)
    # Later of repo creation and weights landing (metrics §0): a model cannot be public
    # before its repo exists, nor runnable before its weights land.
    cands = [c for c in (created, first, weights) if c]
    date = max(cands) if cands else None
    method = ("first_commit" if date == first else
              "weights_commit" if date == weights else "created_at")
    unc = 0
    if created and first and abs((iso(created) - iso(first)).days) > 2:
        unc = 1
    if weights and date and abs((iso(weights) - iso(date)).days) > 2:
        unc = 1
    # Single-candidate case: gated repos 401 on /commits, leaving only createdAt. With
    # nothing to disagree with, the checks above cannot fire - so a lone candidate is
    # itself grounds for hand resolution, not grounds for confidence. (Found via
    # gemma-3-27b-it, whose createdAt predates its announcement by ~11 days.)
    if not first and not weights:
        unc = 1
        method = "created_at_only"
    return date, method, unc, created, first, weights


def main():
    cohort = tomllib.loads((ROOT / "cohort.toml").read_text())
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "db" / "schema.sql").read_text())

    for fid, f in cohort["frameworks"].items():
        con.execute("INSERT OR REPLACE INTO frameworks(id,repo,support_via) VALUES(?,?,?)",
                    (fid, f["repo"], f["support_via"]))

    rows, bad = [], []
    for m in cohort["models"]:
        hf_id = m["hf_id"]
        try:
            _, meta = hub.get(f"models/{hf_id}")
        except Exception as e:
            bad.append((hf_id, f"{type(e).__name__}: {getattr(e,'code',e)}"))
            print(f"  FAIL  {hf_id}  {getattr(e,'code',e)}")
            continue
        hub.save_raw(meta, RAW / "models", hf_id)
        try:
            commits = hub.all_commits(hf_id)
            hub.save_raw(commits, RAW / "commits", hf_id)
        except Exception as e:
            commits = []
            print(f"  warn  {hf_id}: commits unavailable ({getattr(e,'code',e)})")

        date, method, unc, created, first, weights = resolve_release(meta, commits)
        params = (meta.get("safetensors") or {}).get("total")
        pb = round(params / 1e9, 2) if params else None
        arch = ((meta.get("config") or {}).get("architectures") or [None])[0]
        fp16 = round(pb * 2 * 1.20, 1) if pb else None
        int4 = round(pb * 0.55 * 1.25, 1) if pb else None
        card = next((c for lim, c in CARDS if fp16 and fp16 <= lim), None)
        vlow = hf_id.lower()
        variant = next((v for v in ("instruct", "base", "coder", "vl", "vision", "distill") if v in vlow), None)

        con.execute("""INSERT OR REPLACE INTO models(hf_id,family,variant,architecture,params_b,
            release_date,release_date_method,release_date_uncertain,created_at_api,first_commit_at,
            license,support_kind,in_cohort,vram_floor_fp16_gb,vram_floor_int4_gb,min_gpu_class_fp16,
            gated,weights_commit_at,band,draft_target) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?,?)""",
            (hf_id, m["family"], variant, arch, pb, (date or "")[:10], method, unc, created, first,
             (meta.get("cardData") or {}).get("license"), m["support_kind"], fp16, int4, card,
             str(meta.get("gated")), weights, m.get("band"), m.get("draft_target")))
        con.execute("INSERT OR REPLACE INTO download_snapshots(hf_id,fetched_at,downloads_30d,likes) VALUES(?,?,?,?)",
                    (hf_id, SNAP, meta.get("downloads"), meta.get("likes")))
        rows.append(dict(band=m.get("band","?"), hf_id=hf_id, kind=m["support_kind"], arch=arch, pb=pb, date=(date or "")[:10],
                         unc=unc, created=(created or "")[:10], first=(first or "")[:10],
                         weights=(weights or "")[:10], gated=str(meta.get("gated")),
                         dl=meta.get("downloads"), fp16=fp16, card=card, ncommits=len(commits)))
    con.commit()

    w = max((len(r["hf_id"]) for r in rows), default=20)
    print(f"\n{'band':<10} {'model':<{w}}  {'kind':<10} {'release':<10} {'created':<10} {'arch':<38} {'B':>7} {'fp16GB':>8}  gated")
    print("-" * (w + 110))
    for r in sorted(rows, key=lambda r: (r["band"], r["date"])):
        flag = "!" if r["unc"] else " "
        print(f"{r['band']:<10} {r['hf_id']:<{w}}  {r['kind']:<10} {r['date']:<10}{flag}{r['created']:<10} "
              f"{str(r['arch']):<38} {str(r['pb']):>7} {str(r['fp16']):>8}  {r['gated']}")
    print(f"\nverified {len(rows)}/{len(cohort['models'])} | needs hand resolution: "
          f"{sum(r['unc'] for r in rows)} | db: {DB.relative_to(ROOT)} | raw: {RAW.relative_to(ROOT)}")
    if bad:
        print("\nBAD IDS (fix cohort.toml):")
        for b, e in bad:
            print(f"  {b}  -> {e}")
    archs = {}
    for r in rows:
        archs.setdefault(r["arch"], []).append(r["hf_id"])
    dupes = {a: v for a, v in archs.items() if len(v) > 1}
    if dupes:
        print("\nSHARED ARCHITECTURES (inheritance: only the earliest is a new_arch measurement)")
        for a, v in dupes.items():
            print(f"  {a}: {', '.join(v)}")


if __name__ == "__main__":
    main()
