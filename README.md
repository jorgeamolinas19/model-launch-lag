# model-launch-lag

**What makes an open-weight model launch go well?**

When a new open model ships, the gap between "weights are public" and "developers can
actually run it" ranges from below zero to never. This project measures that gap across
six serving stacks, classifies what broke along the way, and distills the result into a
launch readiness checklist that cites its own evidence.

**Status: v1 scaffold.** Definitions are frozen; no data collected yet. See
[Next steps](#next-steps).

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

**18 models × 6 frameworks** — vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM, and
`transformers` — defined in [cohort.toml](cohort.toml) and weighted toward
**architecture novelty** rather than popularity, because novelty is where
days-to-support carries signal. Twelve new-architecture cases, six variant controls.

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
with two free baselines and a published self-agreement ceiling. Mine reported GPUs and
VRAM from issue bodies to get the hardware picture. Then score each launch against the
readiness checklist and test whether the score predicts the observed outcome.

## The four documents that gate everything else

Read these before writing a collector or labeling an issue. They are the project.

| Document | What it settles |
|---|---|
| [docs/codebook-v1.md](docs/codebook-v1.md) | Category and severity definitions, the precedence ladder for compound issues, exclusion rules, labeling protocol |
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

Dev machine is a 2018 Intel MacBook — 4-core i5-8257U, 8 GB RAM, no GPU. That rules out
serving a model locally, so the classifier splits across free tiers:

| Stage | Where | Produces |
|---|---|---|
| Prompt iteration (~50 `dev` issues, many passes) | Local Ollama, 3–4B quantized, CPU | Pipeline correctness. Slow, free. |
| Full batch + throughput/VRAM measurement | **Kaggle Notebooks** — 30 GPU-h/week, 12-h sessions | Final labels and the real memory/throughput figures |
| Third benchmark data point | **NIM-hosted endpoint**, free starter credits | A managed-inference comparison against self-hosted |
| Baselines | Local CPU | Regex/keyword classifier; the repos' own maintainer labels |

Total cost: **$0.** The two baselines are what make the accuracy number interpretable —
if regex scores 70% and an 8B model scores 74%, that is itself the finding.

## Deliverables

**v1:** the readiness checklist with evidence; a memo written as a publishable blog
post; a ~10-slide deck; one overview table (signed days-to-support with coverage and
censoring); hand-verified support events; ~300 labeled issues published as a dataset;
the classifier benchmark across 2–3 models with accuracy, throughput, and VRAM.

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

## Next steps

1. Verify the cohort against the Hub API; resolve release dates by the metrics §0 rule.
2. Verify every framework path glob in the evidence rules against each repo at HEAD.
3. Write the collectors (Hub, GitHub, Ollama registry) against the raw-snapshot contract.
4. Stratified-sample 300 issues, split dev/test, hand-label against the codebook.
5. Classifier prompt on `dev` only; baselines; then `test` once.
6. Score each launch against the checklist; delete every item the data did not earn.
