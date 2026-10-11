# Memo: what open-model launches look like across serving frameworks

**Status: draft. Question 1 findings are final for this snapshot (2026-10-10); Questions
2–3 sections are filled from the regex baseline until hand labels land and will be
re-cut from LLM labels.** Every figure below is reproducible from the repo at the commit
named in the footer.

## Summary

Across 22 open-weight launches (16 from the last twelve months, 6 earlier as a
time-trend control), new architectures reach the Python serving stack — `transformers`,
vLLM, SGLang — at a **median of day 0**, and that is integration work rather than
architectural reuse. Roughly a third of recent launches had framework support merged
*before* the weights were public, up from about a quarter two years earlier. The
frameworks that at first looked slowest were the ones whose repository structure made
support hardest to *measure*, not the ones that were slow; closing that measurement gap
moved TensorRT-LLM from an apparent +52 days to a verified +17, and llama.cpp from +30 to
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
| transformers | +0 | 14 | +0 | 14 | +0 | 14 | 0 | 2 |
| vLLM | +0 | 8 | +0 | 8 | +0 | 8 | 5 | 3 |
| SGLang | +1 | 11 | +1 | 11 | +1 | 11 | 2 | 3 |
| llama.cpp | n/a | 1 | +2 | 12 | +2 | 12 | 0 | 0 |
| Ollama | n/a | 0 | n/a | 0 | +9 | 12 | 0 | 2 |
| TensorRT-LLM | +17 | 12 | +17 | 12 | +17 | 12 | 1 | 3 |

*New-architecture models only; Kaplan–Meier medians including censored pairs.*

**The ranking is not stable across evidence classes**, so no single ranking is
published. Within class A, every measurable framework sits within ~17 days of day 0.

### Findings

**1. Day-0 support is integration work, not inheritance.** Moving from class A to the
architecture-compatible count adds 5 pairs to vLLM and 2 to SGLang and does not move
either median. The speed is real.

**2. Pre-release coordination is the norm and rising.** 28% of historical-band support
events (8 of 29) were merged before public release; 39% in the recent band (17 of 44).
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
sits at +17 days with `gpt-oss +3d`, `Qwen3 +4d`.

**4. Release dates are harder than they look.** The Hub's `createdAt` is repo creation,
often private. Of 22 models, 6 needed hand resolution against vendor announcements; the
API-derived date was off by a median of 11 days on those, in *both* directions
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
- 14 pairs remain `undetermined` and are excluded from every figure; 5 negative offsets
  were adjudicated by historical evidence rather than a threshold.
- One cohort release date (Nemotron-3-Nano: repo content 2025-12-04, announcement
  2025-12-15) is unresolved as to whether the weights were public before announcement.

## Question 2 — what broke?

**Labels in this section are from the keyword baseline** (`regex_baseline`, codebook v2)
and will be re-cut from hand-validated LLM labels. The *shape* of the findings is stable
under that caveat; the exact percentages are not.

### Volume

4,662 (issue, model) attributions over 22 models × 6 frameworks → **3,559 distinct
issues**, of which **2,856 survive the codebook exclusions** (1,631 passing mentions —
mostly the same issue attributed to a sibling model via a family alias — 127 duplicates,
45 maintainer tracking issues). Match confidence of the kept set: 58% repo short name,
32% family name only, 10% architecture class.

| framework | first-30-day issues | share |
|---|---|---|
| vLLM | 944 | 33% |
| llama.cpp | 688 | 24% |
| Ollama | 557 | 20% |
| SGLang | 462 | 16% |
| transformers | 159 | 6% |
| TensorRT-LLM | 46 | 2% |

Issue volume tracks user-base size and reporting culture far more than launch quality:
the model with the most first-month issues (Qwen3.8-27B, 487) had day-0 support
everywhere. Per-download normalisation does not rescue this — downloads are in the
millions and the Hub figure is a rolling 30-day count at *snapshot*, not at release+30.
Raw counts are published; cross-framework comparison of them is not.

TensorRT-LLM's 46 issues are not evidence of fewer problems; its users file through
NVIDIA channels the GitHub API cannot see. The same visibility caveat that applied to its
support dates applies here.

### Time to resolve (open issues censored at snapshot)

| category | n | KM median days | still open | closed as not-planned |
|---|---|---|---|---|
| performance | 54 | 40 | 24% | 17% |
| template_tokenizer | 415 | 45 | 22% | 18% |
| quantization | 685 | 46 | 31% | 15% |
| oom_hardware | 88 | 49 | 22% | 16% |
| install_build | 721 | 57 | 19% | 25% |
| missing_feature | 296 | 61 | 22% | 16% |
| correctness | 34 | 61 | 38% | 6% |
| speculative_decoding | 57 | 65 | 42% | 9% |

Two things stand out. **Speculative-decoding issues are the slowest to resolve and the
most likely to still be open** (42%) — consistent with pairing problems having no single
owner. And **a quarter of install/build issues close as not-planned**, the highest
dismissal rate of any category: many are environment-specific and never reproduce.

## Question 3 — what should a platform team fix?

### Top problems, severity-weighted

| category | n | score (3/2/1) | blocker | degraded |
|---|---|---|---|---|
| **install_build** | 721 | 1,844 | 414 | 295 |
| **quantization** | 685 | 1,643 | 280 | 398 |
| **template_tokenizer** | 415 | 963 | 149 | 250 |
| missing_feature | 296 | 670 | 91 | 192 |
| oom_hardware | 88 | 204 | 33 | 50 |
| speculative_decoding | 57 | 138 | 25 | 31 |

**The top three are stable under all three weightings tested** (3/2/1, 5/2/1, 3/1/0), so
the ranking is a property of the data rather than of the weights.

The pooled ranking partly re-describes who files issues where, and the per-framework
mixes show it: vLLM is 46% install/build (CUDA/wheel/driver), llama.cpp is 40%
quantization and 27% template/tokenizer (GGUF conversion, chat templates), SGLang leads
on quantization (26%) and missing features, Ollama is 45% "other" (usage questions).
A platform team's priorities differ by which stack its users are on.

### Hardware

Hardware was extractable from 63% of kept issues — a lower bound on what people ran.
Where a GPU is named: 449 datacenter, 395 consumer, 119 workstation, 66 Apple Silicon.
The split by framework is stark and explains much of the category mix above:

| framework | datacenter | consumer | Apple Silicon |
|---|---|---|---|
| SGLang | 73% | 12% | — |
| vLLM | 58% | 25% | — |
| TensorRT-LLM | 57% | 29% | — |
| transformers | 46% | 41% | 8% |
| Ollama | 15% | 48% | 32% |
| llama.cpp | 13% | 69% | 7% |

Quant formats named in issues: GGUF 443, FP8 264, **NVFP4 126**, MXFP4 67, AWQ 51, MLX 31.
NVFP4 is the third most-discussed format in first-month issues — a 2026 phenomenon with
no analogue in the historical band.

**Capability gap (§6c):** of 88 OOM issues, 15 state their card's VRAM; **10 of those 15
attempted a model whose fp16 floor exceeds the card they named.** Small n, but the
direction is unambiguous: people try to run what they want on what they have, and the
answer is a quantized artifact on day 0, not a better error message.

### Three recommendations for a GPU platform team

Each is an opportunity in coordination or visibility; none is a criticism of a
framework's engineering.

**1. Ship the install path with the model, not after it.** Install/build is the largest
and most-dismissed category (721 issues, 25% closed not-planned). Most are version
skew: a model that needs framework ≥ X on CUDA ≥ Y, learned by failing. A one-table
"known-good matrix" in the model card at launch — framework version, CUDA, GPU
generation, quant format — would convert the single biggest issue category into a
lookup. Evidence: vLLM 46% install/build; `pip`/wheel/`no kernel image` dominate.

**2. Publish a quantized artifact at launch for the formats the install base can run.**
Quantization is #2 by volume and #1 by *degraded* outcomes (398). The capability-gap
figure shows demand for sub-fp16 memory on day 0; NVFP4 appearing in 126 first-month
issues shows the format is already in users' hands before the kernels are everywhere.
Pairing a day-0 NVFP4/FP8 artifact with an explicit GPU-generation requirement would
address both the OOM demand and the "format loads on Hopper but not Ampere" failure
mode. Evidence: `quant_artifacts` lag (§7) once collected; `issue_hardware.quant_mentioned`.

**3. Validate chat templates against each target framework before release.** Template
and tokenizer issues are #3 (415) with a 45-day median resolution and symptoms users
cannot self-diagnose (model never stops, tool-call tags leak). A template test harness
run against vLLM, SGLang and llama.cpp's Jinja renderers before publishing would catch
most of these pre-release. llama.cpp's 27% template share shows where the renderer
divergence bites hardest.

## Classifier

**Status: baseline only; LLM dev run in progress; no hand labels yet.**

A stratified sample of **339 issues** (dev 136 / test 203) is drawn and seeded in the
database; the worksheet awaits hand labels. Until then no accuracy figure exists, and
none is quoted. The regex baseline's distribution is above; the open-model classifier
(Qwen3-4B via Ollama, prompt v1, `think=false`) runs locally at ~23 s/issue on CPU and
will be scored against the hand labels on the **test** split only after the prompt is
frozen on **dev**. The full batch and the throughput/VRAM benchmark follow the GPU
runbook.

## Method notes a reader should know

- Everything is "as of" snapshot 2026-10-10. Issue state mutates.
- Metrics are computed over published hand labels (`labels/labels_v2.csv`, CC BY 4.0) and
  model labels pinned to a prompt version and model tag per run.
- Negative support offsets were manually adjudicated using historical implementation
  evidence. Pre-existing architectures were distinguished from model-specific
  integrations, and architecture presence alone was not treated as proof of executable
  checkpoint compatibility.

---
*Repo: https://github.com/jorgeamolinas19/model-launch-lag · Snapshot 2026-10-10 ·
Codebook v2 · Figures regenerate from `scripts/report_support.py` and
`scripts/metrics_issues.py`.*
