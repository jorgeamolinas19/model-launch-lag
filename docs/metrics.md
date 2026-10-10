# Metric definitions

**Version:** `v1` · Every published table carries `snapshot_date`. GitHub issue state
mutates — an issue open at fetch may be closed tomorrow — so every number here is "as
of" a snapshot, and the snapshot date is a first-class column, not a footnote.

## 0. Release date (the input everything depends on)

`release_date` is the date the weights became **publicly** available.

**Trap:** the HF Hub's `createdAt` is the date the repo was *created*, which for many
launches is while it was still private — sometimes weeks early. Taking it at face value
would silently corrupt every latency number downstream.

**Rule:** compute three candidates and store all of them —

1. `createdAt` from the Hub API
2. the first commit date in the repo's git history
3. the first day of non-trivial download volume

Use **(2)** as `release_date` by default. Where (1) and (2) disagree by more than 2
days, flag the model `release_date_uncertain = 1`, store `release_date_method`, and
exclude it from headline latency figures unless hand-resolved against an external
announcement.

## 1. Days to support

```
days_to_support = support_event.event_date - model.release_date
```

**Signed. Negative values are preserved, never clamped to zero.** A PR merged before
public release means the framework had the weights early, which is one of the more
interesting things this project can measure. Clamping to day 0 — as the original plan
had it — would delete that signal entirely. Report:

- the signed distribution
- `n_early` = count of events with `days_to_support < 0`, per framework ("launch partner" events)
- `n_day_zero` = events landing on day 0 exactly

### Architecture vs. variant — the split that keeps this metric meaningful

Serving frameworks register **architectures**, not checkpoints. Once `Qwen3ForCausalLM`
lands, every later Qwen3 size inherits support for free and scores 0 days. Pooling the
two kinds of event makes the median collapse toward zero and measures nothing.

Every model is tagged `support_kind`:

- **`new_arch`** — first model in the cohort with this `architectures` value. This is the real latency measurement and the primary reported figure.
- **`variant`** — the architecture was already supported at this model's release. Expected value is 0; the finding here is the **exceptions**, where a variant still needed work (vision towers, new processor classes, MoE routing changes, tool-call templates).

Report `new_arch` latency as the headline. Report `variant` as "share of variants
runnable at day 0" — a coverage number, not a latency one.

### Censoring — the correctness issue in this metric

Some (model, framework) pairs are **never supported**. If the median is taken over only
supported pairs, the result is biased downward, and — perversely — a framework that
skips the hard models looks *fastest*. This is the single easiest way to publish a wrong
conclusion here.

**Rule:**

- `unsupported` pairs are **right-censored observations at `snapshot_date - release_date` days**, not missing rows.
- Use **Kaplan–Meier** to estimate median days-to-support, with the censored pairs included.
- Always publish **coverage** next to latency: `supported / applicable` per framework. Latency without coverage is not interpretable.
- State `n_censored` on every table.

> Minimum acceptable version if Kaplan–Meier is cut from v1: report the median over
> supported pairs **and** coverage **and** the censored count, side by side, labeled as
> a biased estimate. Never the median alone.

## 2. Issue load

```
issue_load = count(issues) for (model, framework)
             where created_at within [release_date, release_date + 30 days]
             and excluded = 0
```

**Observation-window rule:** a model needs `snapshot_date >= release_date + 30` to be
eligible. Models released inside the window are excluded, not partially counted.

**Normalized form:**
```
issues_per_1k_downloads = issue_load / (downloads_30d / 1000)
```

Download counts are a **moving target** — the Hub reports a rolling 30-day figure that
changes daily. Snapshot it once per collection run into `download_snapshots` with the
fetch timestamp, and use the snapshot nearest `release_date + 30` for normalization.
Never normalize against a number fetched at a different time from the one in the table.

**Stated limitation:** Hub downloads measure interest in the *weights*, not usage of any
*framework*. A model can be heavily downloaded and barely served. This normalization
reduces the popularity confound; it does not remove it.

## 3. Time to resolve

```
days_to_resolve = closed_at - created_at   # per issue, grouped by category
```

Reported as a **median**, by category and by framework.

**Censoring again:** still-open issues are right-censored at `snapshot_date -
created_at`. A framework that never closes anything has no closure dates and would
score an excellent median on the issues it did close. Use Kaplan–Meier, or report median
plus **% still open** plus `n_censored`.

**Close reason matters more than close speed.** "Closed" conflates fixed, stale-botted,
duplicate, and won't-fix. Record close reason where the API exposes it and report:

```
pct_closed_by_fix = closed with a linked commit or PR / all closed
```

This is the more honest reliability signal, and it avoids penalizing projects that keep
a transparent backlog instead of auto-closing — which keeps the finding constructive.

## 4. Top problems

```
problem_score(category) = count(category) × weight(severity)
```

Default weights: `blocker = 3`, `degraded = 2`, `minor = 1`.

**Required sensitivity check:** recompute the ranking under `5/2/1` and `3/1/0` and
publish whether the top 3 change. The weights are a judgment call, so the defensible
claim is not the score but *"this ranking is stable under reasonable reweighting"* — or,
if it isn't, that fact is the finding.

Report both pooled and **per-framework** category mixes. Pooled rankings partly just
re-describe each framework's user base (consumer-hardware hobbyists versus datacenter
operators file different bugs), so the pooled table alone would mislead.

## 5. Threats to validity — publish these, don't bury them

| Threat | Mitigation | Residual |
|---|---|---|
| **Time trend** — frameworks got much faster at onboarding models over the cohort window | Report latency against release date; restrict or stratify the window | A cohort spanning the improvement may show "framework X is fast" when it means "X's models came later". The largest confound in the study. |
| **Architecture inheritance** | `new_arch` / `variant` split (§1) | Boundary cases where an arch is "mostly" reused |
| **Framework interdependence** — Ollama←llama.cpp, SGLang←vLLM, all←transformers | Report deltas against the upstream gate | Columns are not independent; no ranking should be read as a standalone race |
| **Popularity** | Normalize per 1k downloads | Downloads ≠ framework users |
| **Triage culture** | `pct_closed_by_fix` instead of raw close speed | Labeling discipline still varies by project |
| **Who files issues** | Per-framework category mixes | Self-selection of reporters is not correctable |
| **Evidence fidelity** | Grade every support event (`exact` / `good` / `coarse`) | TensorRT-LLM dates are coarse by nature of its publishing model |
| **Severity subjectivity** | Structural signals stored alongside; self-agreement κ published | Severity remains the softest field in the dataset |

## Reproducibility contract

Every generated artifact records: `snapshot_date`, `codebook_version`,
`classifier_model` (exact tag/digest), `prompt_version`, `commit_sha` of this repo, and
the raw-snapshot directory it read. A run that cannot name all six is not publishable.
