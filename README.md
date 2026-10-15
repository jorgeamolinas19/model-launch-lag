# model-launch-lag

**What makes an open-weight model launch go well?**

When a new open model ships, the gap between "weights are public" and "developers can
actually run it" ranges from below zero to never. This project measures that gap across
six serving stacks, classifies what broke along the way, and distills the result into a
launch readiness checklist that cites its own evidence.

**Status: v1 data collected; see [Status](#status).**

## The questions

1. **How fast did it become runnable?** Days from public weight release to working
   support in each framework — signed, so pre-release coordination is visible.
2. **What broke?** The recurring, severity-weighted issue types developers hit in the
   first 30 days.
3. **What hardware did people actually try?** What the ecosystem attempted to run these
   models on, and where it hit a wall.
4. **What would have prevented it?** The launch conditions that separated smooth
   launches from rocky ones.

Question 4 is the deliverable. Questions 1–3 are how it gets earned.

## Scope (v1)

**22 models × 6 frameworks** — vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM, and
`transformers` — defined in [cohort.toml](cohort.toml) and weighted toward
**architecture novelty** rather than popularity, because novelty is where
days-to-support carries signal. 16 new-architecture cases, 5 variant controls and one
draft/target pair; 16 launches from the last twelve months, 6 earlier as a time-trend
control.

`transformers` is included because it is the upstream gate: whether a model ships with
a merged modeling file or only `trust_remote_code` largely determines when everyone
downstream can move.

## Method, in one paragraph

Resolve each model's true public release date from the Hub — not `createdAt`, which is
repo-creation and often predates public availability by weeks. For each framework, find
the earliest merged artifact that makes the model *runnable* under that framework's
written evidence rule, hand-verify every one, and record never-supported pairs as
censored rather than missing. Collect first-30-day issues, match them to models through
an alias table, exclude bots and passing mentions, then classify category and severity
against a frozen codebook using a local open model — evaluated against hand labels,
with a keyword baseline, a second (assistant) labeler, and a self-agreement reference still to come (the labeler's own consistency — a reference point, not a hard ceiling). Mine reported GPUs and
VRAM from issue bodies to get the hardware picture. Then score each launch against the
readiness checklist and test whether the score predicts the observed outcome.

## The four documents that gate everything else

Read these before writing a collector or labeling an issue. They are the project.

| Document | What it settles |
|---|---|
|  [docs/codebook-v2.md](docs/codebook-v2.md) | 9 categories, severity, the precedence ladder for compound issues, exclusion rules, labeling protocol |
| [docs/evidence-rules.md](docs/evidence-rules.md) | What counts as "support landed" per framework, with a fidelity grade per rule |
| [docs/metrics.md](docs/metrics.md) | Exact formulas, censoring treatment, hardware-profile method, threats to validity |
| [docs/readiness-checklist.md](docs/readiness-checklist.md) | The deliverable, and the evidence rule each item must satisfy to ship |

### Five decisions worth knowing up front

- **Days-to-support is signed.** A merge before public release means the framework had
  the weights early. That is the most interesting measurable thing here, and clamping to
  day 0 would delete it.
- **Architecture, not checkpoint.** Frameworks register architectures, so later sizes in
  a family inherit support for free and score 0 days. Models are split `new_arch` vs
  `variant`; only the former is a latency measurement.
- **Unsupported is data.** Never-supported pairs are right-censored. A median over only
  the supported pairs would make the framework that *skips* hard models look fastest.
- **Frameworks are not independent.** Ollama vendors llama.cpp; SGLang adapts vLLM; all
  depend on `transformers`. Latencies are reported as deltas against the upstream gate,
  and no column is presented as a standalone race.
- **Estimates are never mixed with measurements.** VRAM floors are arithmetic and
  labeled as such; reported hardware is mined from issue text and always published with
  its extraction coverage.

## Compute plan

Dev machine is a 2018 Intel MacBook — 4-core i5-8257U, 8 GB RAM, no GPU. Everything
ran on it, at $0:

| Stage | Where | Produced |
|---|---|---|
| Classifier benchmark — Gemma-3-1B, Qwen3-1.7B, Qwen3-4B on the 311 hand-labelled issues | Local Ollama (Q4), CPU | Accuracy, κ, schema coverage, issues/min, peak RAM (`bench_table.py`) |
| Baselines | Local CPU | Keyword rules-v1/v2; a second (assistant) labeler |
| *Optional:* 8–9B models on GPU | Kaggle Notebooks, 2×T4 | Runbook with tested setup cells; not needed for the conclusion |

The baseline is what makes the accuracy number interpretable, and here it decided the
result: the keyword ruleset (57%, κ 0.50) beat every CPU-sized model, and the two human/
assistant labelers agree with each other at the same 57%.

## Deliverables

**v1:** the readiness checklist with evidence; a memo written as a publishable blog
post; a ~10-slide deck; one overview table (signed days-to-support with coverage and
censoring); hand-verified support events; ~300 labeled issues published as a dataset;
the classifier benchmark across 3 models with accuracy, throughput, and peak memory.

**Deferred:** a multi-page site, per-framework pages, Kaplan–Meier survival curves. The
blog post and deck carry the findings; a site is decoration.

## Data handling

- **Raw first.** Every API response stored gzipped under `raw/<source>/<snapshot>/`, so
  the database can be rebuilt and issues reclassified without re-fetching.
- **Link, never copy.** Published outputs carry issue titles and URLs, not bodies. The
  released label set is `(issue_url, category, severity, reason)` — our labels, CC-BY;
  the issue text stays with its authors.
- **Everything is "as of" a snapshot.** Issue state mutates, so `snapshot_date` is a
  column on every table and every published figure.
- **Pinned runs.** Each run records snapshot date, codebook version, classifier model
  digest, prompt version, and this repo's commit SHA.

## Findings posture

Written as enablement, not assessment.

Evidence fidelity differs by framework and this is stated wherever dates are compared:
TensorRT-LLM publishes support through container images and changelogs rather than
continuous upstream commits, which makes its dates **coarse, not slow**. Ranking it
against exact-fidelity frameworks without that caveat would be a measurement error, not
a finding. Likewise, where a framework looks slow because of an upstream dependency it
does not control, the report says so — and where a launch went badly, the checklist
names the coordination fix rather than a responsible party.

## Layout

```
cohort.toml            scope definition + alias seeds (hand-edited)
db/schema.sql           SQLite schema (stdlib sqlite3, no deps)
docs/                   the four gating documents
raw/                    gzipped API snapshots (gitignored)
labels/                 hand-label CSVs + published label set
```

## Pipeline

Every step is a script under `scripts/`, runs against `db/launch_lag.sqlite` (local,
gitignored), and stores raw API responses so later steps can be re-run without
re-fetching. Credentials come from the `gh` CLI keychain; nothing needs a token file.

```
# Question 1 - how fast was it supported
verify_cohort.py            Hub metadata, release-date candidates, hardware floors
apply_hand_dates.py         release_dates_hand.csv overrides (weights-public vs announced)
recompute_days.py           re-derive days_to_support after any date change
verify_paths.py             assert every evidence-rule path exists at each repo HEAD
collect_support.py          support events: path history (exact) / release notes (good)
bisect_arch.py              exact dates where only a declaring file exists (llama.cpp, TRT-LLM)
resolve_inherited.py        architecture already declared at release -> arch_compatible
apply_adjudication.py       negative_offsets_adjudicated.csv; never floors negatives to 0
detect_remote_code.py       trust_remote_code companion to native transformers support
report_support.py           KM medians beside coverage + censoring; evidence-class sensitivity

# Questions 2 & 3 - what broke, what to fix
collect_issues.py           first-30-day issues per (model, framework), alias-matched
clean_issues.py             codebook exclusions, auditable reason codes
baseline_regex.py           keyword precedence-ladder baseline (so LLM accuracy means something)
sample_for_labeling.py      stratified 339, dev/test split assigned at sample time
classify_llm.py             any OpenAI-compatible endpoint; prompt + model tag pinned per run
eval_classifier.py          import hand labels, accuracy/kappa/confusion, publish labels_v2.csv
metrics_issues.py           issue load, time-to-resolve (KM), top problems + reweighting, hardware
collect_close_reason.py     ClosedEvent closer per closed issue -> closed_by_fix (metrics §3)
collect_quants.py           quant-artifact lag per model x format from Hub search (metrics §7)
score_launches.py           checklist validation: launch score vs days-to-support / issue load
bench_table.py              classifier benchmark vs hand labels: accuracy, coverage, issues/min, RAM
selfcheck.py                assert-based check of the non-trivial helpers (run it after edits)
```

Optional GPU extension of the benchmark: [notebooks/gpu_batch_runbook.md](notebooks/gpu_batch_runbook.md).

## Status

- **Q1 collected.** 22 models x 6 frameworks; 7 release dates hand-resolved with
  first-party URLs; evidence classes separated; negative offsets adjudicated by historical
  implementation evidence. Findings are in `report_support.py` output and the memo.
- **Q2/Q3 collected; hand-labelled sample published.** 3,559 distinct first-30-day
  issues → 2,666 after codebook exclusions (a cross-model title guard, added after an
  external audit found a Kimi-K2 issue attributed to DeepSeek-V3.2, removed a further
  ~140). A 339-issue stratified sample (dev 136 / test 203; **311 scored** after
  post-sampling exclusions) is **hand-labelled** against codebook v2 and published as
  [labels/labels_v2.csv](labels/labels_v2.csv) (one labeler, one pass; severity in
  `correctness`/`performance`/`template_tokenizer` is uniform per category and is not
  interpreted). A disclosed assistant reference set labelled earlier from the same
  title+excerpt (`labels.source='ref_claude'`) is kept as a **second labeler**: it agrees
  with the hand labels **57% on category (κ 0.49), 50% on severity (κ 0.25)**. The naive
  keyword baseline agreed with either only ~36%, over-predicting `install_build` ~5x from
  environment dumps, so **an earlier keyword-based "top problems" ranking was
  withdrawn**. Findings: [docs/memo.md](docs/memo.md).
- **Classifier benchmarked (CPU, $0).** On the 190-issue test split against hand labels:
  keyword rules-v2 **56.8% (κ 0.50)**; Qwen3-4B 32.3% (κ 0.25); Qwen3-1.7B 24.3% (κ 0.17);
  Gemma-3-1B 17.3% (κ 0.01, usable output on only 55% of issues — it invents categories).
  Accuracy rises with size but no CPU-sized model reaches the keyword baseline, and the
  models agree with the assistant labeler more than with the human one. The two labelers
  agree 57% with each other, so ~57% is the ceiling this sample can show. Table and
  method: [docs/memo.md](docs/memo.md#classifier).
- **Close reason collected.** Only 15% of the 2,068 closed kept issues were closed by a
  linked PR/commit vs 77% marked `completed`; the proxy the memo first used was nearly
  uninformative. Reported as a lower/upper-bound interval (memo Q2, metrics §3).
- **Checklist validated and pruned.** Quant-artifact lag collected (4,728 repos; GGUF at
  median day 0 for 22/22 models, community-published). Launch score predicts
  days-to-support (ρ −0.72; −0.49 non-circular, n=16) and not issue load (ρ ≈ 0, n=22).
  Six unearned items deleted per the checklist's own rule; three earned.
- **Q1 adjudication:** 2 pairs remain undetermined (both TensorRT-LLM, allowlist-only
  evidence). Two Ollama dates are Wayback-capture upper bounds (fidelity `coarse`).
  Nemotron-3-Nano's release date resolved to its 2025-12-15 announcement (no public page
  capture exists earlier; medium confidence).
- **Codebook gaps found while labeling** (logged for v3, v2 stays frozen): no category
  for runtime crashes/hangs (36% of the hand-labelled sample lands in `other`); maintainer artifacts
  leaking past the exclusion regex; the `missing_feature`/`quantization` boundary for
  "format X unsupported for model Y". See the gaps section in
  [docs/codebook-v2.md](docs/codebook-v2.md).
- **Open human steps:** re-label 50 dev rows ≥5 days later for the self-agreement
  reference (`eval_classifier.py --import-pass2`); spot-check the 17 assistant-adjudicated
  support pairs in `support_events_hand.csv` and the 7 hand-resolved release dates in
  `release_dates_hand.csv` (2 support pairs remain undetermined).

### Running the classifier locally (no GPU)

Ollama's macOS tarball is flat: `ollama`, `llama-server` and the `lib*` runners sit side
by side. Copy all of them to `~/bin/lib/ollama/` (or run from the extracted directory),
not the `ollama` binary alone — the server starts fine without the runner and only fails
at first inference with `llama-server binary not found`. Qwen3 defaults to thinking mode,
which spends the whole token budget before emitting JSON; `classify_llm.py --no-think`
uses Ollama's native `think:false`.
