# Deck — What makes an open-model launch go well?

Ten slides. Each slide: one claim, one piece of evidence, one source line. Figures
regenerate from `reports/`; everything is "as of" snapshot 2026-10-10/11. Items marked
*provisional* rest on the disclosed reference labels and need hand-label confirmation.

---

## 1. The question
**When a new open model ships, how long until developers can actually run it — and what breaks first?**
- 22 launches × 6 serving stacks (transformers, vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM)
- 3,559 first-30-day GitHub issues, 2,856 after cleaning
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

## 6. What breaks: the keyword ranking was wrong
- Keyword baseline vs reference labels: **36% agreement (κ 0.28)**; it over-predicted `install_build` ~5x from environment dumps
- The earlier "install/build > quantization > templates" ranking is withdrawn
- Reference sample (n=339): other 25% · missing_feature 14% · template 12% · correctness 12% · performance 12% · quantization 8% · OOM 6% · spec-decode 6% · install 5%
*Source: reports/eval_regex_vs_ref_test.txt, reports/metrics_ref.txt — provisional*

## 7. Frequency and severity point at different problems
- By volume: implementation defects (`other`) and missing features
- By severity: **quantization** — 20 of 26 are blockers; install/build 15 of 17
- Templates and performance are frequent but almost never block
- Top-3 ranking flips under reweighting → no single ranking published
*Source: reports/metrics_ref.txt §4 — provisional*

## 8. Speculative decoding is the slowest problem to fix
- KM median **110 days** to close, **60% still open** (next slowest: 81 days)
- Defects sit between the target model's code path and the speculative subsystem
- Draft models now launch alongside targets: Kimi-K3-DSpark out-downloads most full models in the cohort
*Source: reports/metrics_ref.txt §3 — provisional*

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
1. **Pair every quantized artifact with an explicit GPU-generation statement**, and ship the install base's format on day 0 — quantization is rare but a blocker 4 times in 5
2. **Smoke-test draft/target pairing before announcing a draft model** — the slowest category, with recurring, catchable shapes
3. **Give runtime crashes a home** — a `runtime_crash` label split by backend, and a crash-only first-30-day dashboard per model; the biggest bucket is currently invisible to category triage

*All three are coordination and visibility opportunities, not criticisms of any framework's engineering.*

---

### Backup: limitations in one slide
- Ollama/llama.cpp have no exact-fidelity support dates by construction; TensorRT-LLM issue volume is a visibility artifact (NVIDIA channels)
- 4 support pairs undetermined; 16 adjudicated from API-verified PRs by the assistant, pending human spot-check
- Category figures: one labeler (assistant), no self-agreement κ yet, n=339 of 2,856
- Downloads normalizer is at snapshot, not release+30; Hub downloads ≠ framework users
- Everything is as of 2026-10-10/11; issue state mutates
