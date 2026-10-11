"""Smallest thing that fails if the non-trivial helpers break. No framework, no DB.

    python3 scripts/selfcheck.py
"""
import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agreement import kappa
from score_launches import ranks, spearman
from collect_quants import fmt_of, publisher_kind

# kappa: perfect agreement 1, chance-level ~0
assert kappa(list("aabb"), list("aabb")) == 1.0
assert abs(kappa(list("abab"), list("aabb"))) < 1e-9

# ranks with ties average; spearman is +1 on a monotone pair, -1 reversed, ~0 on a shuffle
assert ranks([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]
assert abs(spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-9
assert abs(spearman([1, 2, 3, 4], [40, 30, 20, 10]) + 1) < 1e-9
assert abs(spearman([1, 2, 3, 4, 5], [3, 1, 5, 2, 4])) < 0.5

# quant format: first match wins, generic 4-bit spellings land in int4, plain repos are None
assert fmt_of("unsloth/Qwen3.8-27B-GGUF") == "gguf"
assert fmt_of("nvidia/DeepSeek-V3-NVFP4") == "nvfp4"
assert fmt_of("mlx-community/gemma-4-31B-it-4bit") == "mlx"      # mlx org wins over 4bit
assert fmt_of("someone/Qwen3-8B-W4A16") == "int4"
assert fmt_of("Qwen/Qwen3-8B-Base") is None

# publisher: same org is first-party, hardware list, else community
assert publisher_kind("Qwen/Qwen3-8B-FP8", "Qwen") == "first_party"
assert publisher_kind("nvidia/Qwen3-8B-NVFP4", "Qwen") == "hardware_vendor"
assert publisher_kind("unsloth/Qwen3-8B-GGUF", "Qwen") == "community"

# the whole-token rule collect_quants uses: a base name must not match its dotted sibling
tok = re.compile(re.escape("DeepSeek-V3") + r"(?![\w.])", re.I)
assert tok.search("QuantTrio/DeepSeek-V3-AWQ") and not tok.search("QuantTrio/DeepSeek-V3.2-Exp-AWQ")

print("selfcheck ok")
