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

_Pending: filled from `metrics_issues.py` once issue collection completes. Will report
issue load per model-framework and per 1k downloads, the match-confidence mix, and
time-to-resolve by category with open issues censored._

## Question 3 — what should a platform team fix?

_Pending: top problems (count × severity, with the reweighting check), per-framework
category mixes, the hardware capability gap, and three prioritized recommendations
with evidence links._

## Classifier

_Pending: regex baseline vs open-model classifier on the held-out test split, with the
self-agreement ceiling; the 2–3 model benchmark table from the GPU runbook._

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
