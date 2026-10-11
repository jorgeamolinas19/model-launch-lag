#!/usr/bin/env python3
"""Questions 2 and 3: what broke, and what should a platform team fix?

Implements docs/metrics.md §2-§4 and §6 exactly:
  §2 issue load          first-30-day issues per (model, framework), and per 1k downloads
  §3 time to resolve     Kaplan-Meier median days-to-close by category (open = censored),
                         plus % still open and the close-reason mix
  §4 top problems        count x severity weight, with the mandatory reweighting check
  §6 hardware profile    GPUs and VRAM mined from issue text; capability gap vs fp16 floor

  metrics_issues.py --source regex_baseline      # which label set to use
  metrics_issues.py --source llm
"""
import argparse
import json
import re
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
FWS = ["transformers", "vllm", "sglang", "llamacpp", "ollama", "trtllm"]
CATS = ["missing_feature", "install_build", "template_tokenizer", "quantization",
        "speculative_decoding", "oom_hardware", "correctness", "performance", "other"]
WEIGHTS = {"default": {"blocker": 3, "degraded": 2, "minor": 1},
           "steep": {"blocker": 5, "degraded": 2, "minor": 1},
           "blocker_only": {"blocker": 3, "degraded": 1, "minor": 0}}

GPU_RE = re.compile(
    r"\b(H200|H100|H800|A100|A800|A10G?|A30|A40|L40S?|L4|L20|T4|V100|P100|B200|GB200|RTX ?PRO ?6000|"
    r"RTX ?[2345]0[5-9]0 ?(?:Ti|Super|D)?|RTX ?A[456]000|MI300X|MI325X|MI250X?|MI210|"
    r"Jetson(?: Orin| Thor)?|DGX Spark|M[1-4] (?:Pro|Max|Ultra)|Apple Silicon)\b", re.I)
VRAM_RE = re.compile(r"total capacity of ([\d.]+) ?GiB|(\d{2,3}) ?GB (?:of )?(?:VRAM|GPU memory|card)", re.I)
QUANT_RE = re.compile(r"\b(nvfp4|mxfp4|fp8|gguf|q[2-8]_[k0-9_sml]+|awq|gptq|int4|int8|bnb|bitsandbytes|mlx|exl2)\b", re.I)
GPU_CLASS = [("datacenter", r"H200|H100|H800|A100|A800|A30|A40|L40|L4|L20|B200|GB200|MI3|MI2|V100|P100|DGX"),
             ("workstation", r"RTX ?PRO|RTX ?A[456]000|A10"),
             ("consumer", r"RTX ?[2345]0|T4"),
             ("apple_silicon", r"M[1-4] |Apple"),
             ("edge", r"Jetson|Spark")]


def km_median(durations):
    """durations: (time, observed) - open issues enter censored at snapshot."""
    obs = sorted(durations)
    n, s = len(obs), 1.0
    for t, e in obs:
        if n <= 0:
            break
        if e:
            s *= 1 - 1 / n
            if s <= 0.5:
                return t
        n -= 1
    return None


def gpu_class(names):
    for cls, rx in GPU_CLASS:
        if any(re.search(rx, g, re.I) for g in names):
            return cls
    return None


def mine_hardware(con):
    """§6b: what people actually ran, from issue text. Lower bound - unnamed hardware
    is not absent hardware. Writes issue_hardware; returns coverage."""
    con.execute("DELETE FROM issue_hardware")
    rows = con.execute("SELECT id, title, body_excerpt FROM issues WHERE excluded=0").fetchall()
    hit = 0
    for iid, title, body in rows:
        text = f"{title}\n{body or ''}"
        gpus = sorted({re.sub(r"\s+", " ", g.upper()) for g in GPU_RE.findall(text)})
        vram = None
        m = VRAM_RE.search(text)
        if m:
            vram = float(m.group(1) or m.group(2))
        quant = QUANT_RE.search(text)
        if gpus or vram or quant:
            hit += 1
            con.execute("""INSERT OR REPLACE INTO issue_hardware(issue_id, gpu_names, gpu_class,
                           vram_reported_gb, quant_mentioned, extract_method) VALUES(?,?,?,?,?,?)""",
                        (iid, json.dumps(gpus), gpu_class(gpus), vram,
                         quant.group(1).lower() if quant else None, "regex_body"))
    con.commit()
    return hit, len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="regex_baseline")
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    snap = con.execute("SELECT max(snapshot_date) FROM issues").fetchone()[0]
    snap_d = date.fromisoformat(snap)

    issues = [dict(r) for r in con.execute(f"""
        SELECT i.*, l.category_primary cat, l.severity sev, m.release_date, m.support_kind,
               m.vram_floor_fp16_gb, m.params_b
        FROM issues i JOIN models m USING(hf_id)
        LEFT JOIN labels l ON l.issue_id=i.id AND l.source=? AND l.codebook_version='v2'
        WHERE i.excluded=0""", (a.source,))]
    labelled = [i for i in issues if i["cat"]]
    print(f"QUESTIONS 2 & 3 - snapshot {snap}, labels from '{a.source}'")
    print(f"{len(issues)} issues in scope, {len(labelled)} labelled, "
          f"{len(issues) - len(labelled)} unlabelled (excluded from category figures)\n")

    # ---------------- §2 issue load ----------------
    dl = {r[0]: r[1] for r in con.execute(
        "SELECT hf_id, downloads_30d FROM download_snapshots")}
    load = defaultdict(int)
    for i in issues:
        load[(i["hf_id"], i["framework_id"])] += 1
    models = [dict(r) for r in con.execute(
        "SELECT hf_id, release_date, support_kind, band FROM models ORDER BY release_date")]
    print("§2 ISSUE LOAD - first 30 days, per framework (per 100k downloads in parens)\n")
    print(f"{'model':<40}" + "".join(f"{f[:6]:>12}" for f in FWS) + f"{'total':>8}")
    print("-" * (40 + 12 * len(FWS) + 8))
    fw_tot = Counter()
    for m in models:
        if date.fromisoformat(m["release_date"]) + __import__("datetime").timedelta(days=30) > snap_d:
            continue
        cells, tot = [], 0
        d = dl.get(m["hf_id"]) or 0
        for fw in FWS:
            n = load.get((m["hf_id"], fw), 0)
            tot += n
            fw_tot[fw] += n
            per = f"({1e5*n/d:.1f})" if d else ""   # per 100k downloads; per 1k rounds to 0.0
            cells.append(f"{n:>4}{per:>8}")
        print(f"{m['hf_id'][:39]:<40}" + "".join(cells) + f"{tot:>8}")
    print(f"{'ALL':<40}" + "".join(f"{fw_tot[f]:>12}" for f in FWS) + f"{sum(fw_tot.values()):>8}")
    print("\n  Downloads are the Hub's rolling 30-day figure at snapshot, not at release+30 -")
    print("  a stated limitation (metrics §2). Hub downloads measure interest in weights,")
    print("  not use of any framework.")

    # ---------------- §3 time to resolve ----------------
    print(f"\n\n§3 TIME TO RESOLVE - by category (open issues censored at snapshot)\n")
    print(f"{'category':<22}{'n':>5}{'KM med d':>10}{'% open':>8}{'closed:done':>12}{'not_planned':>12}")
    print("-" * 69)
    for cat in CATS:
        rs = [i for i in labelled if i["cat"] == cat]
        if not rs:
            continue
        dur = []
        for i in rs:
            c0 = datetime.fromisoformat(i["created_at"].replace("Z", "+00:00")).date()
            if i["closed_at"]:
                c1 = datetime.fromisoformat(i["closed_at"].replace("Z", "+00:00")).date()
                dur.append(((c1 - c0).days, 1))
            else:
                dur.append(((snap_d - c0).days, 0))
        km = km_median(dur)
        pct_open = 100 * sum(1 for i in rs if not i["closed_at"]) / len(rs)
        done = sum(1 for i in rs if i["state_reason"] == "completed")
        npl = sum(1 for i in rs if i["state_reason"] == "not_planned")
        print(f"{cat:<22}{len(rs):>5}{(str(km) if km is not None else 'n/a'):>10}{pct_open:>7.0f}%"
              f"{done:>12}{npl:>12}")
    print("\n  'completed' vs 'not_planned' is GitHub's close reason - the closest available")
    print("  proxy for fixed-vs-dismissed. closed_by_fix (linked commit) is not collected yet.")

    # ---------------- §4 top problems ----------------
    print(f"\n\n§4 TOP PROBLEMS - count x severity weight, with the reweighting check\n")
    ranks = {}
    for wname, w in WEIGHTS.items():
        score = Counter()
        for i in labelled:
            score[i["cat"]] += w.get(i["sev"], 0)
        ranks[wname] = [c for c, _ in score.most_common()]
        if wname == "default":
            cnt = Counter(i["cat"] for i in labelled)
            sevmix = defaultdict(Counter)
            for i in labelled:
                sevmix[i["cat"]][i["sev"]] += 1
            print(f"{'category':<22}{'n':>5}{'score':>7}{'blocker':>9}{'degraded':>10}{'minor':>7}")
            print("-" * 60)
            for c, s in score.most_common():
                print(f"{c:<22}{cnt[c]:>5}{s:>7}{sevmix[c]['blocker']:>9}{sevmix[c]['degraded']:>10}{sevmix[c]['minor']:>7}")
    print()
    for wname, r in ranks.items():
        print(f"  {wname:<13} top-3: {' > '.join(r[:3])}")
    stable = ranks["default"][:3] == ranks["steep"][:3] == ranks["blocker_only"][:3]
    print(f"\n  top-3 {'STABLE' if stable else 'NOT STABLE'} under reweighting"
          + ("" if stable else " - report the weight-dependence, not a single ranking"))

    print("\n  per-framework category mix (pooled rankings partly re-describe user bases):")
    for fw in FWS:
        rs = [i for i in labelled if i["framework_id"] == fw]
        if not rs:
            continue
        c = Counter(i["cat"] for i in rs)
        top = ", ".join(f"{k} {100*v/len(rs):.0f}%" for k, v in c.most_common(3))
        print(f"    {fw:<13} n={len(rs):<5} {top}")

    # ---------------- §6 hardware ----------------
    hit, tot = mine_hardware(con)
    print(f"\n\n§6 HARDWARE PROFILE - mined from issue text; coverage {hit}/{tot} "
          f"({100*hit/max(tot,1):.0f}%) - a LOWER BOUND\n")
    hw = {r["issue_id"]: dict(r) for r in con.execute("SELECT * FROM issue_hardware")}
    cls = Counter(h["gpu_class"] for h in hw.values() if h["gpu_class"])
    print("  gpu class among issues naming a GPU: " +
          ", ".join(f"{k} {v}" for k, v in cls.most_common()))
    qm = Counter(h["quant_mentioned"] for h in hw.values() if h["quant_mentioned"])
    print("  quant formats mentioned: " + ", ".join(f"{k} {v}" for k, v in qm.most_common(8)))
    # §6c capability gap: OOM issues where reported VRAM < fp16 floor for that model
    oom = [i for i in labelled if i["cat"] == "oom_hardware"]
    gap = [i for i in oom if hw.get(i["id"], {}).get("vram_reported_gb")
           and i["vram_floor_fp16_gb"] and hw[i["id"]]["vram_reported_gb"] < i["vram_floor_fp16_gb"]]
    with_vram = [i for i in oom if hw.get(i["id"], {}).get("vram_reported_gb")]
    print(f"\n  §6c capability gap: of {len(oom)} oom_hardware issues, {len(with_vram)} report VRAM;")
    if with_vram:
        print(f"  {len(gap)}/{len(with_vram)} ({100*len(gap)/len(with_vram):.0f}%) attempted a model whose fp16")
        print("  floor exceeds the card they named - a demand signal for day-0 quantized artifacts")
        print("  (checklist 2.1), not user error.")
    print("\n  Hardware is self-reported by the subset of users who filed issues; these")
    print("  figures describe REPORTERS, not users, and no reweighting fixes that.")

    # per-framework gpu class mix
    print("\n  gpu class by framework (where named):")
    for fw in FWS:
        c = Counter(hw[i["id"]]["gpu_class"] for i in issues
                    if i["framework_id"] == fw and i["id"] in hw and hw[i["id"]]["gpu_class"])
        if c:
            tot_fw = sum(c.values())
            print(f"    {fw:<13} " + ", ".join(f"{k} {100*v/tot_fw:.0f}%" for k, v in c.most_common()))


if __name__ == "__main__":
    main()
