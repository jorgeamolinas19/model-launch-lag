# model-launch-lag

How fast do open-weight model launches become *runnable*, what breaks on the way, and
what should a GPU platform team fix first?

**Status: v1 scaffold.** Definitions are frozen; no data collected yet. See
[Next steps](#next-steps).

## The three questions

1. **How fast was it supported?** Days from public weight release to working support in
   each serving framework.
2. **What broke?** The recurring issue types developers hit in the first 30 days.
3. **What should a platform team fix?** The problems that are both common and severe.

## Scope (v1)

**15 models × 6 frameworks** — vLLM, SGLang, llama.cpp, Ollama, TensorRT-LLM, and
`transformers`. The cohort is defined in [cohort.toml](cohort.toml) and weighted toward
**architecture novelty**, not popularity, because that is where days-to-support carries
any signal at all.

`transformers` is included because it is the upstream gate: whether a model ships with
a merged modeling file or only `trust_remote_code` largely determines when everyone
downstream can move.

## Method, in one paragraph

Resolve each model's true public release date from the Hub (not `createdAt` — see the
trap in [docs/metrics.md](docs/metrics.md#0-release-date-the-input-everything-depends-on)).
For each framework, find the earliest merged artifact that makes the model *runnable*
under that framework's written evidence rule, hand-verify every one, and record
unsupported pairs as censored rather than missing. Collect first-30-day issues, match
them to models through an alias table, exclude bots and passing mentions, then classify
category and severity against a frozen codebook using a local open model — evaluated
against hand labels with a published self-agreement ceiling.

## The three documents that gate everything else

Read these before writing a collector or labeling an issue. They are the project.

| Document | What it settles |
|---|---|
| [docs/codebook-v1.md](docs/codebook-v1.md) | Category and severity definitions, the precedence ladder for compound issues, exclusion rules, labeling protocol |
| [docs/evidence-rules.md](docs/evidence-rules.md) | What counts as "support landed" per framework, with a fidelity grade per rule |
| [docs/metrics.md](docs/metrics.md) | Exact metric formulas, censoring treatment, and the threats-to-validity table |

### Four decisions worth knowing up front

- **Days-to-support is signed.** A PR merged before public release means early access —
  the most interesting thing here. Clamping to day 0 would delete that signal.
- **Architecture, not checkpoint.** Frameworks register architectures, so later sizes in
  a family inherit support for free and score 0 days. Models are split `new_arch` vs
  `variant`; only the former is a latency measurement.
- **Unsupported is data.** Never-supported pairs are right-censored. A median over only
  the supported pairs makes the framework that *skips* hard models look fastest.
- **Frameworks are not independent.** Ollama vendors llama.cpp; SGLang adapts vLLM; all
  depend on `transformers`. Latencies are reported as deltas against the upstream gate,
  and no column is presented as a standalone race.

## Hardware constraint and the classifier plan

This repo's dev machine is a 2018 Intel MacBook: **4-core i5-8257U, 8 GB RAM, no GPU,
~23 GB free disk.** That rules out running a serving framework locally and rules out
measuring VRAM or throughput here.

So the classifier splits in two:

| Stage | Where | What it produces |
|---|---|---|
| Dev loop (~50 `dev` issues, many prompt iterations) | Local, 3–4B quantized model on CPU | Prompt iteration, pipeline correctness. Slow but free. |
| Full batch + benchmark (all issues, 2–3 models) | **Rented GPU** (Modal / RunPod, ~1–2 GPU-hours) | Final labels, plus the real throughput and VRAM numbers the benchmark needs |

This preserves the original "Ollama for dev, vLLM for the batch" shape — vLLM just runs
on a rented hour instead of locally. Two baselines run free on CPU and make the
accuracy number interpretable: a **regex/keyword classifier** and the **frameworks' own
maintainer labels**.

## Deliverables

**v1 (this cut):** one overview table — signed days-to-support with coverage and
censoring — hand-verified support events, ~300 labeled issues, one classifier plus the
two baselines, the published label set, and the memo. A single static page, not a site.

**v2 (deferred):** per-model and per-framework pages, the 2–3 model classifier
benchmark with throughput and VRAM, Kaplan–Meier survival curves.

The memo is the product. The multi-page site is decoration, and the classifier
benchmark doubles the compute and infrastructure work for a question orthogonal to the
three above — it earns its place once the first result is real.

## Data handling

- **Raw first.** Every API response is stored gzipped under `raw/<source>/<snapshot>/`
  so the database can be rebuilt and issues reclassified without re-fetching.
- **Link, never copy.** Published outputs carry issue titles and URLs, not bodies. The
  released label set is `(issue_url, category, severity, reason)` — our labels, under
  CC-BY; the issue text stays with its authors.
- **Everything is "as of" a snapshot.** Issue state mutates, so `snapshot_date` is a
  column on every table and every published figure.
- **Pinned runs.** Each run records snapshot date, codebook version, classifier model
  digest, prompt version, and this repo's commit SHA.

## Findings posture

Written as opportunities, not criticism. Several apparent gaps are publishing artifacts
rather than engineering ones — TensorRT-LLM ships support inside container images with a
changelog as the only public artifact, which makes its dates coarse, not its work slow.
Where a framework looks slow because of an upstream dependency it does not control, the
report says so.

## Layout

```
cohort.toml            scope definition + alias seeds (hand-edited)
db/schema.sql           SQLite schema (stdlib sqlite3, no deps)
docs/                   the three gating documents
raw/                    gzipped API snapshots (gitignored)
labels/                 hand-label CSVs + published label set
```

## Next steps

1. Verify the cohort against the Hub API; resolve release dates by the §0 rule.
2. Verify every framework path glob in the evidence rules against each repo at HEAD.
3. Write the collectors (Hub, GitHub, Ollama registry) against the raw-snapshot contract.
4. Stratified-sample 300 issues, split dev/test, hand-label against the codebook.
5. Classifier prompt on `dev` only; baselines; then `test` once.
