# Issue codebook — version 2

**Version:** `v2` · **Frozen:** 2026-10-10 · **Changes require a new version number.**

> **v1 → v2:** added category `speculative_decoding` (precedence 5) and widened
> `quantization` to name 2026 formats explicitly. v1 was frozen but **never applied to
> any label**, so no re-labeling is owed and no cross-version comparison is affected.
> v1 is kept in the repo as [codebook-v1.md](codebook-v1.md) for provenance.

Every stored label carries this version string. Categories are never edited in place;
a changed definition means `v2`, and cross-version comparisons must be stated as such.

## How to apply this codebook

Label the **issue as filed**, not as resolved. You are answering: *what stopped this
person, in their own report?* Do not use maintainer replies to reclassify — that leaks
resolution into the label and makes the classifier's job impossible (it only sees the
opening post).

Each issue gets exactly one `category_primary`, plus zero or more `category_secondary`
drawn from the same enum. The primary is chosen by the **precedence ladder** below:
walk top to bottom, take the first rule that applies. Everything else that genuinely
applies goes in secondary.

Rationale for a ladder rather than "pick the best fit": the common real issue is
compound ("OOM loading the AWQ quant with a broken chat template"). Without a written
precedence rule, two labelers — or the same labeler on two days — will disagree, and
both your hand labels and the classifier prompt will drift.

## Precedence ladder

The ordering principle is **most specific identified cause wins**. `correctness` and
`performance` are symptom buckets, used only when no more specific cause is named.

| # | Category | Applies when |
|---|---|---|
| 1 | `missing_feature` | The framework has **no implementation** of the model, architecture, or required feature. Nothing else can be diagnosed until it exists. Includes "please add support for X", unrecognized `architectures` entry, unimplemented attention variant, missing LoRA/vision/tool-call path for a model the framework otherwise loads. |
| 2 | `install_build` | The user cannot obtain a working binary, wheel, container, or compiled extension. Includes pip resolution conflicts, CUDA/ROCm toolkit mismatch, missing kernel for a compute capability, cmake/ninja failure, missing shared library at import. |
| 3 | `template_tokenizer` | Chat template, special/control tokens, tokenizer config, EOS/BOS handling, pre-tokenizer mismatch, vocab size disagreement, `added_tokens` not honored. Symptoms: model never stops, emits raw template markup, tool-call tags leak into output. |
| 4 | `quantization` | The problem is specific to a **quantized artifact** — GGUF, AWQ, GPTQ, FP8, **NVFP4, MXFP4**, INT4/INT8, MLX, bitsandbytes, KV-cache quant. Conversion failure, unsupported quant+arch combination, **a format with no kernel for the user's GPU generation**, quant-only garbage output, quant-only accuracy loss. Record the format in `issue_hardware.quant_mentioned`; format is a reporting dimension, not a separate category. |
| 5 | `speculative_decoding` | Specific to **draft/target pairing** — EAGLE, Medusa, MTP, or an explicit draft model. Pairing rejected despite both halves loading, vocab or tokenizer mismatch between draft and target, acceptance-rate collapse, or a crash only with speculation enabled. Note that a framework serving both halves individually does **not** imply the pair is supported, which is why this is its own category rather than a flavor of `missing_feature`. |
| 6 | `oom_hardware` | A resource or hardware ceiling with otherwise-correct software. OOM at load or at context length, insufficient VRAM for the TP/PP layout, unsupported GPU generation, NVLink/P2P requirement, host RAM exhaustion during conversion. |
| 7 | `correctness` | Wrong, degraded, or nonsensical output with **no more specific cause named** in the report. Includes benchmark-score regressions and non-reproducible generations where the author does not implicate quant or template. |
| 8 | `performance` | Slow prefill/decode, low throughput, poor batching or scaling, high TTFT, regression versus another framework — with no more specific cause named. |
| 9 | `other` | Documentation, usage questions answered without a code change, CI/infra noise, licensing, duplicate-of-unknown, anything that survives the ladder. |

### Boundary rules for the cases that will actually bite you

These are the disagreements this codebook exists to settle. Each one is a real
judgment call with a stated answer, not an obvious case.

- **"No kernel image is available for execution on the device"** → `install_build` (2), not `oom_hardware` (5). The wheel lacks the compute capability; the hardware is fine and a correct build fixes it.
- **"CUDA out of memory" while converting to GGUF** → `oom_hardware` (5). The conversion being quant-related does not make it `quantization` (4); the quant path is incidental, the ceiling is memory. Put `quantization` in secondary.
- **GGUF conversion script errors with `unknown architecture`** → `missing_feature` (1), not `quantization` (4). The conversion tooling has no mapping for the arch at all.
- **Quantized model outputs garbage, FP16 is fine** → `quantization` (4), not `correctness` (6). The author has implicated the quant by contrast.
- **Model never emits a stop token** → `template_tokenizer` (3), not `correctness` (6), even when the author describes it as "broken output".
- **"Model loads but is 3x slower than framework Y"** → `performance` (7). If the author names a missing fused kernel or unimplemented attention backend as the cause, it becomes `missing_feature` (1).
- **"Supports base but not the Instruct/VL variant"** → `missing_feature` (1), with a note in `reason` that it is variant-scoped. This case is central to the architecture-vs-variant question, so these must be findable.
- **Request to bump a dependency so a model works** → `install_build` (2), not `missing_feature` (1), when the framework code already supports the model.
- **"Speculative decoding with this draft model is slower than without"** → `speculative_decoding` (5), not `performance` (8). The author has implicated the pairing.
- **"NVFP4 checkpoint fails to load on an Ampere GPU"** → `quantization` (4), not `oom_hardware` (6) and not `install_build` (2). The format requires a newer GPU generation's kernels; record `nvfp4` as the format.
- **"Draft model not recognized" when the framework has no speculative support at all** → `missing_feature` (1). Precedence 1 still wins over 5 when the subsystem is simply absent.

## Severity

Severity answers: **can this person get their job done today?**

| Value | Definition | Observable signals |
|---|---|---|
| `blocker` | Cannot run the model at all for the stated goal. No workaround given or found in-thread at filing time. | Traceback terminating at load/startup; "cannot", "fails to start", "unusable"; no `--flag` workaround mentioned |
| `degraded` | Runs, but produces wrong output, is materially slower, or requires a non-obvious workaround. | "works if I disable X"; "output is wrong but it runs"; a numeric regression |
| `minor` | Cosmetic, informational, or a question. No functional impact. | Warning-noise reports; doc fixes; "is X supported?" with no attempt |

**Known limitation, state it in the README:** severity is weakly observable from issue
text and is inflated by authors who write dramatically. Where available, record these
structural signals alongside the label so severity can be partially audited rather than
trusted: traceback present (bool), closed by a linked commit/PR (bool), maintainer
labels (`bug` / `enhancement` / `question`), reaction count. Report agreement between
LLM severity and `closed_by_fix` as a sanity check.

## Exclusions — label as `excluded`, do not categorize

Excluded issues stay in the database with a reason so the filtering is auditable and
reversible. They are removed from all metric denominators.

| Reason code | Rule |
|---|---|
| `bot` | Author is a bot (`type == "Bot"`, or login matches `*[bot]`, `dependabot`, `github-actions`, `stale`) |
| `duplicate` | Closed as duplicate, or body is only a link to another issue |
| `passing_mention` | Model named only in passing — a version table, a log line of an unrelated run, a "me too on a different model" comment. The issue must be *about* the model. |
| `not_model_specific` | A general framework bug that would occur with any model |
| `maintainer_task` | Tracking issue, release checklist, roadmap item filed by a maintainer |
| `non_english` | Body not in English and not machine-translatable with confidence (record it; do not silently drop) |

## Gaps found while labeling 339 issues (candidates for v3 — v2 is frozen)

Applying v2 to the stratified sample surfaced three systematic problems. They are
recorded here, not fixed here: v2 stays frozen so the published labels stay comparable.

1. **Implementation crashes have no home.** A large share of issues are runtime
   exceptions, hangs, segfaults or assertion failures in otherwise-correct environments
   with no more specific cause named (`AttributeError ... 'sampler'`, Xid faults, watchdog
   timeouts, `GGML_ASSERT`). `correctness` is defined as *wrong output*, so these fall to
   `other`, which ends up at ~25% of the reference set and becomes the top "category" —
   a bucket, not a finding. **v3 should add `runtime_crash`** (process dies or hangs; no
   output to be wrong) with precedence just above `correctness`.
2. **`other` also absorbs three distinct non-defect kinds**: registry/distribution
   problems (pull EOF, missing Docker tag), API-semantics mismatches (`reasoning_content`
   ignored, `previous_response_id` unsupported), and maintainer artifacts (RFCs, CI, test
   suites that mention a model in passing). The last kind should mostly have been
   excluded as `maintainer_task`; the exclusion regex needs `\[RFC\]`, `\[Test\]`,
   `\[CI Failure\]`, `\[Perf\]` tracking patterns and "Benchmark:" titles.
3. **"Format X unsupported for model Y" straddles two rules.** Rule 1 (`missing_feature`:
   no implementation) and rule 4 (`quantization`: unsupported quant+arch combination) both
   claim it. The labels here follow rule 4 for every case where a named quant format is
   the thing missing (FP8 for Llama 4, AWQ MoE, NVFP4 PLE tables, w4a8 on NPU), and rule 1
   only when the architecture itself is absent. v3 should state this explicitly in the
   boundary rules.

Also observed: **the keyword baseline over-predicts `install_build` by ~5x** because
issue templates embed environment dumps (`CUDA used to build PyTorch`, `pip`, `cmake`,
`wheel`) regardless of what the issue is about. Any keyword rule for `install_build`
must exclude the `collect_env.py` block, or weight the title far above the body.

## Labeling protocol

1. **Stratified sample.** Draw by framework × category-guess so rare categories are not left with two examples. Target **340 labels** (9 categories in v2), minimum 20 per category after exclusions. `speculative_decoding` is expected to be the rarest and must be deliberately oversampled, not left to chance. Merge any category still under 10 into `other` for reporting and say so.
2. **Split before you look.** Randomly assign 40% `dev` / 60% `test` at sample time and record it in the DB. Iterate the classifier prompt **only** against `dev`. Touch `test` once, at the end, and report that number. Tuning against the set you report is overfitting with extra steps.
3. **Self-agreement.** Re-label 50 `dev` issues at least 5 days later, blind to your first pass. Report Cohen's κ for category and for severity. This is a **reference point, not a hard ceiling**: it measures the labeler's own consistency. A classifier *can* score above it, but the excess cannot be read as improvement — it is at least as likely to be fitting the labeler's noise. Publishing it is what lets a reader judge how much of any accuracy gap is signal.
4. **Label from the opening post only** — title, body, and author-attached labels. Collapse long bodies to the first traceback plus the first 2000 characters, exactly as the classifier will see them, so human and machine see the same input.
