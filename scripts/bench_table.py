"""Classifier benchmark table (README deliverable): accuracy on the hand-labelled TEST split,
coverage, throughput and peak memory per classifier source.

    bench_table.py --sources regex_baseline,ref_claude,llm,llm:qwen3-1.7b,llm:gemma3-1b \
                   --ram llm=3100000,llm:gemma3-1b=1200000      # peak RSS in KB, optional

Accuracy is computed two ways because they answer different questions: over the issues the
model actually labelled (what it gets right when it answers), and over all scored test
issues with a parse failure counted wrong (what a pipeline built on it would get).
Throughput comes from the run records classify_llm.py writes (issues labelled / wall time).
"""
import argparse, sqlite3, statistics, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agreement import kappa

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--ram", default="", help="source=peak_rss_kb,...")
    a = ap.parse_args()
    ram = dict(kv.split("=") for kv in a.ram.split(",") if "=" in kv)
    con = sqlite3.connect(DB, timeout=60)
    gold = {r[0]: (r[1], r[2]) for r in con.execute(
        """SELECT h.issue_id, h.category_primary, h.severity FROM labels h
           WHERE h.source='hand' AND h.split=? AND h.category_primary IS NOT NULL
           AND EXISTS (SELECT 1 FROM issues i WHERE i.id=h.issue_id AND i.excluded=0)""", (a.split,))}
    n_gold = len(gold)
    print(f"CLASSIFIER BENCHMARK - {a.split} split vs hand labels (n={n_gold}), codebook v2\n")
    print(f"{'classifier':<20}{'labelled':>9}{'cat acc':>9}{'κ':>6}{'acc*':>7}{'sev acc':>9}{'sev κ':>7}"
          f"{'issues/min':>12}{'peak RAM':>10}")
    for src in [s.strip() for s in a.sources.split(",")]:
        pred = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT issue_id, category_primary, severity FROM labels WHERE source=? AND category_primary IS NOT NULL",
            (src,))}
        ids = sorted(set(gold) & set(pred))
        if not ids:
            print(f"{src:<20}  no overlap"); continue
        cg = [gold[i][0] for i in ids]; cp = [pred[i][0] for i in ids]
        sg = [gold[i][1] for i in ids]; sp = [pred[i][1] for i in ids]
        hit = sum(x == y for x, y in zip(cg, cp))
        # throughput: median gap between consecutive labels within a run. Wall time / count is
        # dominated by endpoint stalls (one CPU run lost ~4 h to timeouts); the median is the
        # steady-state rate. Raw wall times stay in runs.notes.
        gaps = []
        for (run,) in con.execute("SELECT DISTINCT run_id FROM labels WHERE source=? AND run_id IS NOT NULL", (src,)):
            ts = [datetime.fromisoformat(t) for (t,) in con.execute(
                "SELECT labeled_at FROM labels WHERE run_id=? ORDER BY labeled_at", (run,))]
            gaps += [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
        med = statistics.median(gaps) if len(gaps) >= 10 else 0
        ipm = f"{60 / med:.1f}" if med > 0 else ("instant" if src == "regex_baseline" else "—")
        r = ram.get(src)
        mem = f"{int(r) / 2**20:.1f} GB" if r else ("0" if src in ("regex_baseline", "ref_claude") else "—")
        print(f"{src:<20}{len(ids):>4}/{n_gold:<4}{100 * hit / len(ids):>8.1f}%{kappa(cg, cp):>6.2f}"
              f"{100 * hit / n_gold:>6.1f}%{100 * sum(x == y for x, y in zip(sg, sp)) / len(ids):>8.1f}%"
              f"{kappa(sg, sp):>7.2f}{ipm:>12}{mem:>10}")
    print("\n acc* = parse failures counted wrong (denominator = all scored issues).")
    print(" Throughput and RAM are a 2018 Intel MacBook (4-core i5, 8 GB, CPU only, Ollama Q4).")
    print(" The labelers agree with each other 57% / κ 0.49: no classifier can be shown to beat that here.")


if __name__ == "__main__":
    main()
