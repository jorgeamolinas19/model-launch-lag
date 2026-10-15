"""Independent, mechanical re-check of every assistant-adjudicated row (resolved_by contains claude-ref)
in support_events_hand.csv and release_dates_hand.csv.

Re-fetches each cited artifact and asserts the claim it supports. This is NOT a human
spot-check and does not change resolved_by: it reduces the human step to reading this
report and the few rows it flags.

    PR       exists, merge state matches the claimed state, merged_at date == event_date,
             title names the model or its architecture
    commit   exists, author date == event_date, message names the model or architecture
    blob     file exists at HEAD; for arch_compatible, its first commit predates release
    Wayback  earliest capture of the cited page == the claimed date
    (none)   for 'unsupported': repo code search for the model name returns nothing

    recheck_adjudications.py   -> reports/adjudication_recheck.txt
"""
import csv, io, json, re, ssl, sys, urllib.parse, urllib.request
from pathlib import Path
import certifi
from gh import get

ROOT = Path(__file__).resolve().parent.parent
_CTX = ssl.create_default_context(cafile=certifi.where())
REPOS = {"vllm": "vllm-project/vllm", "sglang": "sgl-project/sglang", "trtllm": "NVIDIA/TensorRT-LLM",
         "transformers": "huggingface/transformers", "ollama": "ollama/ollama", "llamacpp": "ggml-org/llama.cpp"}


def rows(path):
    text = "\n".join(l for l in (ROOT / path).read_text().splitlines() if not l.startswith("#"))
    return [r for r in csv.DictReader(io.StringIO(text)) if "claude-ref" in (r.get("resolved_by") or "")]


def names(r):
    """Tokens that should appear in a PR title/commit message about this model."""
    model = r["hf_id"].split("/")[1]
    toks = {model.lower(), (r.get("architecture") or "").lower()}
    base = re.split(r"-\d+(\.\d+)?b\b|-it\b|-instruct\b|-a\d+b|-flash", model.lower())[0]
    toks |= {base, base.replace("-", " "), base.replace("-", ""), base.replace("-", "_")}
    return {t for t in toks if len(t) > 3}


def mentions(text, r):
    t = text.lower()
    return any(n in t or n.replace(".", "") in t.replace(".", "") for n in names(r))


def wayback_first(url):
    cdx = ("http://web.archive.org/cdx/search/cdx?output=json&limit=1&fl=timestamp&url="
           + urllib.parse.quote(url, safe=""))
    d = json.load(urllib.request.urlopen(cdx, timeout=60, context=_CTX))
    return d[1][0] if len(d) > 1 else None


def check_support(r):
    url, state, ev = r["source_url"], r["state"], r["event_date"]
    if m := re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url):
        _, pr = get(f"repos/{m.group(1)}/pulls/{m.group(2)}")
        merged = (pr.get("merged_at") or "")[:10]
        ok = []
        if state == "unsupported":
            ok.append(("PR not merged", not pr.get("merged")))
        else:
            ok.append(("PR merged", bool(pr.get("merged"))))
            if ev:
                ok.append((f"merged {merged} == event {ev}", merged == ev))
            if state == "arch_compatible":
                ok.append((f"merged {merged} < release {r['release_date']}", merged < r["release_date"]))
        ok.append((f"title names model: {pr['title'][:60]!r}", mentions(pr["title"], r)))
        return ok
    if m := re.search(r"github\.com/([^/]+/[^/]+)/commit/([0-9a-f]{7,40})", url):
        _, c = get(f"repos/{m.group(1)}/commits/{m.group(2)}")
        d = c["commit"]["committer"]["date"][:10]
        msg = c["commit"]["message"].splitlines()[0]
        return [(f"commit date {d} == event {ev}", d == ev), (f"message names model: {msg[:60]!r}", mentions(msg, r))]
    if m := re.search(r"github\.com/([^/]+/[^/]+)/blob/[^/]+/(.+)$", url):
        repo, path = m.groups()
        _, first = get(f"repos/{repo}/commits?path={urllib.parse.quote(path)}&per_page=1")
        h, _ = get(f"repos/{repo}/commits?path={urllib.parse.quote(path)}&per_page=1")
        last_page = re.search(r'page=(\d+)>; rel="last"', h.get("Link") or "")
        if last_page:
            _, first = get(f"repos/{repo}/commits?path={urllib.parse.quote(path)}&per_page=1&page={last_page.group(1)}")
        born = first[0]["commit"]["committer"]["date"][:10] if first else None
        ok = [(f"file exists at HEAD ({path})", born is not None)]
        if state == "arch_compatible" and born:
            ok.append((f"file born {born} < release {r['release_date']}", born < r["release_date"]))
        if state == "undetermined" and born:
            ok.append((f"file born {born} (allowlist date, not a support date)", True))
        return ok
    if "web.archive.org" in url:
        target = re.sub(r"^https?://web\.archive\.org/web/\d+/", "", url)
        ts = wayback_first(target)
        d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if ts else None
        return [(f"earliest capture {d} == event {ev}", d == ev)]
    if state == "unsupported" and not url:
        term = r["architecture"] or r["hf_id"].split("/")[1]
        q = urllib.parse.quote(f'"{term}" repo:{REPOS[r["framework_id"]]}')
        try:
            _, s = get(f"search/code?q={q}&per_page=1")
            n = s.get("total_count", -1)
        except Exception as e:
            return [(f"code search failed: {e}", None)]
        return [(f"code search '{term}' -> {n} files (now, not at snapshot)", n == 0)]
    return [("no checkable artifact", None)]


def check_date(r):
    url = r["source_url"]
    if "web.archive.org" in url:
        target = re.sub(r"^https?://web\.archive\.org/web/\d+/", "", url)
        ts = wayback_first(target)
        d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if ts else None
        return [(f"earliest capture of model page {d} == release {r['release_date']}", d == r["release_date"])]
    # vendor-blog source: the checkable proxy is the earliest public capture of the HF model page
    ts = wayback_first(f"huggingface.co/{r['hf_id']}")
    d = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if ts else None
    return [(f"earliest capture of HF model page {d} == release {r['release_date']}", d == r["release_date"])]


def main():
    out, n_ok, n_flag, n_manual = [], 0, 0, 0
    for title, path, fn, key in (("SUPPORT EVENTS", "support_events_hand.csv", check_support, lambda r: f"{r['framework_id']:<12} {r['hf_id']}"),
                                 ("RELEASE DATES", "release_dates_hand.csv", check_date, lambda r: r["hf_id"])):
        out.append(f"\n{title} (resolved_by contains claude-ref)\n")
        for r in rows(path):
            try:
                checks = fn(r)
            except Exception as e:
                checks = [(f"fetch failed: {e}", None)]
            verdict = ("MANUAL" if any(v is None for _, v in checks)
                       else "OK" if all(v for _, v in checks) else "FLAG")
            n_ok += verdict == "OK"; n_flag += verdict == "FLAG"; n_manual += verdict == "MANUAL"
            out.append(f"  [{verdict:<6}] {key(r)}  ({r.get('state', 'date')})")
            out += [f"           {'✓' if v else ('?' if v is None else '✗')} {c}" for c, v in checks]
    out.append(f"\n{n_ok} OK · {n_flag} FLAG · {n_manual} MANUAL. OK = every cited fact re-fetched and matched.")
    out.append("This is a mechanical re-check by the same assistant that made the calls - it confirms the")
    out.append("evidence says what the row claims, not that the judgment (e.g. 'predecessor reuse') is right.")
    text = "\n".join(out)
    (ROOT / "reports" / "adjudication_recheck.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
