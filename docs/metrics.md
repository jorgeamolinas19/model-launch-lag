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

**Rule (revised in v2 after running it on 22 models):** use

```
release_date = max(createdAt, first_weight_commit)
```

The first naive version of this rule preferred the first commit outright. Running it
surfaced two failure modes that make that wrong:

- **Imported history.** `allenai/Olmo-3-7B-Think` has a first commit *18 days before*
  its `createdAt` — history pushed from an existing repo. A commit cannot predate the
  repo's public existence, so `createdAt` governs here.
- **Private-then-published.** `google/gemma-4-31B-it` (22 days), `moonshotai/Kimi-K3`
  (44 days) and `mistralai/Mistral-Small-3.1` (6 days) were created well before their
  first content commit. Here the commit governs.

Taking the **later** of the two is defensible in both directions: a model cannot be
public before its repo exists, and cannot be runnable before its weights land.

Where the candidates disagree by more than 2 days, flag `release_date_uncertain = 1`,
store `release_date_method`, and **hand-resolve against an external announcement before
publishing any latency figure for that model.** On the v2 cohort this flags 4 of 22
(18%) — a rate high enough that skipping the hand resolution would visibly corrupt the
headline.

### Measured error of the API rule (v2 cohort)

All four flagged models were hand-resolved against vendor announcements
(`release_dates_hand.csv`). Error of the API-derived date versus the hand-resolved one:

| Model | API-derived | Hand-resolved | Error |
|---|---|---|---|
| `allenai/Olmo-3-7B-Think` | 2025-10-31 | 2025-11-20 | **+20 d** |
| `google/gemma-4-31B-it` | 2026-04-02 | 2026-04-02 | 0 d |
| `moonshotai/Kimi-K3` | 2026-07-27 | 2026-07-16 | **−11 d** |
| `Qwen/Qwen3.8-27B` | 2026-08-05 | 2026-08-14 | **+9 d** |

**Median absolute error 11 days, max 20 days.** Days-to-support for a well-coordinated
launch is frequently in the single digits, so an 11-day error in the *denominator date*
is not a rounding problem — it can invert the sign of `days_to_support` and turn a
day-0 launch into a two-week lag or vice versa. The flagging mechanism caught every
such case, and the unflagged 18 models had agreeing candidates.

Two asymmetries worth noting, because they rule out a simpler rule:

- `Kimi-K3`'s first commit lands **11 days after** its announcement, so no "earliest
  signal" heuristic would find it. The repo gained content after the model was public.
- `Olmo-3`'s imported history predates its announcement by 20 days, in the opposite
  direction.

No single API-derived rule can be correct for both. **Hand resolution is a required
step of this method, not a cleanup pass** — which is why `release_date_method` is a
stored column and why a missing `source_url` blocks publication.

**Still not obtainable from the API:** the date a repo flipped from private to public.
No endpoint exposes it. For 22 models, hand-resolution against vendor announcements is
the honest fix, and it is why `release_date_method` includes `hand_resolved`.

### Weights-public vs announced: two dates, not one

An unstated assumption in the first version of this rule was that "release" is a single
event. It is not, and hand resolution surfaced a case where the two differ materially.

| Field | Definition | Role |
|---|---|---|
| `release_date` | The day the **weights became publicly downloadable** | The denominator for `days_to_support` |
| `announced_at` | The day the vendor **publicly announced** the model | Reported separately |

**`release_date` is the weights date, and that is not a stylistic choice.** A serving
framework cannot support a checkpoint that does not exist yet, so measuring latency from
an announcement would charge frameworks for a wait they had no way to act on.

Measured on this cohort: **Kimi-K3 was announced 2026-07-16 but its weights landed
2026-07-27** — the announcement covered *hosted* availability, 11 days before anything
was downloadable. Using the announcement date would have added 11 days of phantom lag
to every framework's Kimi-K3 row.

The gap is itself worth reporting — hosted-before-weights is a real launch pattern and
bears on checklist item 2.1 — but it belongs in the writeup, not inside the latency
metric.

**Unreconciled, flagged before publication:** `google/gemma-4-31B-it` has a vendor
release log entry of 2026-03-31 against an announcement of 2026-04-02, while the HF
repo's first content commit is 2026-04-02. The repo date is used; the 03-31 entry may
refer to another distribution channel and is recorded in `release_note` rather than
silently dropped.

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

**Attribution rule.** Issues are found by searching each framework repo for the model's
aliases within its window, highest-confidence alias first: the HF architecture class
(`Qwen3_5ForConditionalGeneration`, which appears verbatim in "architecture not
supported" errors), then the repo short name, then the family name. `match_kind`
records which alias hit, and is published with every count.

A family alias hits every sibling released in the same window — `qwen3.5` matches
issues about both Qwen3.5-27B and Qwen3.5-397B — so one GitHub issue can be attributed
to several cohort models. The table keys on `(issue, model)`, the strongest attribution
is kept, and the rest are excluded as `passing_mention`. (The first schema keyed on the
issue alone and silently kept whichever model was collected last. Caught when 988 rows
had 988 distinct ids, which is impossible given overlapping family aliases.)

**Loose-only matches are weak evidence.** An issue matched only by family name, with
the model absent from the title and named once in the body, is excluded as a passing
mention. The share of kept issues matched by `arch_class` vs `slug` vs `loose` is
reported so a reader can judge the attribution confidence of every figure built on
them.

**Normalized form:**
```
issues_per_100k_downloads = issue_load / (downloads_30d / 100000)
```
(Originally specified per 1,000; cohort downloads are in the millions, so every cell
rounded to 0.0. Scale change only — the ratio is unchanged.)

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

## 6. Hardware profile and the capability gap

Two different things, kept strictly separate because conflating an estimate with a
measurement is how a hardware claim becomes indefensible.

### 6a. Estimated floor (arithmetic, not measured)

```
vram_floor_fp16_gb = params_b * 2 * 1.20   # weights + ~20% runtime/activation overhead
vram_floor_int4_gb = params_b * 0.55 * 1.25
```

KV cache is excluded and reported separately, since it scales with context and batch
and would make a single number meaningless. **Label these as estimates everywhere.**
They answer "roughly what class of card does this need", nothing more.

### 6b. Observed hardware (mined from issue reports)

What people *actually tried*, extracted by regex from issue bodies — GPU names, and
reported VRAM from CUDA OOM text such as `GPU 0 has a total capacity of 23.64 GiB`.
Normalized into `gpu_class`: consumer / workstation / datacenter / apple_silicon /
cpu_only.

**This is a lower bound.** Many reporters never name their hardware, so absence of a
GPU name is not absence of a GPU. Report coverage (`% of issues with hardware
extracted`) next to every hardware figure, and never compute a share over the extracted
subset without stating what fraction of issues that subset is.

### 6c. The capability gap — the platform-relevant metric

```
capability_gap = share of first-30-day oom_hardware issues where
                 vram_reported_gb < vram_floor_fp16_gb for that model
```

Read as: **people attempting a model on hardware that could never have run it in that
precision.** A high gap is not user error — it is a signal about what the ecosystem
*wants to run* versus what it can, and it points at specific fixes (shipping a
quantized artifact at launch, publishing a hardware-requirements table on day 0,
clearer preflight errors).

Report alongside it:

- `gpu_class` mix per model and per framework — this is where framework user bases
  visibly diverge, and it is the honest explanation for much of the category-mix
  variation in §4
- the quantization mix in OOM reports — if most gap issues name a quant that the
  framework did not yet support at launch, the finding is a *launch-artifact timing*
  problem, not a hardware problem

**Limitation to publish:** hardware is self-reported by a self-selected subset of users
who were motivated enough to file an issue. These figures describe the population of
*reporters*, not the population of *users*, and no reweighting fixes that.

## 7. Quantization-artifact lag (v2)

A model is not usable by most of the ecosystem when the `bf16` weights land — it is
usable when a quant that fits available hardware lands. Quant repos are therefore not
cohort members (they are derivative), but their **timing** is a first-class metric.

```
quant_lag(model, fmt) = first quant_artifacts.published_at for fmt - release_date
```

Tracked formats: `nvfp4`, `mxfp4`, `fp8`, `gguf`, `awq`, `gptq`, `mlx`, `int4`.

`publisher_kind` splits who closed the gap:

| Value | Meaning |
|---|---|
| `first_party` | The model vendor shipped the quant themselves |
| `hardware_vendor` | A hardware vendor shipped a quant of someone else's model |
| `community` | Independent re-publishers |

This is a two-sided measurement and both sides matter. **Artifact availability is not
framework support:** an `nvfp4` repo is useless if the serving framework has no kernel
for that format on the user's GPU generation, so `quant_lag` is always reported beside
the framework's own support date for that format (evidence rules, §Quant formats).
Where the artifact landed first, the gap is a framework-kernel question; where support
landed first, it is an artifact-publishing question. Reporting only one side would
assign the delay to the wrong place.

Relation to §6c: a high `capability_gap` with a long `quant_lag` for the formats that
fit consumer hardware is the strongest available evidence for checklist item 2.1.

## 8. Threats to validity — publish these, don't bury them

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
| **Quant-format coverage** (§7) | Hub search is keyword-based; a quant repo with an unconventional name is missed | `quant_lag` is an upper bound on speed, i.e. a lower bound on how fast the ecosystem actually moved |
| **Hardware self-reporting** (§6) | Publish extraction coverage with every figure | Describes reporters, not users; not correctable by reweighting |

## Reproducibility contract

Every generated artifact records: `snapshot_date`, `codebook_version`,
`classifier_model` (exact tag/digest), `prompt_version`, `commit_sha` of this repo, and
the raw-snapshot directory it read. A run that cannot name all six is not publishable.
