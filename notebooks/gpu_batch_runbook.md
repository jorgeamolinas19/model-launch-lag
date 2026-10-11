# GPU batch runbook — full classification + classifier benchmark

The dev loop runs locally on CPU (Ollama, 3–4B model, slow but free). The full batch and
the throughput/VRAM benchmark need a GPU. This runbook is for a **free** Kaggle notebook
(30 GPU-h/week, 2×T4 or P100); it also works on any box with vLLM.

Every run records the exact model tag, prompt version, and repo commit in `runs`, so a
label produced here is reproducible from the published repo.

## 0. One-time

```bash
git clone https://github.com/jorgeamolinas19/model-launch-lag && cd model-launch-lag
pip install -q vllm                      # Kaggle: ~3 min; T4 needs --dtype half
```

Upload `db/launch_lag.sqlite` as a Kaggle dataset (it is gitignored — it holds issue
excerpts, which stay off GitHub) and copy it to `db/`.

## 1. Serve a candidate classifier

**Capacity check first.** An 8B checkpoint in fp16 is ~16 GB of weights — it does not
fit a single 16 GB T4 or P100 once KV cache and activations are added. On Kaggle use
either the 2×T4 accelerator with tensor parallelism, or a quantized/smaller checkpoint:

| checkpoint | weights (fp16 / 4-bit) | single T4 16 GB | 2×T4 TP=2 |
|---|---|---|---|
| Qwen/Qwen3-4B | ~8 GB / — | fits (~6 GB KV headroom) | fits |
| Qwen/Qwen3-8B-AWQ (4-bit) | — / ~5 GB | fits | fits |
| Qwen/Qwen3-8B (fp16) | ~16 GB / — | **does not fit** | fits, modest KV |
| nvidia/NVIDIA-Nemotron-Nano-9B-v2 (fp16) | ~18 GB / — | **does not fit** | fits, modest KV |
| google/gemma-3-4b-it | ~8 GB / — | fits | fits |

```bash
# candidate A — single T4: a 4B model in fp16
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-4B \
  --dtype half --max-model-len 6144 --gpu-memory-utilization 0.90 --port 8000 &

# candidate A' — 2xT4: the 8B in fp16 with tensor parallelism
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-8B \
  --dtype half --tensor-parallel-size 2 --max-model-len 6144 --gpu-memory-utilization 0.90 --port 8000 &
```
`--max-model-len 6144` is enough: prompts are ~1.5k tokens and outputs ~100. If vLLM
fails during profiling with an OOM, lower `--gpu-memory-utilization` to 0.85 before
anything else.

Record peak VRAM while the batch runs:

```bash
nvidia-smi --query-gpu=memory.used --format=csv -l 5 > vram_qwen3-8b.csv &
```

## 2. Classify

```bash
# dev first, ALWAYS - never iterate the prompt on test
python scripts/classify_llm.py --base-url http://localhost:8000/v1 --model Qwen/Qwen3-8B --split dev
python scripts/eval_classifier.py --split dev --sources regex_baseline,llm

# only when the prompt is frozen:
python scripts/classify_llm.py --base-url http://localhost:8000/v1 --model Qwen/Qwen3-8B --all
python scripts/eval_classifier.py --split test --sources regex_baseline,llm
```

## 3. Second and third candidates (the benchmark)

Stop the server, swap the model, write under a distinct source so labels coexist:

```bash
# Nemotron-Nano-9B-v2 is ~18 GB in fp16: serve it with --tensor-parallel-size 2 on 2xT4
python scripts/classify_llm.py --base-url http://localhost:8000/v1 \
  --model nvidia/NVIDIA-Nemotron-Nano-9B-v2 --all --source llm:nemotron-nano-9b
python scripts/classify_llm.py --base-url http://localhost:8000/v1 \
  --model google/gemma-3-4b-it --all --source llm:gemma3-4b
python scripts/eval_classifier.py --split test --sources regex_baseline,llm,llm:nemotron-nano-9b,llm:gemma3-4b
```

A hosted comparison point (managed inference vs self-hosted) via a NIM endpoint:

```bash
LLM_API_KEY=$NVIDIA_API_KEY python scripts/classify_llm.py \
  --base-url https://integrate.api.nvidia.com/v1 --model nvidia/nvidia-nemotron-nano-9b-v2 \
  --all --source llm:nim-nemotron-nano-9b
```

## 4. Benchmark table (fill from the `runs` notes + nvidia-smi logs)

| classifier | params | test acc (cat) | kappa | sev acc | issues/min | peak VRAM | $ |
|---|---|---|---|---|---|---|---|
| regex baseline | — | | | | ∞ | 0 | 0 |
| maintainer labels | — | | | | — | 0 | 0 |
| Qwen3-8B (vLLM, T4) | 8B | | | | | | 0 |
| Nemotron-Nano-9B-v2 (vLLM, T4) | 9B | | | | | | 0 |
| gemma-3-4b-it (vLLM, T4) | 4B | | | | | | 0 |
| Nemotron-Nano-9B-v2 (NIM) | 9B | | | | | n/a | credits |

Throughput is `issues / minutes` from the run notes; accuracy comes from
`eval_classifier.py --split test`. Report the self-agreement kappa next to every
accuracy, since nothing can honestly score above it.

## Known T4 constraints

- No bf16: `--dtype half`. FP8 checkpoints will not load — this is itself a `quantization`
  category datum (format needs a newer GPU generation).
- 16 GB: 8–9B models in fp16 fit with ~8k context; nothing larger without quantization.
