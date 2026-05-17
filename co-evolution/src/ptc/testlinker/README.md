# TestLinker Integration

This module runs TestLinker as a project technique and writes predictions that
`generate_t2p_tech.py` can merge as `tech_testlinker`.

## Install

Install the `co-evolution` package with TestLinker dependencies:

```bash
pip install -e ./co-evolution[testlinker]
```

This exposes the `ptc-testlinker` command and installs the extra CodeT5 runtime
dependencies declared for the TestLinker integration, including `protobuf` and
`sentencepiece` for loading the CodeT5 tokenizer with current `transformers`
versions.

## Inputs

Before running TestLinker, generate the normal project artifacts:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/t2p-candidate-filtered/<project>.csv
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method-code/<project>.csv
```

TestLinker runtime artifacts and the pretrained base model default to the
experiment directory:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/
  pretrained-models/
    codet5-base/
      config.json
      pytorch_model.bin
      tokenizer files...
```

Place fine-tuned checkpoints in the shared workspace root:

```text
WORKSPACE_DIRECTORY/
  testlinker-finetuned-checkpoints/
    codet5-base/
      checkpoint-best-acc/
        pytorch_model.bin
      checkpoint-best-acc_and_f1/
        pytorch_model.bin
      checkpoint-best-f1/
        pytorch_model.bin
      checkpoint-last/
        pytorch_model.bin
```

The mapping files (`class_map/` and `projects_all_functions/`) are always
auto-generated during the preprocess stage from
`experiment/EXPERIMENT_NAME/class/<project>.csv` and
`experiment/EXPERIMENT_NAME/method/<project>.csv`. Run `mhc class-scan` and
`mhc method-scan` first to produce those CSVs.

The default run uses:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/pretrained-models/codet5-base
WORKSPACE_DIRECTORY/testlinker-finetuned-checkpoints/codet5-base/checkpoint-best-acc_and_f1/pytorch_model.bin
```

The pretrained CodeT5 directory is the base model/tokenizer loaded by
`transformers.from_pretrained(...)`. The `checkpoint-*` directories are the
fine-tuned TestLinker classifier weights loaded after the base model.

The TestLinker paper implementation package and trained assets are available
from Figshare: <https://figshare.com/s/6d9a729c2ebb83c4b291>.

The mapping files are always auto-generated during preprocess from our class and
method scan data.

Ground-truth files are optional. If you pass `--include-labels`, preprocessing
looks for:

```text
PROJECT_DIRECTORY/data/ground-truth/<project>.csv
```

Pass `--project-directory` (or set `ME_PROJECT_DIRECTORY` in `.env`) to point
at the project root. If omitted, the cache directory is used as fallback.

The expected columns are:

```text
project,from_tctracer_fqs,to_tctracer_fqs,from_url,to_url
```

If the file is missing or does not have those columns, labels are skipped
without an error. When labels are included, the model input CSV contains a
binary per-candidate `label`, set by matching each candidate row's `to_url`
against the ground-truth `to_url` for the same `from_url`.

## Tokenizer Fidelity

For paper-faithful runs, use the original TestLinker environment as closely as
possible:

```text
python 3.8
transformers 4.30
torch 2.1.1
cuda 12.1
```

The default tokenizer mode is:

```text
--tokenizer-mode original
```

This calls the same style of tokenizer load used by the TestLinker authors:

```python
RobertaTokenizer.from_pretrained(...)
```

With newer `transformers` versions, `Salesforce/codet5-base` may fail to load
because the cached tokenizer metadata has old special-token entries that newer
tokenizer code rejects. For local debugging only, use:

```text
--tokenizer-mode auto
```

`auto` first tries the original tokenizer path, then falls back to constructing
the tokenizer directly from `vocab.json` and `merges.txt` with the same special
token strings. This is useful for checking the pipeline on a laptop, but final
reported results should use `original` in an author-compatible environment.

If every `score` is almost identical, first suspect tokenizer loading. A
broken fallback can encode each Java input as only special tokens, which makes
CodeT5 see nearly the same empty input for every invocation. A healthy tokenizer
should encode `closeQuietly` into several non-padding tokens, not only `<s>` and
`</s>`.

`--tokenizer-mode fallback` skips the original path and always uses the
`vocab.json` / `merges.txt` fallback. Treat it as a troubleshooting option, not
the default experiment mode.

## Run With Job Script

Run the full TestLinker pipeline for one or more projects:

```bash
scripts/job.sh \
  --command testlinker \
  --stage all \
  --projects "commons-io" \
  --top-k 1
```

For a SLURM array, `job.sh` selects the current project from `--projects` and
passes it to `ptc-testlinker`.

## Stages

Run stages individually when debugging:

```bash
ptc-testlinker testlinker \
  --stage preprocess \
  --workspace-directory .cache \
  --project commons-io \
  --order-production-method testlinker
```

Project selection supports the same single/list/range forms as `mhc`:

```bash
# explicit list
ptc-testlinker testlinker \
  --stage all \
  --workspace-directory eval \
  --projects commons-io,commons-lang \
  --tokenizer-mode auto \
  --include-labels \
  --order-production-method testlinker \
  --model-name-or-path Salesforce/codet5-base

# rows 10 through 19 from workspace-eval/data/repository/repository.csv
ptc-testlinker testlinker \
  --stage all \
  --workspace-directory eval \
  --project-index "10:20" \
  --tokenizer-mode auto \
  --include-labels \
  --order-production-method testlinker \
  --model-name-or-path Salesforce/codet5-base

# all projects
ptc-testlinker testlinker \
  --stage all \
  --workspace-directory eval \
  --project-index ":" \
  --tokenizer-mode auto \
  --include-labels \
  --order-production-method testlinker \
  --model-name-or-path Salesforce/codet5-base
```

```bash
ptc-testlinker testlinker \
  --stage execute \
  --workspace-directory .cache \
  --project commons-io \
  --top-k 1
```

## Stage Outputs

`preprocess` reads project CSVs and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/input/model-csv-input/<project>.csv
```

This CSV has one row per candidate and includes `project,from_url,from_name,
from_file,body,to_url,to_name,from_testlinker_fqs,to_testlinker_fqs,
to_testlinker_p,label`.

`execute` reads the CSV, runs the model/ranker, and writes the same rows plus
`score,rank`:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/<model>/model-output-csv/<project>.csv
```

`postprocess` reads the model output CSV and writes the same rows plus
`recommender,label_pred` under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/<model>/<method-resolver>/<project>.csv
```

Default resolver is `testlinker`. Pass `--method-resolver` to select one or
both resolvers:

```bash
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io

# direct top-k URL match
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io \
  --method-resolver testlinkerv2

# both outputs
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io \
  --method-resolver all
```

Postprocess output appends:

```text
recommender,label_pred
```

`label_pred` is the 0/1 recommendation. `testlinker` resolves the top-k ranked
rows through mapping JSON files, while `testlinkerv2` directly marks rows with
`rank <= top_k`.

`generate_t2p_tech.py` merges the `testlinker` output by
`from_url,to_url` and creates:

```text
tech_testlinker
```

## Useful Options

```text
--top-k                 Number of model-ranked invocations to select.
--checkpoint            Checkpoint name under shared-workspace testlinker-finetuned-checkpoints/codet5-base.
--checkpoint-directory  Explicit directory containing pytorch_model.bin.
--model-name-or-path    Explicit pretrained CodeT5 base model/tokenizer directory or model id.
--tokenizer-mode        original, auto, or fallback. Default: original.
--include-labels        Include optional ground-truth labels in input/output CSVs.
--order-production-method
                        candidate or testlinker. Default: candidate.
--order-production-directory
                        Directory containing <project>_detail.json files when
                        using testlinker order. Default:
                        testlinker/code/result/TestLink.
--no-cuda               Force CPU inference.
--replace               Re-run stages even when output files already exist.
--project-directory     Project root (ME_PROJECT_DIRECTORY). Used to locate
                        data/ground-truth/<project>.csv (when --include-labels)
                        and data/testlinker/class-mapping/ (copied into
                        testlinker class_map/ during preprocess).
--method-resolver       testlinker, testlinkerv2, or all. Default: testlinker.
```
