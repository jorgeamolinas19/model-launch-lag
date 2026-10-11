# Open-model launch readiness checklist

**Status: v1 scored. Items that finished unearned were deleted (listed at the end, with why).**

This is the project's primary deliverable. It is not a leaderboard and not a critique:
it is the set of conditions that, across the cohort, separated launches that were
runnable on day 0 from launches that took weeks to settle.

## The evidence rule for this document

No item ships without a filled evidence slot. An item is **earned** when it cites at
least one of:

- a `support_event` where the condition's presence or absence measurably moved `days_to_support`, or
- ≥ 3 issues across ≥ 2 frameworks in the same `category_primary` traceable to the condition, or
- a `capability_gap` figure (metrics §6c) above the cohort median for the affected model class

Items that finish the analysis unearned are **deleted, not softened.** A checklist of
plausible-sounding advice is worth less than a short list of things the data actually
showed, and the discipline of deleting is what makes the remainder credible.

Each item records: `evidence` (links), `n` (supporting observations), `frameworks`
(where it held), and `counterexamples` (launches that violated it and were fine anyway).
Counterexamples are mandatory — an item with none has not been tested, only asserted.

---

## Phase 1 — Pre-release (model builder ↔ framework maintainers)

| # | Condition | Hypothesis | Evidence | n |
|---|---|---|---|---|
| 1.1 | Architecture implementation upstreamed before public release | Pre-release merges produce negative `days_to_support`; this is the single largest lever on day-0 readiness | **Earned.** 17 of 44 recent-band support events merged before release (39%), vs 8 of 29 historical (28%). Class-A medians are day 0 across transformers/vLLM/SGLang and the effect survives removing architecture-compatible pairs (`report_support.py` sensitivity). Counterexample: Kimi-K3 — all pre-release activity was on the hosted API; weights landed 11 days after announcement and no framework had early access. | 17 |
| 1.2 | `transformers` support is native, not `trust_remote_code` | Remote-code-only launches gate every downstream framework | **Reframed, not earned as written.** The 5 remote-code models (DeepSeek-V3, Kimi-Linear, Kimi-K3, Kimi-K3-DSpark, Nemotron-3-Nano) are all novel architectures from labs without a same-day native merge; remote code made them runnable on day 0 (`detect_remote_code.py`). Evidence shows remote code is the *mechanism by which novel architectures ship*, not a failure mode. Native support is a second milestone (DeepSeek-V3: +93d). Item rewritten: "ship remote code at launch when native support will lag; file the native PR concurrently." Counterexample needed: a remote-code model whose downstream (vLLM/SGLang) support lagged *because* of it — not yet observed. | 5 |

## Phase 2 — Day 0 (launch artifacts)

| # | Condition | Hypothesis | Evidence | n |
|---|---|---|---|---|
| 2.1 | A quantized artifact in the install base's format available within days of launch — and a one-line GPU-generation statement with it | Absence drives the `capability_gap`: users attempt fp16 on cards that cannot hold it, or a format their silicon has no kernel for | **Earned, reframed.** The artifact half is *already solved by the community*: a GGUF repo appears at a median of **day 0** for 22/22 cohort models (19 within a week), FP8 at +1d (21/22), NVFP4 at +5d (21/22) — 4,651 community quant repos vs 27 first-party and 50 hardware-vendor (`collect_quants.py`, metrics §7; Hub `createdAt`, so upper bounds). First-party quants are almost only FP8 (Qwen, Google, zai). NVFP4 lag collapsed over the window: 59–135 days for the 2025 launches (NVIDIA first), 0–5 days for 2026 launches (community first). So the remaining gap is the *statement*, not the artifact: quantization is 9% of hand-labelled issues but the most likely category to block (15/29; 18/22 under the assistant labeler) and the slowest to close (122-day KM median), and the recurring shape is a format whose kernel does not exist on the user's GPU generation. 10 of 15 OOM issues naming a VRAM figure tried a model whose fp16 floor exceeds the card (§6c). Former item 2.2 (hardware table) is folded in here. Counterexample: gpt-oss-20b shipped MXFP4 natively on day 0 and still drew 314 first-month issues — artifact timing does not set issue volume (launch-score validation below: ρ≈0). | 22 models |
| 2.5 | Tokenizer files complete and self-consistent | `template_tokenizer` is hypothesized as the highest-severity-per-issue category | **Hypothesis revised by data.** Template/tokenizer is 5% of the hand-labelled sample (13% under the assistant labeler — the two disagree most on this boundary) and rarely a blocker (0 of 15 hand, uniform severity; 5 of 41 reference); the highest blocker rates are quantization and missing_feature. Keep the item for frequency, drop the severity claim. | 15 |
| 2.6 | Draft/target speculative pairing smoke-tested in each framework before the draft is announced | Pairing defects sit between the target's code path and the speculative subsystem and have no single owner | **Earned.** `speculative_decoding` has the highest open rate of any category (47%; 92-day KM median — second only to quantization) under the hand labels and was the slowest outright under the assistant labeler (110 days, 63% open); 4 of 19 are blockers by hand, 8 by the reference; recurring shapes: draft class ignored, `spec_info None` under disaggregation, aux hidden states not emitted for a new target arch. Kimi-K3-DSpark out-downloads most full models in the cohort, so this is a mainstream launch concern. Counterexample: Qwen3.8-27B's DFlash2 drafter was served in llama.cpp at ~10x SGLang's eager speed, so pairing *can* land fast when the target is already well-supported. | 19 |

## Phase 3 — Week 1 (feedback loop)

| # | Condition | Hypothesis | Evidence | n |
|---|---|---|---|---|
| 3.1 | Give runtime crashes a label and a per-model first-30-day crash view | The largest bucket (`other`, 36% of the hand-labelled sample) is invisible to category triage because no taxonomy owns "the process died" | **Earned.** 113 of 311 hand-labelled issues are crashes/hangs/asserts with no more specific cause (86 under the assistant labeler — the two agree this is the biggest bucket). Non-CUDA backends (ROCm, Vulkan, Metal, SYCL, NPU) are over-represented in them relative to their user share (memo, Rec 3). Counterexample: none needed — this is a taxonomy fix, not a launch condition; it earns its place by size. | 113 |

---

## Scoring a launch — the validation step

Each cohort model was scored on the five data-decidable items (`score_launches.py`,
`reports/launch_scores.txt`): 1.1 pre-release merge, 1.2 day-0 `transformers`
(native or remote code), and 2.1 GGUF / FP8 / NVFP4 repo within 7 days. Spearman ρ,
n beside every figure; with n=22 and two time bands, |ρ| < 0.4 is noise.

| score vs … | ρ | n |
|---|---|---|
| median signed days-to-support (new_arch) | **−0.72** | 16 |
| same, dropping item 1.1 (which is itself a support date) | **−0.49** | 16 |
| quant items only (2.1a–c) vs days-to-support | −0.47 | 16 |
| issues per 100k downloads (all models) | +0.02 | 22 |
| issues per 100k downloads (primary band only) | −0.02 | 16 |
| raw issue count | −0.13 | 22 |

**Reading.** The checklist predicts *how fast frameworks pick a model up* — the
non-circular version still holds at ρ ≈ −0.5 — and predicts *nothing* about how many
problems users file. That is the honest scope of this document: its items are
coordination conditions for day-0 runnability, not levers on issue volume, which tracks
user-base size (Qwen3.8-27B: 436 issues, perfect quant coverage, day-0 support
everywhere). A reader who wanted "fewer issues" should look at Rec 3 (crash triage)
rather than at any item here. No confidence interval is given: at n=16 a bootstrap CI
on ρ spans roughly ±0.4 and would only restate the sentence above.

## Deleted, not softened

Per the evidence rule, these finished the analysis unearned and are removed rather than
kept as advice:

- *1.3 chat template validated per framework* — `template_tokenizer` is 5% of hand-labelled issues (13% under the assistant labeler) and never a blocker in either set; the two labelers disagree most on exactly this boundary, so no claim survives.
- *1.4 stable `architectures` string* — no cohort launch renamed its architecture class between preview and release; untestable here.
- *2.2 hardware requirements table* — folded into 2.1.
- *2.3 stated minimum framework versions* — the "largest category (25%)" figure that earned it was a keyword artifact (environment dumps in issue templates); by hand labels `install_build` is 3% (8 issues). Withdrawn with the ranking.
- *2.4 smallest family member alongside largest* — 4 of 22 cohort launches shipped a sub-10B sibling on day 0; no outcome measured here separates them.
- *3.2 known-limitations updated as issues land*, *3.3 variant gaps stated* — no evidence slot could be filled from issue data; they describe model-card hygiene, which this study did not collect.

## Framing

Written as enablement, not assessment. Several conditions are things a *framework* can
only partially control — a maintainer cannot upstream an implementation for weights
they have not seen, which makes 1.1 a statement about access and coordination rather
than about engineering speed. Where the data shows a gap, the item names the
coordination fix, not a responsible party.
