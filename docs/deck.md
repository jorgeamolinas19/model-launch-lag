# Deck — What makes an open-model launch go well?

Ten slides. Each slide: one claim, one piece of evidence, one source line. Figures
regenerate from `reports/`; everything is "as of" snapshot 2026-10-10/11. Category
figures are from the hand labels (n=311); where the assistant reference labeler differs
materially both are shown.

---

## 1. The question
**When a new open model ships, how long until developers can actually run it — and what breaks first?**
- 22 launches × 6 serving stacks (transformers, vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM)
- 3,559 first-30-day GitHub issues, 2,666 after cleaning (passing mentions, duplicates, maintainer artifacts, cross-model titles removed)
- Output: a launch readiness checklist that cites its own evidence
*Source: README.md*

## 2. Day 0 is the norm for the Python serving stack — and it's integration work, not reuse
- Median days-to-support for new architectures: transformers **0**, vLLM **+1**, SGLang **+1** (class A, exact evidence)
- Removing architecture-compatible pairs does not move the medians
- 39% of recent launches had support merged *before* the weights were public (28% two years earlier)
*Source: reports/support_new_arch.txt*

## 3. The biggest apparent gaps were measurement artifacts
| method | said | truth |
|---|---|---|
| PR search | Qwen3 in transformers **+530d** | **−27d** |
| one page of release notes | DeepSeek-V3 in Ollama **+329d** | cache floor |
| allowlist file bisection | all 17 TRT-LLM archs **2026-09-08** | file's birthday |
- TensorRT-LLM moved from an apparent +52d to a verified **+17d** once dated from its 75 per-architecture files
- Rule adopted: first commit to the architecture's own implementation path
*Source: docs/evidence-rules.md*

## 4. Release dates are harder than they look
- Hub `createdAt` is repo creation, often private: 6 of 22 models needed hand resolution
- API-derived date was off by a **median of 11 days** on those — in both directions
- Kimi-K3 was *announced* 11 days before its weights were downloadable → two fields, `release_date` and `announced_at`
*Source: docs/metrics.md §0, release_dates_hand.csv*

## 5. `trust_remote_code` is how novel architectures ship
- 5 of 22 models carry their own modeling code — all novel architectures, none from Google/Qwen/Meta
- DeepSeek-V3: native transformers support **+93d**, but runnable at release via remote code
- Remote code is a mechanism, not a failure mode; the native merge is a second milestone
*Source: scripts/detect_remote_code.py*

## 6. What breaks: the keyword ranking was wrong — and labelers agree only 57%
- Naive keyword baseline: **36% agreement (κ 0.28)** with either labeler; it over-predicted `install_build` ~5x from environment dumps in issue templates → earlier ranking withdrawn
- Tuned keyword baseline vs hand labels: **57% (κ 0.50)**. Assistant labeler vs hand labels: **57% (κ 0.49)**. Same number — the label noise *is* the ceiling on this sample
- Open models on CPU (test, vs hand): Gemma-3-1B **17%** (invents categories on 45% of issues) · Qwen3-1.7B **24%** · Qwen3-4B **32%** — rising with size, all below keywords
- Models agree with the assistant labeler more than the human (Qwen3-4B: 48% vs 33%, all labelled issues)
- Hand labels (n=311): other 36% · correctness 13% · performance 11% · missing_feature 10% · quantization 9% · OOM 6% · spec-decode 6% · template 5% · install 3%
*Source: reports/eval_hand_test.txt, reports/agreement_hand_vs_ref_claude.txt, reports/metrics_hand.txt*

## 7. Frequency and severity point at different problems
- By count: runtime defects (`other`) and wrong output
- By blocker rate: **quantization 52%** (15 of 29; 82% under the second labeler) and **missing features 45%**
- Severity κ between labelers is 0.25 → blocker rates shown as ranges, never one number
- Top-3 ranking flips under reweighting → no single ranking published
*Source: reports/metrics_hand.txt §4*

## 8. Quantization and speculative decoding are the slowest problems to fix
- Quantization: KM median **122 days** to close; speculative decoding **92 days, 47% still open** (everything else 31–68 days)
- Direction holds under both labelers (89 / 110 days under the reference)
- Spec-decode defects sit between the target model's code path and the speculative subsystem; Kimi-K3-DSpark out-downloads most full models in the cohort
- "Closed" ≠ "fixed": only **15%** of closed issues have a linked PR/commit closer vs **77%** marked completed → close speed measures triage culture, so it is always shown beside open rate
*Source: reports/metrics_hand.txt §3*

## 9. Hardware: two ecosystems filing into the same trackers
| | datacenter | consumer | Apple Silicon |
|---|---|---|---|
| SGLang | 73% | 12% | — |
| vLLM | 58% | 25% | — |
| llama.cpp | 13% | 69% | 7% |
| Ollama | 15% | 48% | 32% |
- NVFP4 is the 3rd most-named quant format in first-month issues (126), after GGUF and FP8
- 10 of 15 OOM reports with a VRAM figure tried a model whose fp16 floor exceeded the card
*Source: reports/metrics_regex.txt §6 (hardware mining needs no labels)*

## 10. Three recommendations for a GPU platform team
1. **Pair every quantized artifact with an explicit GPU-generation statement**, and ship the install base's format on day 0 — quantization is rare but the most likely category to block and the slowest to close
2. **Smoke-test draft/target pairing before announcing a draft model** — the highest open rate of any category, with recurring, catchable shapes
3. **Give runtime crashes a home** — a `runtime_crash` label split by backend, and a crash-only first-30-day dashboard per model; the biggest bucket is currently invisible to category triage

*All three are coordination and visibility opportunities, not criticisms of any framework's engineering.*

---

### Backup: limitations in one slide
- Ollama/llama.cpp have no exact-fidelity support dates by construction; TensorRT-LLM issue volume is a visibility artifact (NVIDIA channels)
- 2 support pairs undetermined; 16 adjudicated from API-verified PRs by the assistant, pending human spot-check; 2 Ollama dates are Wayback-capture upper bounds
- Category figures: one human labeler, one pass, no self-agreement κ yet; a second (assistant) labeler agrees 57% / κ 0.49 on category and κ 0.25 on severity; hand severity is uniform per category in 3 categories (not interpreted); n=311 of 2,666
- The cross-model title guard trades recall for precision: a few issues whose title names a sibling generation but whose body tests the attributed model are lost
- Downloads normalizer is at snapshot, not release+30; Hub downloads ≠ framework users
- Everything is as of 2026-10-10/11; issue state mutates
