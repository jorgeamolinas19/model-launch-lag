# Evidence rules for "support landed"

**Version:** `v1` · every `support_event` row stores `evidence_rule` naming the clause below that produced it.

A support event is a claim about a date. The claim is only as good as the artifact
behind it, so each framework gets an explicit rule and a **fidelity** grade. Fidelity
is reported alongside every latency number; mixing a merge-commit date (exact) with a
release-note date (±release cadence) without saying so would be the quietest way to get
this project wrong.

> **Verified against every repo at HEAD on 2026-10-10** by `scripts/verify_paths.py`:
> 11 of 12 code paths resolved; the one failure (a TensorRT-LLM changelog) is corrected
> below. Re-run that script before any collection run — a stale path yields zero
> support events, which reads as "never supported" rather than as a broken collector,
> and would be invisible in the output.

**Release notes: use the GitHub Releases API, not a file.** All six repos publish
releases with substantive notes (verified: 1.5k–82k characters each), so the API is the
portable release-note source and no per-repo changelog path is needed. Release-note
evidence is dated by `published_at`.

## The general rule

> Support for model *M* in framework *F* landed on the date of the **earliest merged
> artifact that makes *M* runnable by a user of *F*** — where "runnable" means loading
> the published weights and generating, not merely parsing the config.

### How the rule is implemented (and the method that failed)

**Primary method — path history.** For frameworks with a per-architecture
implementation file or directory (`transformers`, `vllm`, `sglang`), the support date is
the **first commit touching that path**. Exact, and immune to search ranking.

**Rejected method — PR search.** Dating support by "earliest merged PR naming the
model" fails when the term appears in thousands of PRs, because the oldest *matches*
are not the implementation PR. Measured: it placed Qwen3 support in `transformers` at
**+530 days**; the first commit to `src/transformers/models/qwen3/` gives **−27 days**.
Wrong sign, wrong order of magnitude, and plausible enough to write a paragraph about.

PR search survives only where no per-architecture path exists (`llama.cpp`,
`TensorRT-LLM`), and support events found that way are graded **`good`, never `exact`**.

**Shared-implementation guard.** A matched path older than the model is a *shared*
implementation — one `deepseek_v2.py` covering several generations — so its age says
nothing about this model. Where a matched path predates release by more than 240 days,
the date is rejected as inherited and the pair becomes `undetermined`.

Two consequences worth stating up front:

- **Naming is not support.** A PR mentioning the model in a test fixture, a benchmark
  config, a docs table row, or a dependency bump does not qualify. The artifact must be
  an implementation, a registration, or a published build.
- **Support can require several PRs.** Where it does (llama.cpp), the event date is the
  **last** required part, because the user cannot run the model until all of them land.
  Store every contributing link.

## Per-framework rules

### `transformers` — `huggingface/transformers`
Included because it is the upstream gate for everyone else, and its two support modes
are themselves a finding.

- **`native`** — merged PR adding `src/transformers/models/<arch>/`. **Fidelity: exact.**
- **`remote_code`** — the model ships its own modeling file and runs only with
  `trust_remote_code=True`. Record as a separate state with the HF repo's first commit
  date, **not** as native support. **Fidelity: exact (HF-side).**

Record both. "Day-0 via remote code, native support 23 days later" is a true and
interesting sentence that a single date would destroy.

### `vllm` — `vllm-project/vllm`
- **Primary:** merged PR adding or modifying `vllm/model_executor/models/<arch>.py` *and* registering the architecture in the model registry. **Fidelity: exact.**
- **Secondary:** entry added to the supported-models documentation table. **Fidelity: exact.**
- **Fallback:** release-note entry naming the model. **Fidelity: coarse.**

### `sglang` — `sgl-project/sglang`
- **Primary:** merged PR under `python/sglang/srt/models/`. **Fidelity: exact.**
- **Fallback:** release-note entry. **Fidelity: coarse.**

Note in findings: SGLang frequently adapts vLLM's implementation, so its latency is
partly a function of vLLM's. Do not present the two as independent.

### `llama.cpp` — `ggml-org/llama.cpp`
Support is **multi-part** and this is the main place a naive rule produces wrong dates.
A new architecture generally needs all of:

1. architecture mapping in `convert_hf_to_gguf.py`
2. graph construction in the model/loader source
3. tokenizer or pre-tokenizer handling where the vocab is new

**Rule:** the event date is the **latest** of the required parts, with every PR link
stored. If only (1) has landed, the model converts but does not run — record
`partial_support` with that date and leave the support event open. **Fidelity: exact,
but the multi-part structure means the single-PR rule used elsewhere would understate
llama.cpp's latency. Say so in the memo.**

### `ollama` — `ollama/ollama` + library
Support ships as a **library entry**, not as code, so the GitHub API alone cannot date
it. The first version of this rule assumed a registry manifest date; probing
(`scripts/probe_ollama.py`) showed that source does not exist, so the rule is rewritten
around what verifiably does.

- **Primary:** earliest `ollama/ollama` **GitHub release whose notes name the model**, dated by the release's `published_at`. Verified usable: 19 of the last 40 releases name at least one cohort model family. **Fidelity: good** — granularity is the release cadence (often same-day, occasionally a few days).
- **Secondary:** presence of the model on `ollama.com/library/<model>` confirms support *exists* but carries only relative dates ("1 year ago"), so it can **confirm** support and never **date** it.
- **Tertiary:** merged PR where a new architecture needed Go-side or vendored-runner work. **Fidelity: exact.**

**Dead ends — do not re-attempt, all three were tested and fail:**

| Source | Result |
|---|---|
| `registry.ollama.ai/v2/library/<m>/tags/list` | HTTP 404 for every model |
| `ollama.com/api/tags?name=<m>` | HTTP 200 but returns **byte-identical payloads for different model names** — it ignores the query. Looks like success; is not. |
| `ollama.com/api/show?name=<m>` | HTTP 405 |

The OCI manifest endpoint (`/v2/library/<m>/manifests/latest`) does return a per-model
digest, but it describes the *current* `latest` tag, so it cannot establish a first
publish date and is unused.

**Dependency to state explicitly:** Ollama vendors llama.cpp, so an Ollama date is
usually gated by the llama.cpp date. Report Ollama latency *and* Ollama-minus-llama.cpp,
and do not read the gap as Ollama being slow.

### `tensorrt-llm` — `NVIDIA/TensorRT-LLM`
- **Primary:** merged PR under `tensorrt_llm/models/` or an `examples/<model>/` directory. **Fidelity: exact.**
- **Fallback:** entry in `docs/source/release-notes.md`, or a GitHub Release whose notes name the model. **Fidelity: coarse.** (There is no `CHANGELOG.md`; the first version of this rule named one and was wrong.)

Support sometimes ships only inside a container image with the changelog as the sole
public artifact, and the repo's publishing cadence is not continuous upstream commits.
**These dates are the lowest-fidelity in the dataset. Grade them, report the grade, and
do not rank TensorRT-LLM against exact-fidelity frameworks without the caveat.** Keeping
this explicit also keeps the finding constructive: it is a publishing-visibility
artifact, not a statement about engineering speed.

## Two support questions that are not architecture support (v2)

### Draft/target pairing (speculative decoding)

A framework can serve a draft model and a target model individually and still reject
them as a speculative pair. Support is therefore a claim about the **pair**, not about
either architecture.

> Pairing support for *(draft D, target T)* in framework *F* landed on the date of the
> earliest merged artifact that lets a user run *T* with *D* as a speculative draft.

- **vLLM / SGLang:** merged PR adding the draft architecture to the speculative-decoding path, or adding the method (EAGLE/MTP) for the target's architecture. **Fidelity: exact.**
- **llama.cpp:** merged support for the draft arch in the draft-model path, since the generic `--draft` flag requires both archs to load **and** vocabularies to match. **Fidelity: exact.**
- **TensorRT-LLM:** merged example or plugin for the speculation method on that model family, or a changelog entry. **Fidelity: coarse.**
- **Ollama:** record `not_applicable` unless the library exposes a draft pairing.

**Vocabulary compatibility is a precondition, not support.** Where a pair shares no
tokenizer, record `not_applicable` with that reason rather than `unsupported` — the
framework cannot be said to lack support for something arithmetically impossible.

### Quant-format support (distinct from artifact availability)

`quant_lag` (metrics §7) measures when a quantized *artifact* appeared. This rule
measures when a *framework* could execute that format, which is a different date and
often the binding one.

> Format support landed on the date of the earliest merged artifact providing kernels
> or a loader for that format, **on a GPU generation the user plausibly has.**

- **vLLM / SGLang:** merged quant-method registration plus a kernel path. **Fidelity: exact.**
- **llama.cpp:** merged quant type in the GGUF type table and the dequant path. **Fidelity: exact.**
- **TensorRT-LLM:** changelog or example demonstrating the format. **Fidelity: coarse.**

**Record the GPU generation requirement with the date.** A format supported only on the
newest architecture is not available to most of the install base, and a date without
that qualifier would overstate real availability. This is a capability statement about
hardware generations, not a judgment about any vendor's roadmap.

## Three distinctions this dataset keeps separate

Conflating these was an error in the first version of these rules. A pre-existing
architecture declaration does **not** prove that every later checkpoint using it was
immediately runnable: a new RoPE scaling scheme, a changed tokenizer, or an added config
field can break a model whose architecture class is already registered.

| Distinction | What the evidence proves | State |
|---|---|---|
| **Architecture support at release** | The framework recognized the architecture before the model became public. Compatibility with *this checkpoint* is **not** established. | `arch_compatible` |
| **Model-specific support** | The framework could load *that particular model* — its config, tokenizer, and implementation requirements. | `supported` |
| **Observed support date** | The earliest *verifiable* date of working support. May be later than an architecture declaration date, and is the only figure safe to quote as latency. | `event_date` + `fidelity` |

Pairs resolved by the architecture-at-release test are therefore recorded as
**`arch_compatible`, not `supported`**.

**A negative offset is never converted to zero.** Zero asserts the checkpoint was
runnable at launch, and that requires its own evidence. Where only a predecessor
architecture is shown to exist, the model-specific support date stays `undetermined`.

Consequence: `arch_compatible` pairs carry **no `days_to_support` value at all** — they
count toward coverage and never toward a median. Enforcing this cleared day-0 latency
claims from **27 of 130 pairs**, each of which had been asserting launch-day support on
architecture evidence alone. Flooring negatives to zero was a systematic downward bias
on measured latency, not a conservative simplification as first assumed.

### Adjudicating negative offsets

Negative offsets are resolved by **historical implementation evidence, not a numeric
threshold** — three successive thresholds each moved the problem rather than solving it.
The procedure, recorded per case in `negative_offsets_adjudicated.csv`:

1. Find the implementation at the negative-offset commit.
2. Identify which publicly released checkpoint it originally supported.
3. Compare the new checkpoint's config and required operations against that implementation.
4. Accept pre-release integration only where evidence ties the implementation to *this* model.

> Methods statement: negative support offsets were manually adjudicated using historical
> implementation evidence. Pre-existing architectures were distinguished from
> model-specific integrations, and architecture presence alone was not treated as proof
> of executable checkpoint compatibility.

## States a (model, framework) pair can be in

Every pair gets a row. Absence of support is data, not a missing value — this is what
makes the censoring in `metrics.md` possible.

| State | Meaning |
|---|---|
| `supported` | Rule satisfied; `event_date` and evidence links stored |
| `partial` | Some required parts landed (llama.cpp convert-only); `event_date` of the partial, support still open |
| `remote_code` | Runnable only via `trust_remote_code` (transformers) |
| `unsupported` | No qualifying artifact as of `snapshot_date` — **right-censored, not missing** |
| `undetermined` | The method could not establish a date: no architecture path matched, or the only match was a shared implementation. **Excluded from all metrics** and flagged for hand resolution, with candidate PR links stored. This state exists because the fallback it replaced was *actively harmful* — PR search dated DeepSeek-V3.2 in SGLang from a GLM-5 MXFP4 pull request. An admitted gap is worth more than a date that cannot be defended, and at 132 pairs hand resolution is tractable. |
| `not_applicable` | Framework structurally cannot serve this model class (e.g. an embedding-only model in a chat-serving framework). Excluded from denominators with a reason. |

## Verification requirement

There are only a few hundred support events in the v1 cohort. **Hand-verify 100% of
them** by opening the stored link and confirming the artifact matches its rule. One
wrong support event moves a headline number; at this volume there is no excuse for
sampling. Record `verified_by` and `verified_at` per row, and treat any unverified row
as excluded from published metrics.
