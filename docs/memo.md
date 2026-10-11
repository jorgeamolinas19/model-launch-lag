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
- 2 pairs remain `undetermined` (TensorRT-LLM × Olmo-3 and × granite-4.1: the
  architecture appears only in an allowlist file, with no implementation file or
  model-titled PR). 16 pairs were adjudicated by the assistant from API-verified PR
  evidence and are marked `claude-ref` pending a human spot-check; 5 negative offsets
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
stratified sample (311 scored after post-sampling exclusions) labelled against codebook
v2 by the assistant from title + excerpt only** (`ref_claude`) — a disclosed
strong-model reference, not human labels, and to be replaced by hand labels before
publication. The keyword baseline was also run over all
2,804 kept issues, but its first version agreed with the reference only **36%** (κ 0.28),
over-predicting `install_build` ~5x because issue templates embed environment dumps.
**An earlier draft of this memo ranked problems from those keyword labels; that ranking
was a keyword artifact and is withdrawn.** This is exactly what the baseline was for.
(A second rule set that strips environment dumps reaches 52% — see *Classifier*.)

### Volume

4,662 (issue, model) attributions over 22 models × 6 frameworks → **3,559 distinct
issues**, of which **2,666 survive the codebook exclusions** (1,750 passing mentions —
the same issue attributed to a sibling model via a family alias, plus issues whose title
names a *different* model than the one attributed; 127 duplicates; 116 maintainer
artifacts: RFCs, CI failures, test suites and benchmark posts). Match confidence of the
kept set: 58% repo short name, 33% family name only, 10% architecture class.

The cross-model title guard was added after an external audit found an issue titled
"Kimi K2 produces gibberish" attributed to DeepSeek-V3.2. It removed 28 of the 339
sampled rows (15 dev / 13 test), so category figures below are over the **311 that
survive**. The guard trades recall for precision: a few issues whose *title* names a
sibling generation but whose body tests the attributed model are lost too (e.g. a
"Qwen3.5 GDN regression" report that benchmarks Qwen3.8-27B weights). That cost is
accepted; a mis-attributed gold label is worse than a missing one.

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

### What the sample actually contains (reference labels, n = 311 scored)

| category | n | share | blocker | degraded | minor | KM median days to close | still open |
|---|---|---|---|---|---|---|---|
| other | 73 | 23% | 23 | 25 | 25 | 19 | 16% |
| missing_feature | 44 | 14% | 12 | 22 | 10 | 56 | 23% |
| template_tokenizer | 41 | 13% | 5 | 35 | 1 | 37 | 12% |
| correctness | 39 | 13% | 11 | 28 | 0 | 53 | 33% |
| performance | 39 | 13% | 1 | 30 | 8 | 61 | 26% |
| quantization | 22 | 7% | 18 | 4 | 0 | 89 | 14% |
| oom_hardware | 18 | 6% | 9 | 9 | 0 | 46 | 22% |
| speculative_decoding | 19 | 6% | 8 | 10 | 1 | **110** | **63%** |
| install_build | 16 | 5% | 14 | 2 | 0 | 61 | 19% |

Three things are robust here even at n = 311:

- **`other` is a bucket, not a finding.** A quarter of issues are runtime crashes,
  hangs, assertion failures and segfaults with no more specific cause named. Codebook v2
  has no category for "the process died" — `correctness` means *wrong output* — so they
  fall through. This is the single largest gap the labeling found and is logged for v3
  as `runtime_crash` ([codebook-v2.md](codebook-v2.md#gaps-found-while-labeling-339-issues-candidates-for-v3--v2-is-frozen)).
- **Speculative decoding is the slowest category by a wide margin** — a 110-day median
  and 63% still open, versus 19–89 days elsewhere. Draft/target pairing problems sit
  between two code paths and often two teams.
- **Quantization and install/build are rare but almost always blockers.** 18 of 22
  quantization issues and 14 of 16 install/build issues stop the user cold. Template and
  performance issues are frequent but almost never block (6 blockers in 80).

## Question 3 — what should a platform team fix?

### Top problems, severity-weighted — and why the ranking is not stable

| category | n | score (3/2/1) | blocker | degraded | blocker rate |
|---|---|---|---|---|---|
| other (crashes/hangs) | 73 | 144 | 23 | 25 | 32% |
| missing_feature | 44 | 90 | 12 | 22 | 27% |
| correctness | 39 | 89 | 11 | 28 | 28% |
| template_tokenizer | 41 | 86 | 5 | 35 | 12% |
| performance | 39 | 71 | 1 | 30 | 3% |
| **quantization** | 22 | 62 | **18** | 4 | **82%** |
| install_build | 16 | 46 | 14 | 2 | **88%** |
| oom_hardware | 18 | 45 | 9 | 9 | 50% |
| speculative_decoding | 19 | 45 | 8 | 10 | 42% |

**The top three change under reweighting** (3/2/1 and 5/2/1: other > missing_feature >
correctness; blocker-only: other > correctness > missing_feature), so the memo does not
publish a single ranking. The weight-dependence *is* the finding, and the two lenses
disagree: by **count** — any weighting — the first-month pain is implementation defects
and missing features; by **blocker rate** it is quantization (82%) and install/build
(88%), which are rare but stop the user cold, while performance (3%) and templates (12%)
are frequent and almost never block. A platform team optimising for "fewest users
stuck" and one optimising for "fewest issues filed" would pick different targets.

Per-framework mixes differ enough that one priority list would mislead: `transformers`
skews to missing features (37%); llama.cpp to templates and performance (21% / 16%);
Ollama to performance and templates (23% / 16%); SGLang to quantization and speculative
decoding (18% / 14%). vLLM's 98 scored issues are the most evenly spread.

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
framework's engineering. Evidence is from the reference-labelled sample and is marked
provisional until hand labels confirm it.

**1. Pair every quantized artifact with an explicit GPU-generation statement, and ship
the quant for the install base's hardware on day 0.** Quantization has the highest
blocker rate of any substantive category in the sample — 18 of 22 issues — and the
failure mode is
consistent: a format whose kernels exist only on newer silicon (`fp8e4nv not supported`
on A10; NVFP4 on Ampere; MXFP4 persistent-kernel requirement on Blackwell; `machete`
missing on RTX 5090). Hardware mined from all 2,856 issues shows the split that makes
this bite: SGLang/vLLM users are 58–73% datacenter, llama.cpp/Ollama users 48–69%
consumer. NVFP4 appears in 126 first-month issues and MXFP4 in 67. A model card line
of the form *"NVFP4: Blackwell (SM100+) only; FP8: Hopper+; GGUF Q4_K_M: any"* would
convert most of these from a traceback into a lookup. Checklist items 2.1 / 2.2.

**2. Treat speculative-decoding pairing as part of launch readiness, not a follow-up.**
Draft models now launch alongside targets (Kimi-K3-DSpark has more downloads than most
full models in the cohort), and pairing issues are the slowest to resolve of any
category — 110-day median, 63% still open — because the defect sits between the target
model's code path and the speculative subsystem. Of the 19 scored, 8 were blockers.
A pairing smoke test (draft loads against target; vocab matches; one verify step runs)
in each framework before announcing a draft would catch the recurring shapes seen here:
`decoder_layer_cls` ignored, `spec_info None` under disaggregation, aux hidden states
not emitted for a new architecture. Checklist item 2.6 (new in v2).

**3. Give runtime crashes a home, so the biggest bucket becomes actionable.** A quarter
of the sample is "the process died": CUDA illegal memory access at long context,
watchdog timeouts, segfaults on a specific backend, assertion failures in graph
capture. They are not wrong output and not install problems, so no current taxonomy
owns them, and they are invisible in any category-based triage. Two cheap moves:
(a) a `runtime_crash` label in issue templates, split by *backend* (CUDA / ROCm / Vulkan
/ Metal / SYCL / NPU), since the sample shows non-CUDA backends are heavily
over-represented in crashes relative to their user share; (b) a crash-only dashboard
per model in the first 30 days. The first makes the problem measurable; the second makes
it a launch metric.

## Classifier

**Status: baseline scored against a disclosed reference set; open-model dev run in
progress; no human labels yet.**

A stratified sample of **339 issues** (dev 136 / test 203) was labelled by the
assistant against codebook v2 from title + excerpt only, as a stand-in reference until
hand labels exist (`labels.source = 'ref_claude'`, run id recorded). Against it:

| classifier | split | category acc | κ | severity acc | κ |
|---|---|---|---|---|---|
| regex rules-v1 (naive keywords) | test (203, pre-guard) | 36.0% | 0.28 | 54.2% | 0.25 |
| regex rules-v2 (env-dump stripped, title-first) | dev (121) | 57.0% | 0.51 | 57.0% | 0.27 |
| regex rules-v2 | **test (190)** | **51.6%** | **0.44** | 50.5% | 0.19 |
| Qwen3-4B, prompt v1, CPU | dev (121) | _running_ | | | |

(n = sampled rows that survive the cleaning rules; 28 of 339 were excluded after
sampling by the cross-model title guard and widened maintainer-task filter.)

Rules-v1 was good at `missing_feature` (72% precision / 75% recall — the vocabulary is
distinctive) and poor everywhere else, because issue templates embed environment dumps
(`CUDA used to build PyTorch`, `pip`, `cmake`) that match `install_build` regardless of
the complaint. Rules-v2 strips those blocks and trusts the title first; that alone
lifted agreement from 36% to 52%. **Disclosure:** rules-v2 was written after seeing the
reference set's confusion matrix, including the test split, so its test figure is
optimistic — a fair reading is "a keyword baseline that knows the codebook's traps lands
around 50%". **That is the bar an open model has to clear**; anything above ~70% is a
real gain over keywords. The open-model classifier will touch test once, after its
prompt is frozen on dev. Throughput/VRAM for the 2–3 model benchmark follow the GPU
runbook.

Two caveats on the reference set itself: it is one labeler, so no self-agreement κ
exists yet (the protocol calls for a 50-issue re-label ≥5 days later), and it shares a
model family with none of the classifiers under test but is still a language model —
agreement with it is not accuracy against human judgment.

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
