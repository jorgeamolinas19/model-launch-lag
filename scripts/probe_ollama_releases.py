#!/usr/bin/env python3
"""Do ollama/ollama release notes name newly-supported models? If so they are a
dateable, per-model evidence source and the Ollama rule can rest on them."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import gh

NAMES = ["qwen3", "qwen3.5", "qwen3.8", "gemma 4", "gemma4", "gemma 3", "deepseek",
         "kimi", "glm", "nemotron", "olmo", "granite", "llama 4", "gpt-oss", "mistral"]

if __name__ == "__main__":
    _, rels = gh.get("repos/ollama/ollama/releases?per_page=40")
    print(f"scanned {len(rels)} ollama/ollama releases\n")
    hits = 0
    for r in rels:
        body = (r.get("body") or "").lower()
        found = sorted({n for n in NAMES if n in body})
        if found:
            hits += 1
            first = (r.get("body") or "").strip().splitlines()
            lead = next((l.strip("#* ") for l in first if l.strip()), "")[:68]
            print(f"  {r.get('tag_name','?'):<12} {(r.get('published_at') or '')[:10]}  "
                  f"{','.join(found)[:44]:<44} | {lead}")
    print(f"\n{hits}/{len(rels)} releases name at least one cohort-relevant model family")
    print("-> release notes ARE a usable per-model, dateable source" if hits >= len(rels) // 4
          else "-> release notes are too sparse to date support on their own")
