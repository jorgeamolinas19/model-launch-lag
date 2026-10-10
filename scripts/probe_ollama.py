#!/usr/bin/env python3
"""Find a per-model, first-publish date source for the Ollama library.

ollama.com/api/tags?name= returns byte-identical payloads for different model names,
so it ignores the query and cannot date a library entry. Ollama's evidence rule depends
on SOME per-model date, so this tries the remaining candidates and reports which (if
any) actually discriminate between models.
"""
import json
import re
import ssl
import urllib.error
import urllib.request

import certifi

CTX = ssl.create_default_context(cafile=certifi.where())
MODELS = ["qwen3", "gemma3", "deepseek-r1"]
OCI_ACCEPT = ("application/vnd.docker.distribution.manifest.v2+json,"
              "application/vnd.oci.image.manifest.v1+json")


def fetch(url, accept=None, raw=False):
    h = {"User-Agent": "model-launch-lag"}
    if accept:
        h["Accept"] = accept
    r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30, context=CTX)
    b = r.read()
    return r.status, (b if raw else b.decode("utf-8", "replace"))


def try_source(label, url_fn, accept=None, extract=None):
    """Report whether a source returns DIFFERENT content per model (the real test)."""
    sigs, notes = {}, []
    for m in MODELS:
        try:
            st, body = fetch(url_fn(m), accept)
            sig = extract(body) if extract else body[:200]
            sigs[m] = sig
            notes.append(f"{m}={str(sig)[:46]}")
        except urllib.error.HTTPError as e:
            sigs[m] = f"HTTP{e.code}"
            notes.append(f"{m}=HTTP{e.code}")
        except Exception as e:
            sigs[m] = type(e).__name__
            notes.append(f"{m}={type(e).__name__}")
    vals = list(sigs.values())
    ok = len(set(map(str, vals))) > 1 and not all(str(v).startswith(("HTTP", "SSL", "URL")) for v in vals)
    print(f"\n[{'DISCRIMINATES' if ok else 'useless      '}] {label}")
    for n in notes:
        print(f"    {n}")
    return ok


def dates_in(body):
    d = sorted(set(re.findall(r"\d{4}-\d{2}-\d{2}", body)))
    if d:
        return f"{len(d)} dates {d[0]}..{d[-1]}"
    rel = re.findall(r"(\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago)", body)
    return f"{len(rel)} relative: {rel[:3]}" if rel else "no dates found"


if __name__ == "__main__":
    results = {}
    results["registry tags/list"] = try_source(
        "registry.ollama.ai/v2/library/<m>/tags/list",
        lambda m: f"https://registry.ollama.ai/v2/library/{m}/tags/list", "application/json")
    results["registry manifest"] = try_source(
        "registry.ollama.ai/v2/library/<m>/manifests/latest (OCI)",
        lambda m: f"https://registry.ollama.ai/v2/library/{m}/manifests/latest", OCI_ACCEPT,
        lambda b: (json.loads(b).get("config", {}).get("digest", "?")[:24]
                   if b.strip().startswith("{") else b[:40]))
    results["library html"] = try_source(
        "ollama.com/library/<m> (HTML)",
        lambda m: f"https://ollama.com/library/{m}", None, dates_in)
    results["api show"] = try_source(
        "ollama.com/api/show?name=<m>",
        lambda m: f"https://ollama.com/api/show?name={m}", "application/json",
        lambda b: b[:60])
    print("\n" + "=" * 74)
    live = [k for k, v in results.items() if v]
    print(f"usable per-model sources: {live if live else 'NONE'}")
    if not live:
        print("-> Ollama evidence rule needs a different basis; see docs/evidence-rules.md")
