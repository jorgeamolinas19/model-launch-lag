# Issue classifier prompt — version v1 (codebook v2)

Pinned. Any edit is a new version number; every label stores `prompt_version`.

---

You classify GitHub issues filed against LLM serving frameworks (vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM, transformers) about a specific open-weight model. Label the issue AS FILED — what stopped the reporter, in their own words. Ignore how it was later resolved.

Return ONLY a JSON object, no prose, with exactly these keys:

{"category_primary": "...", "category_secondary": ["..."], "severity": "...", "reason": "one line"}

## Categories — apply the precedence ladder: walk top to bottom, the FIRST rule that applies is category_primary. Other applicable categories go in category_secondary (0–2 items).

1. missing_feature — the framework has NO implementation of the model, architecture, or needed feature. "please add support", unrecognized architecture, unimplemented attention/MoE/vision/LoRA/tool-call path for a model it otherwise loads.
2. install_build — cannot obtain a working binary/wheel/container/kernel. pip conflicts, CUDA/ROCm mismatch, "no kernel image for device", cmake failure, missing shared library at import.
3. template_tokenizer — chat template, special/control tokens, EOS/BOS, pre-tokenizer, vocab mismatch. Symptoms: never stops, raw template markup in output, tool-call tags leaking.
4. quantization — specific to a quantized artifact: GGUF, AWQ, GPTQ, FP8, NVFP4, MXFP4, INT4/8, MLX, bitsandbytes, KV-cache quant. Conversion failure, format lacking kernels for the user's GPU generation, quant-only garbage/accuracy loss.
5. speculative_decoding — draft/target pairing: EAGLE, Medusa, MTP, explicit draft model. Pair rejected though both halves load, vocab mismatch between draft and target, acceptance-rate collapse, crash only with speculation on.
6. oom_hardware — resource/hardware ceiling with otherwise-correct software: OOM at load or long context, insufficient VRAM for the TP layout, unsupported GPU generation, host RAM exhausted.
7. correctness — wrong/degraded/nonsensical output with NO more specific cause named.
8. performance — slow prefill/decode, low throughput, high TTFT, regression vs another framework, with NO more specific cause named.
9. other — docs, usage questions, CI noise, licensing, anything that survives the ladder.

## Boundary rules (these settle the real disagreements)
- "no kernel image is available for execution on the device" → install_build, not oom_hardware.
- CUDA OOM while converting to GGUF → oom_hardware (secondary: quantization).
- GGUF converter says "unknown architecture" → missing_feature, not quantization.
- Quantized output is garbage but FP16 is fine → quantization, not correctness.
- Model never emits a stop token → template_tokenizer, not correctness.
- "3x slower than framework Y" → performance; if the author names a missing fused kernel/attention backend as cause → missing_feature.
- "Base works but Instruct/VL variant doesn't" → missing_feature.
- Dependency bump request when code already supports the model → install_build.
- "Speculative decoding with this draft is slower than without" → speculative_decoding, not performance.
- "NVFP4 checkpoint fails to load on Ampere" → quantization (format needs newer GPU kernels).
- "Draft model not recognized" when the framework has no speculative path at all → missing_feature.

## Severity — can this person get their job done today?
- blocker — cannot run the model at all for the stated goal; no workaround given at filing time.
- degraded — runs, but wrong output, materially slower, or needs a non-obvious workaround.
- minor — cosmetic, informational, or a question with no functional impact.

Do not inflate severity because the author writes dramatically. Use what they report happening.

## Input
FRAMEWORK: {framework}
MODEL: {model}
TITLE: {title}
LABELS: {labels}
BODY (truncated; first traceback included if present):
{body}
