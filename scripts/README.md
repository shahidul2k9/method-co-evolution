# Data Collection scripts

Helper scripts for building Java artifacts, running collection jobs locally or on Slurm, and maintaining experiment datasets. Unless noted otherwise, run commands from the repository root.

ReadMe Index:

- [`mhc method-scan`](#mhc-method-scan)
- [`mhc class-scan`](#mhc-class-scan)
- [`mhc method-callgraph`](#mhc-method-callgraph)
- [`mhc method-code`](#mhc-method-code)
- [`mhc artifact-update`](#mhc-artifact-update)
- [`mhc method-history`](#mhc-method-history)
- [`mhc method-complexity`](#mhc-method-complexity)
- [`mhc test-smell`](#mhc-test-smell)
- [`ptc-testlinker testlinker`](#ptc-testlinker-testlinker)

## Jar Dependency
The parser-backed collection commands require the Java parser executable JAR. Build the Java parser and copy the executable JAR into `WORKSPACE_DIRECTORY/jar/` before running data collection:

```bash
scripts/build-method-parser.sh
```

For the jNose test-smell workflow, also build `jnose-core` and `jnose-adapter`; see [jnose-adapter/README.md](../jnose-adapter/README.md).

## MHC Command

The full batch command and option list is maintained in [`scripts/job.sh`](job.sh); run `scripts/job.sh --help` to inspect it. For direct local runs, most `mhc` commands follow this shape:

```bash
mhc <command> \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

Common prerequisites:

- `.env` is configured with `ME_PROJECT_DIRECTORY`, `ME_WORKSPACE_DIRECTORY`, and `ME_EXPERIMENT_NAME`.
- The Python environment is installed and active.
- `WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/project.csv` exists and contains the target project metadata.
- `WORKSPACE_DIRECTORY/jar/` contains the parser JAR from `scripts/build-method-parser.sh`.
- jNose, TestLinker, and LLM commands require their extra backend setup.


### MHC Option Reference

| Option | Example | Explanation | Supported command names |
|--------|---------|-------------|-------------------------|
| `--command` | `--command method-scan` | Select the command for `scripts/job.sh` batch execution. | `scripts/job.sh` |
| `--workspace-directory` | `--workspace-directory "$ME_WORKSPACE_DIRECTORY"` | Shared workspace root containing experiment data. | All `mhc` commands |
| `--experiment-name` | `--experiment-name "$ME_EXPERIMENT_NAME"` | Experiment folder under `workspace/experiment/`. | All `mhc` commands |
| `--repository-directory` | `--repository-directory "$TMPDIR/repository"` | Checkout/cache location for repositories during collection. | Repository-backed `mhc` commands, especially Slurm runs |
| `--jar-directory` | `--jar-directory "$ME_WORKSPACE_DIRECTORY/jar"` | Directory containing Java parser, history-tool, and adapter JARs. | `method-scan`, `class-scan`, `method-callgraph`, `method-complexity`, `test-smell`; optional for Java-backed commands |
| `--history-directory` | `--history-directory /scratch/history` | Optional external root for method history outputs. | `method-history`; commands that consume external history when configured |
| `--project` | `--project "checkstyle"` | Run one project by name. | All project-scoped commands |
| `--projects` | `--projects "checkstyle,commons-io"` | Run a comma-separated project list. | Batch and wrapper usage for project-scoped commands |
| `--project-index` | `--project-index "10:20"` | Select projects by index or slice from `project.csv`. | Batch and wrapper usage for project-scoped commands |
| `--shards` | `--shards 10` | Split supported commands into per-project shards. | `method-history`, `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--shard` | `--shard 2` | Select the shard number for a sharded direct run. | `method-history`, `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--merge-only` | `--merge-only` | Merge existing shard/cache outputs without collecting new rows. | `method-history`, `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--tool-name` | `--tool-name methodParser` | Select the tool backend. | Required by `method-history`, `method-callgraph`, `method-complexity`, `test-smell` |
| `--java-options` | `--java-options "-Xmx4g"` | Extra JVM arguments for Java-backed commands. | `method-history`, `method-scan`, `class-scan`, `method-callgraph`, `method-complexity`, `test-smell` |
| `--timeout-seconds` | `--timeout-seconds 1800` | Per-task timeout, most often for method history. | Primarily `method-history`; accepted by batch wrapper for `mhc` commands |
| `--merge-threshold` | `--merge-threshold 10000` | Flush/merge threshold for history JSON or scan/cache rows. | `method-history`, `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--merge-interval-seconds` | `--merge-interval-seconds 900` | Time-triggered cache flush interval. | `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--max-cache-size` | `--max-cache-size 256` | In-memory cache budget in MB. | `method-callgraph` |
| `--max-workers` | `--max-workers 4` | Worker thread count for supported commands. | `method-history`, `method-scan`, `class-scan`, `method-code`, `method-callgraph`, `artifact-update`, `test-smell` |
| `--retry-errors` | `--retry-errors false` | Retry or skip rows previously marked with `__error_marker__`. | `method-scan`, `class-scan`, `method-code`, `method-callgraph` |
| `--enable-symbol-solver` | `--enable-symbol-solver true` | Enable JavaParser symbol resolution during method scanning. | `method-scan` |
| `--cache-evict-interval-seconds` | `--cache-evict-interval-seconds 300` | Evict JavaParser caches by elapsed time. | `method-scan` |
| `--cache-evict-interval-files` | `--cache-evict-interval-files 500` | Evict JavaParser caches by completed file count. | `method-scan` |
| `--init-reset-interval-files` | `--init-reset-interval-files 2000` | Reinitialize scanner after a number of completed files. | `method-scan`, `method-callgraph` |
| `--artifact-config-path` | `--artifact-config-path config/artifact-detection` | Artifact detection YAML file or directory. | `method-scan`, `class-scan`, `artifact-update`; useful before downstream commands |
| `--command-options` | `--command-options "--replace"` | Extra arguments forwarded through `scripts/job.sh` to the selected command. | Batch wrapper for all forwarded `mhc` commands |
| `--replace` | `--replace` | Regenerate output even if it already exists. | Commands that write per-project outputs, including scan/code/callgraph/history workflows |
| `--stage` | `--stage all` | Select staged workflow phase. | `test-smell` (`preprocess`, `execute`, `postprocess`, `all`) |
| `--strategies` | `--strategies nc,ncc` | Run strategy-aware test smell processing from `t2p-link/<strategy>/`. | `test-smell` |
| `--api-type` | `--api-type huggingface` | Select the LLM provider. | `llm-m2m-link` through `scripts/job.sh` |
| `--model-name-or-path` | `--model-name-or-path Qwen/Qwen2.5-0.5B-Instruct` | Hugging Face model ID, OpenAI model name, or local model path. | `llm-m2m-link` through `scripts/job.sh` |
| `--short-model-name` | `--short-model-name qwen_0.5b` | Short output directory name for model results. | `llm-m2m-link` through `scripts/job.sh` |
| `--prompt-format` | `--prompt-format text` | Prompt serialization format. | `llm-m2m-link` through `scripts/job.sh` |
| `--batch-size` | `--batch-size 4` | Grouped case batch size for LLM inference. | `llm-m2m-link` through `scripts/job.sh` |
| `--max-new-tokens` | `--max-new-tokens 256` | Generation cap per grouped case. | `llm-m2m-link` through `scripts/job.sh` |
| `--resume` | `--resume error` | Resume mode for existing LLM outputs. | `llm-m2m-link` through `scripts/job.sh` |
| `--input-kind` | `--input-kind t2p` | LLM input direction. | `llm-m2m-link` through `scripts/job.sh` |
| `--job-index-shift` | `--job-index-shift 1000` | Offset added to `SLURM_ARRAY_TASK_ID` before deriving project/shard indexes. | `scripts/job.sh` |
| `--top-k` | `--top-k 1` | Number of top TestLinker invocations to keep. | `testlinker` through `scripts/job.sh` |

Use [`scripts/job.sh`](job.sh) for Slurm arrays, project-index expansion, and batch-only options.

### `mhc method-scan`

Extracts `method/<project>.csv`. Prerequisites: parser JAR and `project.csv`. Wrapper alternative: [`scripts/method-scan.sh`](method-scan.sh).

```bash
mhc method-scan \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

### `mhc class-scan`

Extracts `class/<project>.csv`. Prerequisites: parser JAR and `project.csv`. Wrapper alternative: [`scripts/class-scan.sh`](class-scan.sh).

```bash
mhc class-scan \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

### `mhc method-callgraph`

Writes `callgraph/` and `fanin/`. Prerequisites: `method/`, `class/`, and parser JAR. Wrapper alternative: [`scripts/method-callgraph.sh`](method-callgraph.sh).

```bash
mhc method-callgraph \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --tool-name methodParser \
  --project "checkstyle"
```

### `mhc method-code`

Writes `method-code/<project>.csv`. Prerequisite: `method/`. Wrapper alternative: [`scripts/method-code.sh`](method-code.sh).

```bash
mhc method-code \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

### `mhc artifact-update`

Refreshes artifact metadata in existing `method/` and/or `class/` outputs. Prerequisite: existing method or class scan output. Wrapper alternative: [`scripts/artifact-update.sh`](artifact-update.sh).

```bash
mhc artifact-update \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

### `mhc method-history`

Writes method history outputs. Prerequisite: `method/`. Slurm wrapper alternative: [`scripts/job.sh`](job.sh) with `--command method-history`.

```bash
mhc method-history \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --tool-name historyFinder \
  --project "checkstyle"
```

### `mhc method-complexity`

Writes method complexity outputs. Prerequisites: parser JAR and `method/`. Slurm wrapper alternative: [`scripts/job.sh`](job.sh) with `--command method-complexity`.

```bash
mhc method-complexity \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --tool-name complexityAnalyzer \
  --project "checkstyle"
```

### `mhc test-smell`

Writes `test-smell/`. Prerequisites: jNose adapter, `method/`, `callgraph/`, and optionally `t2p-link/` for strategy-aware runs. Wrapper alternative: [`scripts/test-smell.sh`](test-smell.sh).

```bash
mhc test-smell \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --tool-name jnose \
  --stage all \
  --project "checkstyle"
```

### `ptc-testlinker testlinker`

Writes neural mapping outputs. Prerequisites: `t2p-candidate-filtered/`, `method-code/`, and TestLinker model assets. Wrapper alternative: [`scripts/testlinker.sh`](testlinker.sh).

```bash
ptc-testlinker testlinker \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --stage all \
  --project "checkstyle"
```


It reads `ME_WORKSPACE_DIRECTORY` from `.env` and uses `ME_EXPERIMENT_NAME`, defaulting to `main`.

## `SLURM Job Command`

Slurm `sbatch` wrapper for `mhc`, `ptc-llm`, and `ptc-testlinker` commands. It loads cluster modules, activates `.venv`, resolves Slurm array task IDs into projects and shards, and forwards normalized arguments to the correct CLI.

```bash
sbatch --array=1-2 scripts/job.sh \
  --command method-scan \
  --projects "checkstyle,commons-io" \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

Supported commands:

```text
method-history
method-callgraph
method-scan
class-scan
method-code
artifact-update
method-complexity
llm-m2m-link
testlinker
test-smell
```



Without `--project` or `--projects`, an array task can derive `--project-index` from `SLURM_ARRAY_TASK_ID`.

### Project-Array Mode

One Slurm array task per project:

```bash
sbatch --array=1-2 scripts/job.sh \
  --command method-scan \
  --projects "checkstyle,commons-io" \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

Array index `1` maps to the first project in the list.

### Shard Mode

One Slurm array task per `(project_index, shard)` pair. Use a zero-based array where the upper bound is `project_count * shards - 1`.

```bash
sbatch --array=0-99 scripts/job.sh \
  --command method-history \
  --tool-name historyFinder \
  --shards 10 \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

The flattened task index maps as:

```text
project_index = SLURM_ARRAY_TASK_ID / shards
shard = SLURM_ARRAY_TASK_ID % shards + 1
```

When `--job-index-shift N` is passed, `job.sh` adds `N` before calculating project and shard. This supports clusters where array indexes must stay within a limited range.

After sharded scan/code/callgraph jobs finish, run the same command with `--merge-only` and matching project selection to finalize outputs.

### LLM Example

```bash
sbatch --array=1-2 scripts/job.sh \
  --command llm-m2m-link \
  --stage execute \
  --api-type huggingface \
  --model-name-or-path "Qwen/Qwen2.5-0.5B-Instruct" \
  --short-model-name qwen_0.5b \
  --batch-size 4 \
  --input-kind t2p \
  --projects "checkstyle,commons-io" \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

### TestLinker Example

```bash
sbatch --array=1-2 scripts/job.sh \
  --command testlinker \
  --stage all \
  --projects "checkstyle,commons-io" \
  --top-k 1 \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

### Test-Smell Example

```bash
sbatch --array=1-2 scripts/job.sh \
  --command test-smell \
  --tool-name jnose \
  --stage all \
  --strategies nc,ncc \
  --projects "commons-io,checkstyle" \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

Omit `--strategies` to run the callgraph-based jNose workflow.

## `ptc-sbatch`

`ptc-sbatch` is installed by the `co-evolution` package. It rewrites large or sparse `sbatch` array commands into valid task ranges, optionally skipping projects whose expected outputs already exist.

Inline command:

```bash
ptc-sbatch sbatch --array=0-999 scripts/job.sh \
  --command method-history \
  --tool-name historyFinder \
  --shards 10 \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME"
```

Command file:

```bash
ptc-sbatch workspace/cmd.txt
ptc-sbatch workspace/cmd.txt --replace
```

It prints project indexes included, requested indexes not included, converted task indexes, any truncated ranges, and the final shell-safe `sbatch` command.


## `Web UI`
Oracle Labelling with Web UI

`http://127.0.0.1:8765`.

```bash
scripts/history-viewer.sh
```