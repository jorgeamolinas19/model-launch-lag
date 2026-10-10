#!/usr/bin/env python3
"""The overview table for question 1: how fast did each model become runnable?

Reports latency ALWAYS beside coverage and censored counts. A median over only the
supported pairs is biased downward and makes a framework that skips hard models look
fastest, so this script refuses to print a bare median (docs/metrics.md §1).
"""
import argparse
import sqlite3
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "launch_lag.sqlite"
FWS = ["transformers", "vllm", "sglang", "llamacpp", "ollama", "trtllm"]


def km_median(durations, censored):
    """Kaplan-Meier median. durations: (time, event_observed) pairs.

    Returns None when survival never reaches 0.5 - i.e. more than half of pairs are
    still unsupported, in which case no median exists and saying so is the honest
    answer rather than substituting the observed-only median.
    """
    obs = sorted(durations)
    n_at_risk = len(obs)
    s = 1.0
    for t, event in obs:
        if n_at_risk <= 0:
            break
        if event:
            s *= 1 - 1 / n_at_risk
            if s <= 0.5:
                return t
        n_at_risk -= 1
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="new_arch", choices=["new_arch", "variant", "all"])
    a = ap.parse_args()
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    where = "" if a.kind == "all" else f"AND m.support_kind='{a.kind}'"
    rows = [dict(r) for r in con.execute(f"""
        SELECT s.framework_id fw, s.hf_id, s.state, s.days_to_support d, s.fidelity,
               m.support_kind, m.band, m.release_date, m.architecture
        FROM support_events s JOIN models m USING(hf_id)
        WHERE 1=1 {where}""")]
    if not rows:
        print("no support_events yet - run collect_support.py")
        return
    snap = con.execute("SELECT max(snapshot_date) FROM support_events").fetchone()[0]

    print(f"DAYS TO SUPPORT - {a.kind} models, snapshot {snap}")
    print("Negative = merged before public release (early access). Latency is only")
    print("interpretable beside coverage: see the censored column.\n")
    hdr = (f"{'framework':<14}{'cover':>8}{'KM med':>8}{'obs med':>9}"
           f"{'early':>7}{'day0':>6}{'cens':>6}{'part':>6}  fidelity")
    print(hdr)
    print("-" * len(hdr))
    for fw in FWS:
        r = [x for x in rows if x["fw"] == fw]
        if not r:
            continue
        sup = [x for x in r if x["state"] in ("supported", "partial") and x["d"] is not None]
        cens = [x for x in r if x["state"] == "unsupported"]
        part = [x for x in r if x["state"] == "partial"]
        # Censored pairs enter the KM fit at their censoring time, not as missing rows.
        dur = [(x["d"], 1) for x in sup] + [(9999, 0) for _ in cens]
        km = km_median(dur, cens)
        obs = statistics.median([x["d"] for x in sup]) if sup else None
        fid = ",".join(sorted({x["fidelity"] for x in r}))
        cover = f"{len(sup)}/{len(r)}"
        print(f"{fw:<14}{cover:>8}{(f'{km:+d}' if km is not None else 'n/a'):>8}"
              f"{(f'{obs:+.0f}' if obs is not None else '-'):>9}"
              f"{sum(1 for x in sup if x['d'] < 0):>7}{sum(1 for x in sup if x['d'] == 0):>6}"
              f"{len(cens):>6}{len(part):>6}  {fid}")

    print("\n  KM med = Kaplan-Meier median including censored pairs (the defensible figure)")
    print("  obs med = median over supported pairs only (biased low; shown for contrast)")
    print("  n/a     = over half the pairs are still unsupported, so no median exists")
    und = [x for x in rows if x["state"] == "undetermined"]
    if und:
        print(f"  {len(und)} pair(s) undetermined and excluded from every figure above; "
              f"see hand-resolution list")
    inh = con.execute("""SELECT count(*) FROM support_events s JOIN models m USING(hf_id)
        WHERE s.evidence_rule LIKE '%:inherited(%' AND m.support_kind='new_arch'""").fetchone()[0]
    if inh:
        print(f"\n  CAUTION: {inh} new_arch pair(s) are recorded at day 0 because the")
        print("  architecture was ALREADY declared at the commit before release. For a new")
        print("  architecture that means pre-release support, so the true value is <= 0 and")
        print("  0 is a conservative FLOOR, not a measurement. Dating how far ahead would")
        print("  need the arch-addition commit, which is still unresolved. This UNDERSTATES")
        print("  early access rather than overstating it.")

    # transformers native latency is misleading where the model shipped its own code.
    rc = list(con.execute(f"""
        SELECT m.hf_id, s.days_to_support, m.remote_code_evidence
        FROM models m JOIN support_events s ON s.hf_id=m.hf_id AND s.framework_id='transformers'
        WHERE m.ships_remote_code=1 {where.replace('m.', 'm.')}
        ORDER BY s.days_to_support DESC"""))
    if rc:
        print("\n\nREMOTE CODE: where native-only latency overstates the real wait\n")
        print("These models ship their own modeling code, so they are runnable in")
        print("transformers at RELEASE. The native date is a second milestone, not the")
        print("first one - quoting it alone would misrepresent the developer experience.\n")
        for hf_id, d, ev in rc:
            native = f"native {d:+d}d" if d is not None else "native not yet"
            print(f"  {hf_id[:45]:<46} remote_code day 0 | {native:<16} ({ev})")

    # Per-model matrix
    models = sorted({(x["release_date"], x["hf_id"]) for x in rows})
    print(f"\n\nPER-MODEL ({a.kind})\n")
    print(f"{'released':<11}{'model':<44}" + "".join(f"{f[:6]:>8}" for f in FWS))
    print("-" * (55 + 8 * len(FWS)))
    for rd, hf in models:
        cells = []
        for fw in FWS:
            e = next((x for x in rows if x["hf_id"] == hf and x["fw"] == fw), None)
            if not e:
                cells.append("-")
            elif e["state"] == "unsupported":
                cells.append("none")
            elif e["d"] is None:
                cells.append("?")
            else:
                cells.append(f"{e['d']:+d}" + ("p" if e["state"] == "partial" else ""))
        print(f"{rd:<11}{hf[:43]:<44}" + "".join(f"{c:>8}" for c in cells))
    print("\n  p = partial support (some required parts landed, model not yet runnable)")
    print("  none = no qualifying artifact as of snapshot (right-censored, not missing)")

    # Time trend: the confound the historical band exists to measure
    print("\n\nTIME TREND (the confound the historical band exists to measure)\n")
    for band in ("historical", "primary"):
        b = [x for x in rows if x["band"] == band and x["d"] is not None
             and x["state"] in ("supported", "partial")]
        c = [x for x in rows if x["band"] == band and x["state"] == "unsupported"]
        if not b:
            continue
        print(f"  {band:<11} n={len(b):>3} supported, {len(c):>3} censored | "
              f"median {statistics.median([x['d'] for x in b]):+.0f}d | "
              f"early {sum(1 for x in b if x['d'] < 0)} | day0 {sum(1 for x in b if x['d'] == 0)}")
    print("\n  Any band-to-band difference is confounded with cohort composition; it is a")
    print("  descriptive contrast, not a causal claim about frameworks improving.")


if __name__ == "__main__":
    main()
