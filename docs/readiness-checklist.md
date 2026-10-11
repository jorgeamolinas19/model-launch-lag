# Open-model launch readiness checklist

**Status: scaffold. Every item below is a hypothesis until it carries evidence.**

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
| 1.3 | Chat template validated against each target framework's renderer | Template divergence is hypothesized as a top-3 category (metrics §4) | _pending_ | — |
| 1.4 | Config `architectures` string stable between preview and release | A renamed arch class silently breaks shipped registry entries | _pending_ | — |

## Phase 2 — Day 0 (launch artifacts)

| # | Condition | Hypothesis | Evidence | n |
|---|---|---|---|---|
| 2.1 | A quantized artifact published at launch, not weeks later | Absence drives the `capability_gap`: users attempt fp16 on cards that cannot hold it | _pending_ | — |
| 2.2 | Hardware requirements table published with the weights | Reduces `oom_hardware` volume in week 1 | _pending_ | — |
| 2.3 | Stated minimum framework versions in the model card | `install_build` issues cluster where this is missing | _pending_ | — |
| 2.4 | Smallest family member released alongside the largest | Gives the ecosystem something runnable on consumer hardware on day 0 | _pending_ | — |
| 2.5 | Tokenizer files complete and self-consistent | `template_tokenizer` is hypothesized as the highest-severity-per-issue category | _pending_ | — |

## Phase 3 — Week 1 (feedback loop)

| # | Condition | Hypothesis | Evidence | n |
|---|---|---|---|---|
| 3.1 | A single canonical place to report model-specific issues | Fragmentation across 6 repos duplicates triage | _pending_ | — |
| 3.2 | Known-limitations section updated as issues land | Reduces duplicate filing | _pending_ | — |
| 3.3 | Variant-specific gaps stated explicitly | "Base works, VL does not" surfaces repeatedly as `missing_feature` | _pending_ | — |

---

## Scoring a launch

Once items are earned, each cohort model is scored against the checklist and the score
is correlated with observed `days_to_support` and `issue_load`. **This is the
validation step, not decoration:** if the score does not correlate, the checklist is
wrong and this document gets rewritten rather than published. Report the correlation
even when it is weak, with n and a confidence interval — a checklist that admits its
own predictive limits is usable; one that hides them is not.

## Framing

Written as enablement, not assessment. Several conditions are things a *framework* can
only partially control — a maintainer cannot upstream an implementation for weights
they have not seen, which makes 1.1 a statement about access and coordination rather
than about engineering speed. Where the data shows a gap, the item names the
coordination fix, not a responsible party.
