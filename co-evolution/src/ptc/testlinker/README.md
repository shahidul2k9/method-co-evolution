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
without an error. When labels are included, `input/project-csv/<project>.csv`
contains `label_json` and a binary per-candidate `label`, and the final output
CSV places `label` immediately before `label_pred`. The binary `label` is set
by matching each candidate row's `to_url` against the ground-truth `to_url` for
the same `from_url`.

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

If every `pred_score` is almost identical, first suspect tokenizer loading. A
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
  --top-k 1 \
  --testlinker-directory "$WORKSPACE_DIRECTORY/experiment/$ME_EXPERIMENT_NAME/testlinker"
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

```bash
# heuristics only (default)
ptc-testlinker testlinker \
  --stage postprocess \
  --workspace-directory .cache \
  --project commons-io

# both outputs
ptc-testlinker testlinker \
  --stage postprocess \
  --workspace-directory .cache \
  --project commons-io \
  --postprocess-modes testlinker-original testlinker-symbolsolver
```

## Stage Outputs

`preprocess` reads project CSVs and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/input/model-csv-input/<project>.csv
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/input/model-input-json/<project>/<test-id>.json
```

This CSV has one row per invocation/signature candidate. Rows with the same
`test_id` belong to the same test method and are grouped internally only when
building temporary TestLinker JSON.

`execute` reads the JSON files, runs the model/ranker, and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/model-output-json/<project>.json
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/model-output-csv/<project>.csv
```

`postprocess` writes one output file per selected mode under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/testlinker/output/<mode>/<project>.csv
```

Default mode is `testlinker-original`. Pass `--postprocess-modes` to select
one or both modes:

```bash
# default — heuristics only
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io

# symbol-solver only
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io \
  --postprocess-modes testlinker-symbolsolver

# both outputs
ptc-testlinker testlinker --stage postprocess --workspace-directory .cache --project commons-io \
  --postprocess-modes testlinker-original testlinker-symbolsolver
```

**`testlinker-original`** output columns:

```text
project,from_name,to_name,label,label_pred,pred_score,recom_by,testlinker_signature,from_url,to_url
```

`label_pred` is the 0/1 TestLinker model/rule recommendation. `pred_score` is
the raw CodeT5 class-1 score; blank when a rule-based shortcut was used.

**`testlinker-symbolsolver`** output columns:

```text
project,from_name,to_name,label,testlinker_symbolsolver,from_url,to_url
```

`testlinker_symbolsolver` is 1 when the `testlinker_signature` recommendation
resolves to `to_url` according to our JavaParser symbol-solver method index
(`data/method/<project>.csv`).

`generate_t2p_tech.py` merges the `testlinker-original` output by
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
--only-model            Skip TestLinker's rule-based shortcut.
--no-cuda               Force CPU inference.
--replace               Re-run stages even when output files already exist.
--project-directory     Project root (ME_PROJECT_DIRECTORY). Used to locate
                        data/ground-truth/<project>.csv (when --include-labels)
                        and data/testlinker/class-mapping/ (copied into
                        testlinker class_map/ during preprocess).
--mapping-mode          testlinker-original (default) or testlinker-symbolsolver.
                        Controls how recommendations are derived in the execute step.
                        testlinker-original: model/heuristic ranks invocations and
                        selects from mapped candidates. testlinker-symbolsolver: uses
                        apply_signature_mapping detail_sigs directly, skipping the
                        ranker (recom_by=symbolsolver). Mapping files are always
                        generated from data/class and data/method CSVs.
--postprocess-modes     Space-separated list of postprocess outputs to write.
                        Choices: testlinker-original testlinker-symbolsolver.
                        Default: testlinker-original.
```

For local smoke tests without loading CodeT5:

```bash
ptc-testlinker testlinker \
  --stage all \
  --workspace-directory .cache \
  --project commons-io \
  --model-mode heuristic
```

To use the JavaParser symbol-solver mapping directly as recommendations (no model ranking):

```bash
ptc-testlinker testlinker \
  --stage all \
  --workspace-directory .cache \
  --project commons-io \
  --mapping-mode testlinker-symbolsolver \
  --postprocess-modes testlinker-symbolsolver
```

`--model-mode` and `--mapping-mode` are independent:

| | `testlinker-original` mapping | `testlinker-symbolsolver` mapping |
|---|---|---|
| `codet5` model | CodeT5 ranks invocations; mapping provides candidates | detail_sigs from symbol-solver used directly; `recom_by=symbolsolver` |
| `heuristic` model | position-based ranking; mapping provides candidates | detail_sigs from symbol-solver used directly; `recom_by=symbolsolver` |

Use `--model-mode heuristic` only for debugging; real evaluated runs should use `codet5`.
