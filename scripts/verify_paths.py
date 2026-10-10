#!/usr/bin/env python3
"""Verify every path in docs/evidence-rules.md still exists at each repo's HEAD.

The rules were written from prior familiarity, not from a live read, so this is the
gate before any support-event collection: a stale glob silently yields zero support
events, which reads as "never supported" rather than as a broken collector.

Also probes the Ollama registry, whose evidence rule depends on an endpoint outside
the GitHub API and therefore on an assumption worth testing early.
"""
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi

sys.path.insert(0, str(Path(__file__).parent))
import gh

# (framework, repo, [(path, expected_kind, why_it_matters)])
CHECKS = [
    ("transformers", "huggingface/transformers", [
        ("src/transformers/models", "dir", "native arch support lives here"),
    ]),
    ("vllm", "vllm-project/vllm", [
        ("vllm/model_executor/models", "dir", "model implementations"),
        ("vllm/model_executor/models/registry.py", "file", "arch registration"),
        ("docs/models/supported_models.md", "file", "secondary evidence: docs table"),
    ]),
    ("sglang", "sgl-project/sglang", [
        ("python/sglang/srt/models", "dir", "model implementations"),
    ]),
    ("llamacpp", "ggml-org/llama.cpp", [
        ("convert_hf_to_gguf.py", "file", "part 1: arch mapping for conversion"),
        ("src/llama-model.cpp", "file", "part 2: graph construction"),
        ("src/llama-vocab.cpp", "file", "part 3: tokenizer handling"),
    ]),
    ("ollama", "ollama/ollama", [
        ("server", "dir", "Go-side work when a new arch needs it"),
    ]),
    ("trtllm", "NVIDIA/TensorRT-LLM", [
        ("tensorrt_llm/models", "dir", "model definitions"),
        ("examples", "dir", "fallback evidence: per-model examples"),
        ("CHANGELOG.md", "file", "fallback evidence: release notes"),
    ]),
]


def check_repo(fw, repo, paths):
    info = gh.repo_info(repo)
    if not info:
        print(f"\n{fw:<13} {repo}\n  REPO NOT FOUND - evidence rule is unusable as written")
        return [(fw, repo, "<repo>", "MISSING")]
    canon, meta = info
    renamed = "" if canon.lower() == repo.lower() else f"  (redirects to {canon})"
    print(f"\n{fw:<13} {canon}{renamed}")
    print(f"  default branch {meta.get('default_branch')} | "
          f"{meta.get('stargazers_count', 0):,} stars | "
          f"open issues {meta.get('open_issues_count', 0):,}")
    bad = []
    for path, want, why in paths:
        got = gh.exists(canon, path)
        ok = got == want
        mark = "ok  " if ok else "FAIL"
        print(f"  [{mark}] {path:<42} {('found ' + got) if got else 'NOT FOUND':<10} {why}")
        if not ok:
            bad.append((fw, canon, path, got or "missing"))
    return bad


def probe_ollama():
    """Can we date an Ollama library entry without the GitHub API?"""
    print("\nollama registry probe (evidence rule: library publish date)")
    ctx = ssl.create_default_context(cafile=certifi.where())
    for url, label in [
        ("https://registry.ollama.ai/v2/library/qwen3/tags/list", "tags list"),
        ("https://ollama.com/api/tags?name=qwen3", "web api"),
    ]:
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "model-launch-lag"}), timeout=30, context=ctx)
            body = r.read(1200)
            try:
                parsed = json.loads(body)
                keys = sorted(parsed)[:8] if isinstance(parsed, dict) else f"list[{len(parsed)}]"
            except Exception:
                keys = body[:120]
            print(f"  [ok  ] {label:<10} HTTP {r.status}  keys={keys}")
        except urllib.error.HTTPError as e:
            print(f"  [FAIL] {label:<10} HTTP {e.code}")
        except Exception as e:
            print(f"  [FAIL] {label:<10} {type(e).__name__}")


def main():
    lim, rem = gh.rate()
    print(f"github rate limit {rem}/{lim} remaining"
          f"{'  (ANONYMOUS - expect throttling)' if lim <= 60 else ''}")
    bad = []
    for fw, repo, paths in CHECKS:
        try:
            bad += check_repo(fw, repo, paths)
        except urllib.error.HTTPError as e:
            print(f"\n{fw:<13} {repo}\n  ERROR HTTP {e.code}")
            bad.append((fw, repo, "<error>", str(e.code)))
    probe_ollama()
    lim, rem2 = gh.rate()
    print(f"\n{'=' * 78}")
    if bad:
        print(f"{len(bad)} STALE PATH(S) - docs/evidence-rules.md must be corrected before collection:")
        for fw, repo, path, got in bad:
            print(f"  {fw:<13} {repo:<28} {path}  ({got})")
    else:
        print("all evidence-rule paths resolve at HEAD")
    print(f"api calls used: {rem - rem2}")


if __name__ == "__main__":
    main()
