# scripts

Helper scripts for building Java artifacts, running collection jobs locally or on Slurm, and maintaining experiment datasets. Unless noted otherwise, run commands from the repository root.

The scripts expect the same environment used by the Python packages:

```bash
ME_PROJECT_DIRECTORY=/path/to/method-co-evolution
ME_WORKSPACE_DIRECTORY=/path/to/method-co-evolution/workspace
ME_EXPERIMENT_NAME=main
GITHUB_API_KEY=ghp_...
```

Most outputs live under:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/
```

Shared Java artifacts live under:

```text
WORKSPACE_DIRECTORY/jar/
```

## `build-method-parser.sh`

Builds the `method-parser` Maven module and copies the parser JAR into `WORKSPACE_DIRECTORY/jar/`.

```bash
scripts/build-method-parser.sh
```

It reads `ME_WORKSPACE_DIRECTORY` from `.env`. Build this JAR before running parser-backed `mhc` commands such as `method-scan`, `class-scan`, `method-callgraph`, or `method-complexity`.

## Local Wrapper Scripts

These thin wrappers call `mhc` with project defaults from `.env`:

| Script | MHC command |
|--------|-------------|
| `method-scan.sh` | `mhc method-scan` |
| `class-scan.sh` | `mhc class-scan` |
| `method-callgraph.sh` | `mhc method-callgraph` |
| `method-code.sh` | `mhc method-code` |
| `artifact-update.sh` | `mhc artifact-update` |
| `test-smell.sh` | `mhc test-smell` |
| `testlinker.sh` | `ptc-testlinker testlinker` |

Use the underlying CLI directly when you need full control over project selection, sharding, or paths.

## `job.sh`

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

### Project Selection

Use one normal project selector:

| Flag | Example |
|------|---------|
| `--project` | `checkstyle` |
| `--projects` | `checkstyle,commons-io` |
| `--project-index` | `10:20` |
| `--project-index` | `-1` |

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

### Important Options

| Flag | Default | Description |
|------|---------|-------------|
| `--command` | required | Command to run |
| `--workspace-directory` | `$PROJECT_DIRECTORY/workspace` | Shared workspace root |
| `--experiment-name` | `ME_EXPERIMENT_NAME` or `main` | Experiment name |
| `--history-directory` | unset | Optional method-history root override |
| `--tool-name` | command-dependent | Tool name for history, parser, complexity, or test-smell commands |
| `--java-options` | unset | Extra JVM flags |
| `--timeout-seconds` | `1800` | Per-method history timeout |
| `--merge-threshold` | `10000` | History merge or scan/cache flush threshold |
| `--merge-interval-seconds` | `900` | Scan/code/callgraph time-triggered flush interval |
| `--merge-only` | off | Merge/finalize existing shard output |
| `--retry-errors` | `true` | Retry previous `__error_marker__` rows |
| `--artifact-config-path` | unset | Artifact detection YAML file or directory |
| `--stage` | command-dependent | LLM, TestLinker, or test-smell stage |
| `--api-type` | `auto` | LLM provider |
| `--model-name-or-path` | unset | Hugging Face, OpenAI, or local model ID/path |
| `--short-model-name` | derived | Short output directory name |
| `--prompt-format` | `auto` | LLM prompt format |
| `--batch-size` | `4` | LLM grouped case batch size |
| `--max-new-tokens` | `256` | LLM generation cap |
| `--resume` | `none` | LLM resume mode |
| `--input-kind` | `t2p` | LLM input direction |
| `--shards` | `1` | Total shards per project |
| `--job-index-shift` | `0` | Offset for shifted Slurm array indexes |
| `--top-k` | `1` | TestLinker top-k invocations |
| `--strategies` | unset | Comma-separated t2p-link strategies for test-smell |

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

## `update_oracle_method_metadata.py`

Backfills method metadata into oracle JSON files by matching them against a method CSV index.

```bash
python scripts/update_oracle_method_metadata.py \
  --oracle-dir path/to/oracle \
  --method-dir "$ME_WORKSPACE_DIRECTORY/experiment/$ME_EXPERIMENT_NAME/method" \
  --log-file update.log
```

Dry run:

```bash
python scripts/update_oracle_method_metadata.py \
  --oracle-dir path/to/oracle \
  --method-dir "$ME_WORKSPACE_DIRECTORY/experiment/$ME_EXPERIMENT_NAME/method" \
  --dry-run
```

Matching uses exact `(file, element_name)` first and falls back to `element_name` only if no exact match exists. Ambiguous matches are skipped and logged. When metadata changes, JSON files are renamed to the canonical `{number}-{repo}-{java-file}-{method}.json` format.
