# co-evolution

Python package for linking, reviewing, and evaluating production-test method co-evolution. It exposes:

| CLI | Purpose |
|-----|---------|
| `ptc-llm` | LLM-based method-to-method linking |
| `ptc-history-viewer` | Local FastAPI browser UI for method-history review |
| `ptc-testlinker` | Neural TestLinker integration |
| `ptc-sbatch` | Slurm array command expansion and truncation helper |

Install from the repository root:

```bash
pip install -e ./co-evolution
pip install -e './co-evolution[llm]'        # OpenAI and Hugging Face backends
pip install -e './co-evolution[testlinker]' # TestLinker/CodeT5 runtime
```

All commands use the current experiment layout:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/
```

Pass `--workspace-directory` explicitly and pass `--experiment-name` or set `ME_EXPERIMENT_NAME`.

## `ptc-llm llm-m2m-link`

Classifies candidate test-production method pairs using an LLM. Inputs are candidate CSVs produced by generator scripts:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/t2p-candidate-filtered/<project>.csv  # t2p
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/fanin/<project>.csv                   # p2t
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method-code/<project>.csv
```

Run with the OpenAI Responses API:

```bash
ptc-llm llm-m2m-link \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "commons-io" \
  --input-kind t2p \
  --api-type openai-responses \
  --model-name-or-path "gpt-4.1-mini" \
  --api-key "$OPENAI_API_KEY" \
  --batch-size 8
```

Run with a local or self-hosted Hugging Face model:

```bash
ptc-llm llm-m2m-link \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "commons-io" \
  --input-kind t2p \
  --api-type huggingface \
  --model-name-or-path "Qwen/Qwen2.5-0.5B-Instruct" \
  --batch-size 4 \
  --dtype auto
```

`--api-type auto` routes GPT-family model IDs to the OpenAI Responses API and other model IDs to Hugging Face.

Outputs are written under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/llm/<input-kind>/<model-name>/
  prediction/<project>.csv
  request/<project>.csv
  error/<project>.csv
```

Use parse mode to project stored LLM responses into link rows without re-running inference:

```bash
ptc-llm llm-m2m-link \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage parse \
  --project "commons-io" \
  --input-kind t2p \
  --model-name-or-path "gpt-4.1-mini"
```

Important options:

| Flag | Default | Description |
|------|---------|-------------|
| `--input-kind` | `t2p` | `t2p` for test-to-production or `p2t` for production-to-test |
| `--api-type` | `auto` | `auto`, `openai-responses`, or `huggingface` |
| `--short-model-name` | derived | Override the model folder name |
| `--prompt-format` | `auto` | `auto`, `json`, or `text` |
| `--resume` | `none` | `none`, `all`, or `error` |
| `--stage` | `execute` | `execute` or `parse` |

## `ptc-history-viewer`

Starts a local browser UI for comparing method histories and reviewing sampled rows.

```bash
ptc-history-viewer serve \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --host 127.0.0.1 \
  --port 8765
```

Open `http://127.0.0.1:8765`.

Development auto-reload:

```bash
ptc-history-viewer serve \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --host 127.0.0.1 \
  --port 8765 \
  --reload
```

The viewer can:

- Compare two methods by GitHub blob URL and history tool.
- Compare two cached history JSON files directly.
- Browse sampled CSVs under the experiment directory.
- Write `revision_url` and manual `note` values back into review CSVs.

Write revision links from the command line:

```bash
ptc-history-viewer add-revision-links \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --csv "$ME_WORKSPACE_DIRECTORY/experiment/$ME_EXPERIMENT_NAME/aggregate/sample.csv" \
  --base-url "http://127.0.0.1:8765"
```

## `ptc-testlinker`

Runs the neural TestLinker pipeline. The detailed setup, model layout, tokenizer modes, and stage outputs are documented in [src/ptc/testlinker/README.md](src/ptc/testlinker/README.md).

Typical run:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage all \
  --project "commons-io" \
  --top-k 1 \
  --tokenizer-mode original
```

Project selection supports `--project`, `--projects`, or `--project-index`.

## `ptc-sbatch`

Expands and normalizes Slurm array commands for `scripts/job.sh`. It reads `project.csv`, skips completed outputs unless `--replace` is passed, handles large array ranges, and prints a shell-safe `sbatch` command.

Examples:

```bash
ptc-sbatch sbatch --array=0-999 scripts/job.sh \
  --command method-history \
  --tool-name historyFinder \
  --shards 10 \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"

ptc-sbatch workspace/cmd.txt --replace
```

The helper writes summaries to stderr and the final command to stdout so it can be reviewed, redirected, or submitted.
