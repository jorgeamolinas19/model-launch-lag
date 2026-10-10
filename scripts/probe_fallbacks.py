#!/usr/bin/env python3
"""Find a working release-notes source per framework, and a first-publish date source
for Ollama. Both are fallback evidence paths that verify_paths.py found wanting."""
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import certifi

sys.path.insert(0, str(Path(__file__).parent))
import gh

REPOS = ["huggingface/transformers", "vllm-project/vllm", "sgl-project/sglang",
         "ggml-org/llama.cpp", "ollama/ollama", "NVIDIA/TensorRT-LLM"]
TRT_CANDIDATES = ["CHANGELOG.md", "docs/source/release-notes.md",
                  "docs/source/reference/release-notes.md", "docs/release-notes.md"]


def releases():
    print("GitHub Releases API (framework-independent release-note source)")
    for r in REPOS:
        try:
            _, d = gh.get(f"repos/{r}/releases?per_page=3")
            if not d:
                print(f"  [----] {r:<28} 0 releases published")
                continue
            latest = d[0]
            body = (latest.get("body") or "")
            print(f"  [ok  ] {r:<28} {len(d)}+ releases | latest {latest.get('tag_name')} "
                  f"@ {(latest.get('published_at') or '')[:10]} | notes {len(body)} chars")
        except urllib.error.HTTPError as e:
            print(f"  [FAIL] {r:<28} HTTP {e.code}")


def trt_changelog():
    print("\nTensorRT-LLM release-notes file candidates")
    for p in TRT_CANDIDATES:
        got = gh.exists("NVIDIA/TensorRT-LLM", p)
        print(f"  [{'ok  ' if got else 'FAIL'}] {p:<44} {got or 'not found'}")


def ollama_tags():
    """Is there a FIRST-publish date, or only a modified date?"""
    print("\nOllama: first-publish vs modified date")
    ctx = ssl.create_default_context(cafile=certifi.where())
    for name in ("qwen3", "nemotron-3-nano", "gemma4"):
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                f"https://ollama.com/api/tags?name={name}",
                headers={"User-Agent": "model-launch-lag"}), timeout=30, context=ctx)
            d = json.load(r)
            ms = d.get("models") or []
            dates = sorted({(m.get("modified_at") or "")[:10] for m in ms if m.get("modified_at")})
            print(f"  {name:<18} {len(ms):>3} tags | modified_at range "
                  f"{dates[0] if dates else '?'} .. {dates[-1] if dates else '?'}")
        except urllib.error.HTTPError as e:
            print(f"  {name:<18} HTTP {e.code}")
        except Exception as e:
            print(f"  {name:<18} {type(e).__name__}")


if __name__ == "__main__":
    releases()
    trt_changelog()
    ollama_tags()
