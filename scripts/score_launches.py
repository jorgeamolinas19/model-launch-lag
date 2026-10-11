"""Readiness-checklist validation (docs/readiness-checklist.md, "Scoring a launch").

Score each cohort model on the checklist items that the collected data can decide, then
test whether the score predicts the two observed outcomes. If it does not correlate, the
checklist is wrong - the doc says so - and this script exists to make that visible.

Items scored (1 point each; only data-decidable items):
  1.1  support merged pre-release in >=1 framework       (support_events.days_to_support < 0)
  1.2  runnable in transformers on day 0                  (native <= 0 d OR ships_remote_code)
  2.1a GGUF repo within 7 days                            (quant_artifacts, metrics §7)
  2.1b FP8 repo within 7 days
  2.1c NVFP4 repo within 7 days

Outcomes:
  issue_load_norm  kept first-30-day issues per 100k downloads (metrics §2)
  median_dts       median signed days_to_support over supported frameworks (new_arch only)

Spearman rank correlation, stdlib only, with n printed beside every figure.
"""
import sqlite3, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"


def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):            # average ranks for ties
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(x, y):
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else float("nan")


def main():
    con = sqlite3.connect(DB, timeout=60)
    models = con.execute("""SELECT hf_id, support_kind, band, ships_remote_code, release_date FROM models
                            WHERE in_cohort=1 ORDER BY release_date""").fetchall()
    rows = []
    for hf_id, kind, band, remote, rel in models:
        ev = con.execute("""SELECT framework_id, days_to_support FROM support_events
                            WHERE hf_id=? AND state IN ('supported','partial') AND days_to_support IS NOT NULL""",
                         (hf_id,)).fetchall()
        dts = {f: d for f, d in ev}
        quant = {f: (min_d) for f, min_d in con.execute("""SELECT fmt, min(julianday(published_at)-julianday(?))
                 FROM quant_artifacts WHERE hf_id=? AND published_at!='' GROUP BY fmt""", (rel, hf_id))}
        items = {
            "1.1": any(d < 0 for d in dts.values()),
            "1.2": bool(remote) or dts.get("transformers", 99) <= 0,
            "2.1a": quant.get("gguf", 99) <= 7,
            "2.1b": quant.get("fp8", 99) <= 7,
            "2.1c": quant.get("nvfp4", 99) <= 7,
        }
        n_iss = con.execute("SELECT count(*) FROM issues WHERE hf_id=? AND excluded=0", (hf_id,)).fetchone()[0]
        dl = con.execute("SELECT downloads_30d FROM download_snapshots WHERE hf_id=? ORDER BY fetched_at DESC LIMIT 1",
                         (hf_id,)).fetchone()
        norm = n_iss / (dl[0] / 1e5) if dl and dl[0] else None
        med = statistics.median(dts.values()) if dts else None
        rows.append((hf_id, kind, band, items, sum(items.values()), n_iss, norm, med))

    print("LAUNCH SCORE vs OUTCOMES - checklist validation step")
    print("items: 1.1 pre-release merge | 1.2 day-0 transformers (native or remote code) | 2.1a/b/c GGUF/FP8/NVFP4 repo <=7d\n")
    print(f"{'model':<44}{'kind':<10}{'1.1':>4}{'1.2':>4}{'gguf':>5}{'fp8':>4}{'nvfp4':>6}{'score':>6}{'issues':>7}{'/100k dl':>9}{'med dts':>8}")
    for hf_id, kind, band, it, sc, n, norm, med in rows:
        f = lambda k: " x" if it[k] else " ."
        print(f"{hf_id[:43]:<44}{kind:<10}{f('1.1'):>4}{f('1.2'):>4}{f('2.1a'):>5}{f('2.1b'):>4}{f('2.1c'):>6}{sc:>6}{n:>7}"
              f"{(f'{norm:.1f}' if norm is not None else 'NA'):>9}{(f'{med:+.0f}' if med is not None else 'NA'):>8}")

    def corr(label, pairs):
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        if len(pairs) < 5:
            print(f"  {label}: n={len(pairs)} too small"); return
        rho = spearman([a for a, _ in pairs], [b for _, b in pairs])
        print(f"  {label}: Spearman rho = {rho:+.2f}  (n={len(pairs)})")

    print("\ncorrelations (negative rho = higher score, better outcome):")
    corr("score vs issues per 100k downloads, all models", [(sc, norm) for *_, sc, n, norm, med in rows])
    corr("score vs median days-to-support, new_arch only", [(sc, med) for _, k, _, _, sc, n, norm, med in rows if k == "new_arch"])
    corr("score WITHOUT 1.1 vs median days-to-support, new_arch (1.1 is itself a support date)",
         [(sc - it["1.1"], med) for _, k, _, it, sc, n, norm, med in rows if k == "new_arch"])
    corr("quant items only (2.1a-c) vs median days-to-support, new_arch",
         [(sum(it[k] for k in ("2.1a", "2.1b", "2.1c")), med) for _, k, _, it, sc, n, norm, med in rows if k == "new_arch"])
    corr("score vs raw issue count, all models", [(sc, n) for *_, sc, n, norm, med in rows])
    corr("quant items only (2.1a-c) vs issues per 100k", [(sum(it[k] for k in ("2.1a", "2.1b", "2.1c")), norm) for _, _, _, it, sc, n, norm, med in rows])
    print("\n  n=22 and the two bands differ in both score and outcome (time trend, metrics §8), so a")
    print("  |rho| below ~0.4 is indistinguishable from noise here. Report it either way.")
    primary = [r for r in rows if r[2] == "primary"]
    corr("score vs issues per 100k, primary band only", [(sc, norm) for *_, sc, n, norm, med in primary])


if __name__ == "__main__":
    main()
