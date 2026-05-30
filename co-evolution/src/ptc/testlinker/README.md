# TestLinker Integration

This module runs TestLinker as a project technique and writes predictions that downstream generator/evaluation code can merge as `tech_testlinker`.

Install the package with TestLinker dependencies:

```bash
pip install -e './co-evolution[testlinker]'
```

This exposes `ptc-testlinker` and installs the CodeT5 runtime dependencies declared for this integration, including `protobuf` and `sentencepiece`.

## Required Inputs

Run the normal extraction pipeline first:

```bash
mhc method-scan ...
mhc class-scan ...
mhc method-callgraph ...
mhc method-code ...
```

TestLinker expects experiment data under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/
```

Required project inputs:

```text
t2p-candidate-filtered/<project>.csv
method-code/<project>.csv
class/<project>.csv
method/<project>.csv
```

The `class_map/` and `projects_all_functions/` mapping files are auto-generated during the `preprocess` stage from `class/<project>.csv` and `method/<project>.csv`.

## Model Artifacts

The default pretrained CodeT5 directory lives inside the experiment:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/pretrained-models/codet5-base/
```

Place fine-tuned checkpoints in the shared workspace root:

```text
WORKSPACE_DIRECTORY/testlinker-finetuned-checkpoints/codet5-base/
  checkpoint-best-acc/
    pytorch_model.bin
  checkpoint-best-acc_and_f1/
    pytorch_model.bin
  checkpoint-best-f1/
    pytorch_model.bin
  checkpoint-last/
    pytorch_model.bin
```

The default run uses:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/pretrained-models/codet5-base
WORKSPACE_DIRECTORY/testlinker-finetuned-checkpoints/codet5-base/checkpoint-best-acc_and_f1/pytorch_model.bin
```

The pretrained directory is loaded with `transformers.from_pretrained(...)`. The checkpoint directory supplies the fine-tuned TestLinker classifier weights loaded after the base model.

The original TestLinker implementation package and trained assets are available from Figshare:

```text
https://figshare.com/s/6d9a729c2ebb83c4b291
```

## Optional Ground Truth

Pass `--include-labels` to include labels during preprocessing. The command looks for:

```text
PROJECT_DIRECTORY/data/ground-truth/<project>.csv
```

Set `--project-directory` or `ME_PROJECT_DIRECTORY` to point at the repository root. If omitted, the configured project directory from `.env` is used.

Expected columns:

```text
project,from_tctracer_fqs,to_tctracer_fqs,from_url,to_url
```

If the file is missing or lacks the required columns, labels are skipped without failing the run. When labels are included, the model input CSV receives a binary `label` for each candidate by matching `from_url` and `to_url`.

## Tokenizer Modes

For paper-faithful runs, use an environment close to the original TestLinker setup:

```text
python 3.8
transformers 4.30
torch 2.1.1
cuda 12.1
```

Default mode:

```text
--tokenizer-mode original
```

`original` loads the tokenizer with the same style used by the TestLinker authors:

```python
RobertaTokenizer.from_pretrained(...)
```

With newer `transformers` versions, `Salesforce/codet5-base` can fail to load because cached tokenizer metadata contains old special-token entries. For local debugging, use:

```text
--tokenizer-mode auto
```

`auto` first tries the original tokenizer path, then falls back to constructing the tokenizer directly from `vocab.json` and `merges.txt` with the same special token strings.

Use this only for compatibility checks:

```text
--tokenizer-mode fallback
```

`fallback` skips the original path and always uses the `vocab.json` / `merges.txt` fallback.

If every `score` is almost identical, inspect tokenizer loading first. A broken fallback can encode Java input as mostly special tokens, which makes CodeT5 see nearly identical inputs.

## Running the Pipeline

Full pipeline for one project:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage all \
  --project "commons-io" \
  --top-k 1 \
  --tokenizer-mode original
```

With labels and TestLinker author ordering:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage all \
  --project "commons-io" \
  --include-labels \
  --order-production-method testlinker \
  --model-name-or-path Salesforce/codet5-base
```

Project selection supports exactly one of:

```bash
--project commons-io
--projects commons-io,commons-lang
--project-index "10:20"
--project-index ":"
```

`--project-index` is resolved against:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/project.csv
```

## Slurm Wrapper

Use `scripts/job.sh` for cluster execution:

```bash
sbatch --array=1-2 scripts/job.sh \
  --command testlinker \
  --stage all \
  --projects "commons-io,checkstyle" \
  --top-k 1 \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

For Slurm arrays, `job.sh` selects the current project from `--projects` or derives a project index from the array task.

## Stages

Run stages separately when debugging.

Preprocess:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage preprocess \
  --project commons-io \
  --order-production-method testlinker
```

Execute:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage execute \
  --project commons-io \
  --top-k 1
```

Postprocess:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage postprocess \
  --project commons-io \
  --top-k 1
```

## Stage Outputs

`preprocess` reads candidate and method-code CSVs and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/input/model-csv-input/<project>.csv
```

The model input includes:

```text
project,from_url,from_name,from_file,body,to_url,to_name,
from_testlinker_fqs,to_testlinker_fqs,to_testlinker_p,label
```

`execute` runs the model/ranker and writes the same rows plus `score` and `rank`:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/<model>/model-output-csv/<project>.csv
```

`postprocess` reads model output and writes predictions under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/<model>/<method-resolver>/<project>.csv
```

Postprocess appends:

```text
recommender,label_pred
```

## Method Resolvers

`--method-resolver` controls how model-ranked rows become method links:

| Resolver | Behavior |
|----------|----------|
| `testlinker` | Applies the TestLinker signature mapping algorithm. This is the default. |
| `testlinkerv2` | Uses direct top-k URL matching from symbol-solver candidates. |
| `all` | Writes outputs for both resolver modes. |

Examples:

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage postprocess \
  --project commons-io \
  --method-resolver testlinkerv2

ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage postprocess \
  --project commons-io \
  --method-resolver all
```

## Troubleshooting

- Missing `class/<project>.csv` or `method/<project>.csv`: run `mhc class-scan` and `mhc method-scan`, then rerun `preprocess`.
- Missing model files: verify the pretrained CodeT5 directory under the experiment and fine-tuned checkpoints under `WORKSPACE_DIRECTORY/testlinker-finetuned-checkpoints/`.
- Uniform or suspiciously similar scores: verify tokenizer mode and inspect encoded tokens for a known method name such as `closeQuietly`.
- CUDA failures: pass `--no-cuda` for CPU debugging or use the cluster `job.sh` wrapper.
- Missing labels: confirm `PROJECT_DIRECTORY/data/ground-truth/<project>.csv` has the expected columns.
