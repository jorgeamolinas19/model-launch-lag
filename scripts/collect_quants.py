"""Quantization-artifact lag (docs/metrics.md §7).

For every cohort model, search the Hub for repos whose id contains the model's base name,
detect the quant format from the repo name, classify the publisher, and store one row per
(model, repo, fmt). The metric is the first appearance per format relative to release.

    quant_lag(model, fmt) = min(published_at | fmt) - release_date

Hub search is keyword-based (threats §8): a quant repo with an unconventional name is
missed, so every lag is an upper bound on the ecosystem's speed. Raw responses go to
raw/hub/quants_<snapshot>/ so this can be rebuilt without re-fetching.

    collect_quants.py            # fetch + store + report
    collect_quants.py --report   # report from the DB only
"""
import argparse, datetime as dt, json, re, sqlite3, statistics
from pathlib import Path
from hub import get, save_raw

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
SNAP = dt.date.today().isoformat()

# order matters: first match wins; 'int4' catches the generic 4-bit spellings
FMT_RE = [
    ("nvfp4", r"nvfp4"), ("mxfp4", r"mxfp4"), ("fp8", r"fp8"), ("gguf", r"gguf"),
    ("awq", r"awq"), ("gptq", r"gptq"), ("mlx", r"\bmlx\b|^mlx-community/"),
    ("int4", r"int4|w4a16|w4a8|4bit|4-bit|bnb-4|nf4|exl[23]|compressed-tensors"),
]
HW_VENDORS = {"nvidia", "intel", "amd", "qualcomm", "arm", "apple", "huawei", "ascend"}
# ponytail: a flat org allowlist; a real vendor registry would read org cards. Ceiling:
# vendor-run community orgs (e.g. 'unsloth', 'bartowski') are 'community' by design.


def fmt_of(repo_id):
    low = repo_id.lower()
    for fmt, rx in FMT_RE:
        if re.search(rx, low):
            return fmt
    return None


def publisher_kind(repo_id, model_org):
    org = repo_id.split("/")[0].lower()
    if org == model_org.lower():
        return "first_party"
    if org in HW_VENDORS:
        return "hardware_vendor"
    return "community"


def search_all(name, cap=1000):
    out, url = [], f"https://huggingface.co/api/models?search={name}&sort=downloads&direction=-1&limit=100"
    while url and len(out) < cap:
        h, page = get(url)
        if not page:
            break
        out += page
        nxt = None
        for part in (h.get("Link") or "").split(","):
            if 'rel="next"' in part and "<" in part:
                nxt = part[part.index("<") + 1: part.index(">")]
        url = nxt if not nxt or nxt.startswith("http") else f"https://huggingface.co{nxt}"
    return out


def collect(con):
    raw = ROOT / "raw" / "hub" / f"quants_{SNAP}"
    models = con.execute("SELECT hf_id, release_date FROM models WHERE in_cohort=1").fetchall()
    for hf_id, rel in models:
        org, name = hf_id.split("/")
        name = re.sub(r"-(BF16|FP16|FP8)$", "", name, flags=re.I)  # sibling quants drop the precision suffix
        # the base name must appear as a whole token: 'DeepSeek-V3' must not match 'DeepSeek-V3.2'
        tok = re.compile(re.escape(name) + r"(?![\w.])", re.I)
        hits = search_all(name)
        save_raw(hits, raw, hf_id)
        n = 0
        for m in hits:
            rid = m.get("id") or m.get("modelId")
            if not rid or rid == hf_id or not tok.search(rid):
                continue
            fmt = fmt_of(rid)
            if not fmt:
                continue
            con.execute("""INSERT OR REPLACE INTO quant_artifacts(hf_id, repo, fmt, publisher_kind,
                           published_at, downloads, snapshot_date) VALUES (?,?,?,?,?,?,?)""",
                        (hf_id, rid, fmt, publisher_kind(rid, org), (m.get("createdAt") or "")[:10],
                         m.get("downloads"), SNAP))
            n += 1
        con.commit()
        print(f"  {hf_id:<48} {len(hits):>4} hits  {n:>3} quant repos")


def report(con):
    rows = con.execute("""SELECT q.hf_id, q.fmt, min(q.published_at), m.release_date,
                                 (SELECT publisher_kind FROM quant_artifacts q2 WHERE q2.hf_id=q.hf_id AND q2.fmt=q.fmt
                                  ORDER BY published_at LIMIT 1),
                                 count(*), sum(q.downloads)
                          FROM quant_artifacts q JOIN models m ON m.hf_id=q.hf_id
                          WHERE q.published_at != '' GROUP BY q.hf_id, q.fmt ORDER BY m.release_date, q.hf_id, q.fmt""").fetchall()
    fmts = ["gguf", "mlx", "awq", "gptq", "int4", "fp8", "mxfp4", "nvfp4"]
    lag = {}
    for hf_id, fmt, first, rel, who, n, dl in rows:
        d = (dt.date.fromisoformat(first) - dt.date.fromisoformat(rel)).days
        lag.setdefault(hf_id, {})[fmt] = (d, who, n, dl or 0)
    print(f"QUANTIZATION-ARTIFACT LAG (metrics §7) - snapshot {SNAP}")
    print("first quant repo per format, days after weights-public release. '.' = none found.")
    print("suffix: f=first-party h=hardware-vendor c=community.  Hub search is keyword-based: upper bounds.\n")
    print(f"{'model':<44}" + "".join(f"{f:>8}" for f in fmts))
    for hf_id in [r[0] for r in con.execute("SELECT hf_id FROM models WHERE in_cohort=1 ORDER BY release_date")]:
        cells = []
        for f in fmts:
            v = lag.get(hf_id, {}).get(f)
            cells.append(f"{v[0]:>+6d}{v[1][0]:>2}" if v else f"{'.':>8}")
        print(f"{hf_id[:43]:<44}" + "".join(cells))
    print("\nper format: models with any repo / median lag / within 7 days / first-party first")
    for f in fmts:
        vals = [v[f] for v in lag.values() if f in v]
        if not vals:
            continue
        ds = [d for d, *_ in vals]
        fp = sum(1 for _, w, *_ in vals if w == "first_party")
        print(f"  {f:<8} {len(vals):>2}/{len(lag):<2}  median {statistics.median(ds):>+5.0f}d   "
              f"<=7d: {sum(d <= 7 for d in ds):>2}   first-party first: {fp}")
    # §7 reading: who closes the gap, pooled across formats
    who = con.execute("SELECT publisher_kind, count(*), sum(downloads) FROM quant_artifacts GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("\nall quant repos by publisher: " + "; ".join(f"{k} {n} repos / {dl or 0:,} downloads" for k, n, dl in who))
    print("\n  Artifact availability is not framework support: a day-0 NVFP4 repo needs a kernel for")
    print("  the user's GPU generation. Read beside the framework support dates (report_support.py).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="skip fetching; report from the DB")
    a = ap.parse_args()
    con = sqlite3.connect(DB, timeout=60)
    if not a.report:
        collect(con)
        print()
    report(con)


if __name__ == "__main__":
    main()
