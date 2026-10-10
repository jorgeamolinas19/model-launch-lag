# Evidence rules for "support landed"

**Version:** `v1` · every `support_event` row stores `evidence_rule` naming the clause below that produced it.

A support event is a claim about a date. The claim is only as good as the artifact
behind it, so each framework gets an explicit rule and a **fidelity** grade. Fidelity
is reported alongside every latency number; mixing a merge-commit date (exact) with a
release-note date (±release cadence) without saying so would be the quietest way to get
this project wrong.

> **Paths below must be verified against each repo before collection.** Framework
> layouts move between versions and these are written from prior familiarity, not from
> a live read. `scripts/verify_paths.py` (to write) should assert each glob matches at
> least one existing file at HEAD and fail loudly otherwise.

## The general rule

> Support for model *M* in framework *F* landed on the date of the **earliest merged
> artifact that makes *M* runnable by a user of *F*** — where "runnable" means loading
> the published weights and generating, not merely parsing the config.

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

### `ollama` — `ollama/ollama` + library registry
Support ships as a **library entry**, not as code, so the GitHub API alone cannot date it.

- **Primary:** first published manifest date for `library/<model>` from the registry API. **Fidelity: good** (publish date, not announcement date).
- **Secondary:** merged PR where a new architecture needed Go-side or vendored-runner work. **Fidelity: exact.**

**Dependency to state explicitly:** Ollama vendors llama.cpp, so an Ollama date is
usually gated by the llama.cpp date. Report Ollama latency *and* Ollama-minus-llama.cpp,
and do not read the gap as Ollama being slow.

### `tensorrt-llm` — `NVIDIA/TensorRT-LLM`
- **Primary:** merged PR under the model definitions directory or an `examples/<model>/` directory. **Fidelity: exact.**
- **Fallback:** changelog or release-note entry naming the model. **Fidelity: coarse.**

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

## States a (model, framework) pair can be in

Every pair gets a row. Absence of support is data, not a missing value — this is what
makes the censoring in `metrics.md` possible.

| State | Meaning |
|---|---|
| `supported` | Rule satisfied; `event_date` and evidence links stored |
| `partial` | Some required parts landed (llama.cpp convert-only); `event_date` of the partial, support still open |
| `remote_code` | Runnable only via `trust_remote_code` (transformers) |
| `unsupported` | No qualifying artifact as of `snapshot_date` — **right-censored, not missing** |
| `not_applicable` | Framework structurally cannot serve this model class (e.g. an embedding-only model in a chat-serving framework). Excluded from denominators with a reason. |

## Verification requirement

There are only a few hundred support events in the v1 cohort. **Hand-verify 100% of
them** by opening the stored link and confirming the artifact matches its rule. One
wrong support event moves a headline number; at this volume there is no excuse for
sampling. Record `verified_by` and `verified_at` per row, and treat any unverified row
as excluded from published metrics.
