# Memo: what open-model launches look like across serving frameworks

**Status: v1 complete for snapshot 2026-10-10.** Question 1 is final; Questions 2–3 are
cut from the published hand labels, with the assistant reference as a second labeler;
the classifier benchmark ran on CPU. Open items are human-only (a self-agreement pass
and a spot-check of adjudicated dates) and are listed in the README. Every figure below
is reproducible from the repo at the commit named in the footer.

## Summary

Across 22 open-weight launches (16 from the last twelve months, 6 earlier as a
time-trend control), new architectures reach the Python serving stack — `transformers`,
vLLM, SGLang — at a **median of day 0**, and that is integration work rather than
architectural reuse. Roughly a third of recent launches had framework support merged
*before* the weights were public, up from about a quarter two years earlier. The
frameworks that at first looked slowest were the ones whose repository structure made
support hardest to *measure*, not the ones that were slow; closing that measurement gap
moved TensorRT-LLM from an apparent +52 days to a verified +24, and llama.cpp from +30 to
+2.

Three recurring problems account for most first-month friction, and three
recommendations follow for a GPU platform team. Each is framed as an opportunity: in
every case the gap is in coordination or visibility, not in any one team's engineering.

## Question 1 — how fast was it supported?

### What was measured

`days_to_support` = earliest merged artifact that makes the model *runnable* in a
framework, minus the day the weights became publicly downloadable. Signed: a negative
number means the framework had the weights early. Never-supported pairs are
right-censored, not dropped. Full definitions: [metrics.md](metrics.md); per-framework
evidence rules and their fidelity grades: [evidence-rules.md](evidence-rules.md).

### The table, by evidence class

Latency is only interpretable beside coverage, and only comparable within an evidence
class. Class A is model-specific support dated from the architecture's own
implementation path (exact). Class B adds exactly-dated *partial* support (llama.cpp's
conversion half). Class C adds release-note and PR-search dates (fidelity `good`).
`AC` counts pairs where the architecture was already declared at release — these carry
**no latency value**, because a registered architecture is not proof the checkpoint ran.

| framework | A median | A n | B median | B n | C median | C n | AC | undetermined |
|---|---|---|---|---|---|---|---|---|
| transformers | +0 | 14 | +0 | 14 | +0 | 14 | 0 | 0 |
| vLLM | +1 | 11 | +1 | 11 | +1 | 11 | 5 | 0 |
| SGLang | +1 | 12 | +1 | 12 | +1 | 13 | 3 | 0 |
| llama.cpp | n/a | 1 | +2 | 12 | +2 | 12 | 0 | 0 |
| Ollama | n/a | 0 | n/a | 0 | +8 | 13 | 0 | 0 |
| TensorRT-LLM | +24 | 12 | +24 | 12 | +24 | 12 | 2 | 1 |

*16 new-architecture models; Kaplan–Meier medians including censored pairs; n = pairs
with a dated event in that class (`reports/support_new_arch.txt`). The second
undetermined pair, TensorRT-LLM × granite-4.1, is a variant and sits outside this table.*

**The ranking is not stable across evidence classes**, so no single ranking is
published. Within class A, every measurable framework sits within ~3.5 weeks of day 0.

### Findings

**1. Day-0 support is integration work, not inheritance.** Moving from class A to the
architecture-compatible count adds 5 pairs to vLLM and 3 to SGLang and does not move
either median. The speed is real.

**2. Pre-release coordination is the norm and rising.** 25% of historical-band support
events (8 of 32) were merged before public release; 33% in the recent band (18 of 54).
Median latency was already ~0 two years ago, so the improvement shows up as
*coordination*, not speed. Examples: vLLM merged Qwen3.5 support 15 days before release;
`transformers` merged Qwen3 27 days before. (Descriptive contrast — the two bands differ
in composition.)

**3. The biggest apparent gaps were measurement artifacts.** Five successive dating
methods were tried; three produced plausible, wrong numbers:

| method | failure | example |
|---|---|---|
| PR search, earliest match | oldest *mentions* ≠ implementation PR | Qwen3 in transformers at **+530d**; truth **−27d** |
| release notes, one page cached | every older model clamped to the cache floor | DeepSeek-V3 in Ollama at exactly the floor date |
| `git blame` | last-modified ≠ first-added; wrong files | DeepSeek-V3.2 dated from a load-balancer file |
| allowlist file bisection | measured the file's birth, not support | all 17 TRT-LLM archs on **2026-09-08** |
| **first commit to the arch's own path** | — | **adopted; exact** |

TensorRT-LLM was the main casualty of the artifacts and the main beneficiary of the
fix: it has 75 per-architecture `modeling_*.py` files, and once dated from those it
sits at +24 days (Kaplan–Meier, 12 dated pairs) with `gpt-oss +3d`, `Qwen3 +4d`, and
three pre-release merges (Llama-4 −53d, GLM-5 −85d, DeepSeek-V4.1 −74d).

**4. Release dates are harder than they look.** The Hub's `createdAt` is repo creation,
often private. Of 22 models, 7 needed hand resolution (`release_dates_hand.csv`): six
against vendor announcements, plus Nemotron-3-Nano (see limitations). On the six, the
API-derived date was off by a median of 11 days, in *both* directions
(imported history predating creation; content landing after announcement). Two dates
differ by kind: Kimi-K3 was *announced* 11 days before its weights were downloadable.
`release_date` is the weights date; a framework cannot support weights that do not
exist.

**5. `trust_remote_code` is how novel architectures ship.** 5 of 22 models carry their
own modeling code — DeepSeek-V3, Kimi-Linear, Kimi-K3, Kimi-K3-DSpark, Nemotron-3-Nano —
all novel architectures from labs without a same-day native `transformers` merge.
DeepSeek-V3 reads as +93 days to native support but was runnable at release. Quoting the
native date alone misrepresents the developer experience; both are reported.

### Limitations specific to Q1

- Ollama and llama.cpp have no class-A observations by construction (no per-architecture
  file / conversion half only). Their numbers are real but not comparable to class A.
- 2 pairs remain `undetermined` (TensorRT-LLM × Olmo-3 and × granite-4.1: the
  architecture appears only in an allowlist file, with no implementation file or
  model-titled PR). 17 pairs were adjudicated by the assistant from API-verified PR
  evidence and are marked `claude-ref`. A mechanical re-check re-fetched every cited
  artifact (PR, commit, file history, archive capture) and all 17, plus the 2
  assistant-touched release dates, matched their rows (`reports/adjudication_recheck.txt`);
  the four *judgment* calls among them (two predecessor-reuse rulings, one docs-PR date,
  one multi-part merge) still await a human read; 5 negative offsets
  were adjudicated by historical evidence rather than a threshold.
- Two Ollama dates are **upper bounds** from the earliest Wayback Machine capture of the
  library page (DeepSeek-V3.2 ≤ +11d, granite-4.1 ≤ +23d), graded `coarse`.
- Nemotron-3-Nano's release date was moved from the repo's content date (2025-12-04) to
  the announcement (2025-12-15): no public capture of the model page exists before the
  announcement. Absence of a capture is not proof of private status; confidence medium.
  It is the third failure mode of the API rule — a non-gated repo whose content predates
  its public flip, so both API candidates agree and neither is the public date.

## Question 2 — what broke?

**Label provenance, in order of trust.** Volume and attribution figures below come from
the full collected set and need no labels. Category figures come from a **339-issue
stratified sample (311 scored after post-sampling exclusions) hand-labelled against
codebook v2** (`labels/labels_v2.csv`, CC BY 4.0). The hand labels were produced in one
pass by one labeler; severity in three categories (`correctness`, `performance`,
`template_tokenizer`, 91 issues) is uniformly `degraded`, which reads as a per-category
convention rather than per-issue judgment, so **blocker rates for those three are not
interpreted below**. A disclosed assistant reference set (`ref_claude`, same
title+excerpt, same codebook) was labelled before the hand labels existed and is kept
as a second labeler: it agrees with the hand labels **57% on category (κ 0.49) and 50%
on severity (κ 0.25)** over 339 issues. The keyword baseline was also run over all kept
issues; its first version agreed with either labeler only ~36% (κ 0.28), over-predicting
`install_build` ~5x because issue templates embed environment dumps. **An earlier draft
of this memo ranked problems from those keyword labels; that ranking was a keyword
artifact and is withdrawn.** The second rule set reaches 57% against the hand labels —
the same level at which the two labelers agree with each other (see *Classifier*).

### Volume

4,662 (issue, model) attributions over 22 models × 6 frameworks → **3,559 distinct
issues**, of which **2,666 survive the codebook exclusions** (1,750 passing mentions —
the same issue attributed to a sibling model via a family alias, plus issues whose title
names a *different* model than the one attributed; 127 duplicates; 116 maintainer
artifacts: RFCs, CI failures, test suites and benchmark posts). Match confidence of the
kept set: 57% repo short name, 34% family name only, 9% architecture class.

The cross-model title guard was added after an external audit found an issue titled
"Kimi K2 produces gibberish" attributed to DeepSeek-V3.2. It removed 28 of the 339
sampled rows (15 dev / 13 test), so category figures below are over the **311 that
survive**. The guard trades recall for precision: a few issues whose *title* names a
sibling generation but whose body tests the attributed model are lost too (e.g. a
"Qwen3.5 GDN regression" report that benchmarks Qwen3.8-27B weights). That cost is
accepted; a mis-attributed gold label is worse than a missing one.

| framework | first-30-day issues | share |
|---|---|---|
| vLLM | 855 | 32% |
| llama.cpp | 656 | 25% |
| Ollama | 545 | 20% |
| SGLang | 418 | 16% |
| transformers | 153 | 6% |
| TensorRT-LLM | 39 | 1% |

Issue volume tracks user-base size and reporting culture far more than launch quality:
the model with the most first-month issues (Qwen3.8-27B, 436) had day-0 support
everywhere. Per-download normalisation does not rescue this — downloads are in the
millions and the Hub figure is a rolling 30-day count at *snapshot*, not at release+30.
Raw counts are published; cross-framework comparison of them is not.

TensorRT-LLM's 39 issues are not evidence of fewer problems; its users file through
NVIDIA channels the GitHub API cannot see. The same visibility caveat that applied to its
support dates applies here.

### What the sample actually contains (hand labels, n = 311 scored)

| category | n | share | blocker | degraded | minor | KM median days to close | still open |
|---|---|---|---|---|---|---|---|
| other | 113 | 36% | 32 | 2 | 79 | 31 | 16% |
| correctness | 41 | 13% | 0† | 41 | 0 | 38 | 29% |
| performance | 35 | 11% | 0† | 35 | 0 | 64 | 37% |
| missing_feature | 31 | 10% | 14 | 1 | 16 | 34 | 13% |
| quantization | 29 | 9% | **15** | 13 | 1 | **122** | 28% |
| oom_hardware | 20 | 6% | 7 | 2 | 11 | 68 | 25% |
| speculative_decoding | 19 | 6% | 4 | 14 | 1 | 92 | **47%** |
| template_tokenizer | 15 | 5% | 0† | 15 | 0 | 38 | 13% |
| install_build | 8 | 3% | 5 | 0 | 3 | 1 | 12% |

† uniform severity across the category — a labeling convention, not evidence (see
provenance note above). Under the assistant reference these three had 11, 1 and 5
blockers respectively.

Where the two labelers disagree, the hand labels move issues *into* `other` (113 vs 86):
17 the reference called `template_tokenizer`, 13 `install_build`, 13 `missing_feature`.
The categories whose counts both labelers agree on within ±3 are `correctness`,
`performance`, `speculative_decoding` and `oom_hardware`; those are the ones to trust.

Three things are robust here even at n = 311 and across both labelers:

- **`other` is a bucket, not a finding.** A third of issues are runtime crashes,
  hangs, assertion failures and segfaults with no more specific cause named. Codebook v2
  has no category for "the process died" — `correctness` means *wrong output* — so they
  fall through. This is the single largest gap the labeling found and is logged for v3
  as `runtime_crash` ([codebook-v2.md](codebook-v2.md#gaps-found-while-labeling-339-issues-candidates-for-v3--v2-is-frozen)).
- **Quantization and speculative decoding are the slowest categories to resolve** —
  122- and 92-day KM medians against 31–68 days elsewhere, and speculative decoding has
  the highest open rate (47%). Both held under the assistant reference too (89 / 110
  days; 14% / 63% open), so the direction is not a labeler artifact even though the
  magnitudes move.
- **Quantization is rare but the most likely to block.** 15 of 29 quantization issues
  stop the user cold (18 of 22 under the reference); missing_feature (14 of 31) and
  install/build (5 of 8, n too small) follow. Template and performance issues are
  frequent and were never marked blockers by the hand labeler (convention, see †).

**"Closed" is not "fixed".** The close-reason proxy this memo first used — GitHub's
`completed` vs `not_planned` — turned out to be nearly uninformative once the actual
closer was collected for all 2,068 closed kept issues (`collect_close_reason.py`): only
**15%** were closed by a linked PR or commit, against **77%** marked `completed`. Per
framework the proxy said 55–99% "completed"; the linked-fix rate is 3–21% (llama.cpp
20%, transformers 21%, vLLM 16%, SGLang 11%, Ollama 10%, TensorRT-LLM 3%). The truth
sits between: a closer is recorded only when the PR used a closing keyword, so 15% is a
floor and 77% a ceiling. The honest reading is that **close speed measures triage
culture, not fix speed**, which is why the time-to-resolve column above is reported
beside open rate and never alone. In the hand sample the categories closed by a linked
fix least often are `correctness` (1 of 29 closed) and `quantization` (1 of 21):
precisely the ones whose issues are hardest to reproduce from a report.

## Question 3 — what should a platform team fix?

### Top problems, severity-weighted — and why the ranking is not stable

| category | n | score (3/2/1) | blocker | degraded | blocker rate |
|---|---|---|---|---|---|
| other (crashes/hangs) | 113 | 179 | 32 | 2 | 28% |
| correctness | 41 | 82 | 0† | 41 | — |
| **quantization** | 29 | 72 | **15** | 13 | **52%** |
| performance | 35 | 70 | 0† | 35 | — |
| missing_feature | 31 | 60 | 14 | 1 | 45% |
| speculative_decoding | 19 | 41 | 4 | 14 | 21% |
| oom_hardware | 20 | 36 | 7 | 2 | 35% |
| template_tokenizer | 15 | 30 | 0† | 15 | — |
| install_build | 8 | 18 | 5 | 0 | 63% (n=8) |

**The top three change under reweighting** (3/2/1: other > correctness > quantization;
5/2/1 and blocker-only: other > quantization > missing_feature), so the memo does not
publish a single ranking. The weight-dependence *is* the finding, and the two lenses
disagree: by **count** the first-month pain is runtime defects and wrong output; by
**blocker rate** it is quantization (52% here, 82% under the reference labeler) and
missing features (45%), which are rarer but stop the user cold. A platform team
optimising for "fewest users stuck" and one optimising for "fewest issues filed" would
pick different targets. Quantization is the one category that tops *both* the
blocker-rate and the time-to-resolve lists under both labelers.

Per-framework mixes differ enough that one priority list would mislead: `transformers`
skews to missing features (21%); llama.cpp to performance (16%); Ollama to correctness
and performance (22% / 14%); SGLang and vLLM to quantization (14% / 12%). Every
framework's largest bucket is `other`.

### Hardware

Hardware was extractable from 63% of the 2,666 kept issues (1,684) — a lower bound on what people ran.
Where a GPU is named: 414 datacenter, 377 consumer, 109 workstation, 64 Apple Silicon.
The split by framework is stark and explains much of the category mix above:

| framework | datacenter | consumer | Apple Silicon |
|---|---|---|---|
| SGLang | 71% | 13% | — |
| vLLM | 58% | 26% | — |
| TensorRT-LLM | 69% | 19% | — |
| transformers | 46% | 41% | 8% |
| Ollama | 15% | 49% | 33% |
| llama.cpp | 13% | 69% | 6% |

Quant formats named in issues: GGUF 423, FP8 233, **NVFP4 111**, MXFP4 62, AWQ 49, MLX 31.
NVFP4 is the third most-discussed format in first-month issues — a 2026 phenomenon with
no analogue in the historical band.

**Capability gap (§6c):** of 130 keyword-labelled OOM issues, 26 state their card's VRAM; **16 of those 26 (62%)
attempted a model whose fp16 floor exceeds the card they named.** Small n, but the
direction is unambiguous: people try to run what they want on what they have, and the
answer is a quantized artifact on day 0, not a better error message.

### Three recommendations for a GPU platform team

Each is an opportunity in coordination or visibility; none is a criticism of a
framework's engineering. Evidence is from the hand-labelled sample, with the assistant
reference as a second labeler; where the two disagree on magnitude both figures are
given.

**1. Pair every quantized artifact with an explicit GPU-generation statement, and ship
the quant for the install base's hardware on day 0.** Quantization has the highest
blocker rate of any category with n ≥ 10 — 15 of 29 issues (18 of 22 under the
reference labeler) — and the slowest resolution (122-day KM median), and the failure mode is
consistent: a format whose kernels exist only on newer silicon (`fp8e4nv not supported`
on A10; NVFP4 on Ampere; MXFP4 persistent-kernel requirement on Blackwell; `machete`
missing on RTX 5090). Hardware mined from all 2,666 kept issues shows the split that makes
this bite: SGLang/vLLM users are 58–71% datacenter, llama.cpp/Ollama users 49–69%
consumer. NVFP4 appears in 111 first-month issues and MXFP4 in 62. A model card line
of the form *"NVFP4: Blackwell (SM100+) only; FP8: Hopper+; GGUF Q4_K_M: any"* would
convert most of these from a traceback into a lookup. Checklist item 2.1.

The *artifact* half of this is already handled — by the community, not the vendor.
Across the 22 models, 4,728 quant repos on the Hub (`collect_quants.py`, metrics §7):
a GGUF appears at a median of **day 0** (22/22 models; 19 within a week), FP8 at +1
day (21/22), NVFP4 at +5 days (21/22). 4,651 of those repos are community-published,
27 first-party, 50 from hardware vendors; first-party quants are almost exclusively
FP8. The one format whose timing changed over the window is NVFP4: 59–135 days for the
2025 launches, with NVIDIA's own repos first, versus 0–5 days for 2026 launches, with
the community first. Dates are Hub `createdAt` (repo creation, often before the public
flip — the same limitation as §0), so lags are upper bounds and the handful of negative
values are not pre-release leaks. Read beside the framework support dates: where a
day-0 NVFP4 repo exists but the user's card has no kernel for it, the gap is neither
the artifact nor the framework — it is the missing sentence on the model card.

**2. Treat speculative-decoding pairing as part of launch readiness, not a follow-up.**
Draft models now launch alongside targets (Kimi-K3-DSpark has more downloads than most
full models in the cohort), and pairing issues are the slowest to resolve of any
category by open rate — 92-day median, 47% still open (110 days / 63% under the
reference labeler) — because the defect sits between the target model's code path and
the speculative subsystem. Of the 19 scored, 4 were blockers by the hand labels (8 by
the reference); the case rests on resolution time, not severity.
A pairing smoke test (draft loads against target; vocab matches; one verify step runs)
in each framework before announcing a draft would catch the recurring shapes seen here:
`decoder_layer_cls` ignored, `spec_info None` under disaggregation, aux hidden states
not emitted for a new architecture. Checklist item 2.6 (new in v2).

**3. Give runtime crashes a home, so the biggest bucket becomes actionable.** A third
of the sample (36%) is "the process died": CUDA illegal memory access at long context,
watchdog timeouts, segfaults on a specific backend, assertion failures in graph
capture. They are not wrong output and not install problems, so no current taxonomy
owns them, and they are invisible in any category-based triage. Two cheap moves:
(a) a `runtime_crash` label in issue templates, split by *backend* (CUDA / ROCm / Vulkan
/ Metal / SYCL / NPU), since the sample shows non-CUDA backends are heavily
over-represented in crashes relative to their user share; (b) a crash-only dashboard
per model in the first 30 days. The first makes the problem measurable; the second makes
it a launch metric.

### Does the checklist predict anything?

Each model was scored on the five items the data can decide — pre-release merge, day-0
`transformers` (native or remote code), and GGUF / FP8 / NVFP4 repo within 7 days
(`score_launches.py`). The score predicts **median days-to-support** (Spearman ρ −0.72,
n=16 new-arch models; −0.49 once the pre-release-merge item, which is itself a support
date, is dropped) and predicts **nothing about issue load** (ρ +0.02 against issues per
100k downloads, n=22; −0.02 within the 2026 band alone). The checklist is therefore a
list of day-0 runnability conditions, not a lever on first-month issue volume — which
tracks user-base size (Qwen3.8-27B: perfect quant coverage, day-0 support everywhere,
436 issues). Items that ended the analysis unearned were deleted from the checklist, as
its own evidence rule requires; the deletions and reasons are listed in the document.

## Classifier

**Status: hand labels in; keyword baseline, the assistant reference and three open
models benchmarked against them on CPU (`scripts/bench_table.py`).**

A stratified sample of **339 issues** (dev 136 / test 203) was hand-labelled against
codebook v2 (`labels.source = 'hand'`). Before the hand labels existed the assistant
labelled the same rows from title + excerpt as a disclosed reference
(`ref_claude`); it is now reported as a second labeler, not a gold set.

**Benchmark — test split (190 scored issues) vs hand labels**

| classifier | labelled | category acc | κ | acc* | severity acc | κ | issues/min | peak RAM |
|---|---|---|---|---|---|---|---|---|
| keyword rules-v2 (env-dump stripped, title-first) | 190/190 | **56.8%** | **0.50** | 56.8% | 53.2% | 0.29 | instant | 0 |
| assistant reference (`ref_claude`, the second labeler) | 190/190 | 56.8% | 0.49 | 56.8% | 45.3% | 0.18 | — | — |
| Qwen3-4B (Ollama Q4, `think=false`) | 189/190 | 32.3% | 0.25 | 32.1% | 42.3% | 0.11 | 1.5 | 3.2 GB |
| Qwen3-1.7B (Ollama Q4, `think=false`) | 185/190 | 24.3% | 0.17 | 23.7% | 43.2% | 0.09 | 2.0 | 2.3 GB |
| Gemma-3-1B (Ollama Q4) | 104/190 | 17.3% | 0.01 | 9.5% | 29.8% | 0.05 | 4.0 | 1.2 GB |

*acc\** counts a parse failure as wrong. All model rows: prompt v1 (frozen on dev before
test was touched), codebook v2, 2018 Intel MacBook (4-core i5, 8 GB, CPU only), $0.
Throughput is the median gap between consecutive labels, because overnight sleep stalled
two runs and wall-clock rates would mostly measure the laptop's power settings. Dev
split (121) agrees within a few points: keyword 55.4% / κ 0.48, Qwen3-4B 34.7% / 0.28,
Qwen3-1.7B 26.7% / 0.18, Gemma-3-1B 14.7% / 0.02. The naive keyword rules-v1 scored
36.0% / κ 0.28 against the assistant reference on the pre-guard test set.

What the benchmark shows:

- **Accuracy rises with size, and no CPU-sized model reaches the keyword baseline.**
  κ goes 0.01 → 0.17 → 0.25 from 1B to 4B. The 4B model is the only one usefully above
  chance, and it is still well below a keyword ruleset that knows the codebook's traps.
- **Below ~2B parameters the schema itself breaks.** Gemma-3-1B produced a usable label
  for only 55% of issues; the rest invent categories (`bug`, `installer`) or put a
  severity in the category slot. Qwen3-1.7B follows the schema (97%) but picks badly.
  Format compliance and judgment fail at different sizes.
- **Models agree with the other model more than with the human.** Qwen3-4B matches the
  assistant reference 48% (κ 0.41, n=322) but the hand labels only 33%; Qwen3-1.7B
  matches the reference 40% and the hand labels 25%. Language models reading the same
  codebook converge on each other, which is the clearest illustration of the ceiling
  point below.
- **The GPU leg (Kaggle, 2×T4, 8–9B models) is documented but optional.** The runbook
  has tested setup cells; at this ceiling a larger model can at best tie the keyword
  baseline, so it would refine the curve rather than change the conclusion.

(n = sampled rows that survive the cleaning rules; 28 of 339 were excluded after
sampling by the cross-model title guard and widened maintainer-task filter.)

Rules-v1 was good at `missing_feature` (72% precision / 75% recall — the vocabulary is
distinctive) and poor everywhere else, because issue templates embed environment dumps
(`CUDA used to build PyTorch`, `pip`, `cmake`) that match `install_build` regardless of
the complaint. Rules-v2 strips those blocks and trusts the title first; that alone
lifted agreement from 36% to 57%. **Disclosure:** rules-v2 was written after seeing the
*reference* set's confusion matrix, not the hand labels, but the two label sets overlap
57%, so treat the test figure as mildly optimistic.

**The number that frames everything else: the two labelers agree 57% (κ 0.49) with each
other.** The keyword baseline against the hand labels (57%) and the assistant reference
against the hand labels (57%) are the same figure. On this sample, with this codebook, a
classifier cannot be shown to beat ~57% because the labels themselves disagree at that
rate — mostly over the boundary of `other` (hand: 113, reference: 86). Severity is
worse: κ 0.25 between labelers, and the hand set applies one severity per category in
three categories. Two consequences: (a) the open-model benchmark is a measure of
*which labeler the model resembles*, not of accuracy, until the codebook's `other`
boundary is tightened (v3: `runtime_crash`); (b) severity-weighted findings are
reported as ranges across both labelers, never as one number. A 50-issue second hand
pass (≥5 days later) would show whether the single labeler is at least self-consistent.

## Method notes a reader should know

- Everything is "as of" snapshot 2026-10-10. Issue state mutates.
- Category metrics are computed over the published hand labels (`labels/labels_v2.csv`,
  311 rows, CC BY 4.0); the assistant reference (`ref_claude`) is reported alongside as a
  second labeler. Model labels are pinned to a prompt version and model tag per run.
- `closed_by_fix` comes from each issue's ClosedEvent closer (GraphQL), which GitHub
  records only for keyword-linked PRs/commits: a lower bound on fixes.
- Negative support offsets were manually adjudicated using historical implementation
  evidence. Pre-existing architectures were distinguished from model-specific
  integrations, and architecture presence alone was not treated as proof of executable
  checkpoint compatibility.

---
*Repo: https://github.com/jorgeamolinas19/model-launch-lag · Snapshot 2026-10-10 ·
Codebook v2 · Figures regenerate from `scripts/report_support.py` and
`scripts/metrics_issues.py`.*
