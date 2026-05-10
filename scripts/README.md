# scripts

Helper scripts for building, distributed execution, and dataset maintenance.

---

## `build-method-parser.sh`

Builds the `method-parser` Maven module and copies the resulting fat JAR into the cache.

```bash
scripts/build-method-parser.sh
```

Reads `ME_WORKSPACE_DIRECTORY` from `.env` (defaults to `eval`). Copies the JAR to `<cache>/jar/`.

---

## `job.sh`

Slurm `sbatch` wrapper for all `mhc`, `ptc-llm`, and `ptc-testlinker` commands. Loads the required environment modules (StdEnv, scipy-stack, arrow, cuda, java/21) and activates the project virtualenv automatically.

### Usage

```
job.sh --command <cmd> [options]
```

`--command` must be one of: `method-history`, `method-callgraph`, `method-scan`, `class-scan`, `method-code`, `complexity-analyzer`, `llm-m2m-link`, `testlinker`.

### Project selection

Use one project selector for normal project-scoped runs:

| Flag | Example |
|------|---------|
| `--project` | `"checkstyle"` |
| `--projects` | `"checkstyle,commons-io"` |
| `--project-index` | `"10:20"` |
| `--project-index` | `"-1"` |

In `method-history`, `method-scan`, `class-scan`, `method-code`, or `method-callgraph` shard mode (`--shards > 1`), omit `--project-index`; `job.sh` derives it from the Slurm array task id. `--project` and `--projects` are optional filters and are forwarded to `mhc`.

On clusters where Slurm array indexes must stay within `0-9999`, pass `--job-index-shift N` when the submitted array has been shifted down. `job.sh` adds this offset back before deriving the project index and shard. The `ptc-sbatch` helper emits this option automatically only when the submitted array must be shifted, and truncates oversized project/task ranges to the largest prefix that fits. It prints the project indexes included in the final command, requested project indexes not included, converted task indexes, truncated ranges, and final sbatch command.

When redirecting `ptc-sbatch` output, the command is written as a shell-safe multiline command with `\` continuations, so the generated file can be reviewed with `cat` or submitted with `bash workspace/cmd.txt`.

### Execution modes

**Project-array mode** — one Slurm array task per project:

```bash
sbatch --array=1-2 scripts/job.sh \
    --command method-scan \
    --projects "checkstyle,commons-io"
```

Each array task index maps to the corresponding project in the list.

**Shard mode** — one Slurm array task per `(project_index, shard)` pair. Use a zero-based Slurm array where the upper bound is `project_count * shards - 1`:

```bash
sbatch --array=0-99 scripts/job.sh \
    --command method-history \
    --tool-name codeShovel \
    --shards 10
```

For callgraph sharding, use `--command method-callgraph --tool-name methodParser --shards N`; after shard jobs finish, run `method-callgraph --merge-only` with the same project selection to write the final `callgraph` and `fanin` CSVs.
For method-scan sharding, use `--command method-scan --shards N`; after shard jobs finish, run `method-scan --merge-only` with the same project selection to write the final method CSVs.
For class-scan sharding, use `--command class-scan --shards N`; after shard jobs finish, run `class-scan --merge-only` with the same project selection to write the final class CSVs.
For method-code sharding, use `--command method-code --shards N`; after shard jobs finish, run `method-code --merge-only` with the same project selection to write the final method-code CSVs.

By default, scan/cache commands retry files or methods that previously produced `__error_marker__` rows. Pass `--retry-errors false` to `method-scan`, `class-scan`, `method-code`, or `method-callgraph` jobs when you want those prior errors to be treated as already attempted and skipped.

For `method-scan`, `class-scan`, `method-code`, and `method-callgraph`, cache rows are flushed when either `--merge-threshold` pending rows accumulate or `--merge-interval-seconds` elapses. `--merge-threshold 0` or `--merge-threshold -1` disables only threshold-triggered intermediate flushing for these commands; final flushing/finalization still runs.

The job index is treated as a flattened project/shard coordinate:

```text
project_index = SLURM_ARRAY_TASK_ID / shards
shard = SLURM_ARRAY_TASK_ID % shards + 1
```

When `--job-index-shift N` is present, replace `SLURM_ARRAY_TASK_ID` in that formula with `SLURM_ARRAY_TASK_ID + N`.

For 10 projects and 10 shards per project, use `--array=0-99`:

| `SLURM_ARRAY_TASK_ID` | Forwarded project index | Forwarded shard |
|-----------------------|-------------------------|-----------------|
| `0` | `0` | `1` |
| `9` | `0` | `10` |
| `10` | `1` | `1` |
| `99` | `9` | `10` |

Optional filters are forwarded. With `--projects "checkstyle,commons-io"`, the derived project index is applied within that list. With `--project "checkstyle"`, only project index `0` is valid, so use an array range such as `--array=0-9` for `--shards 10`.

Do not pass `--project-index` in shard mode; it is computed from the Slurm array task id.

### `llm-m2m-link` example

```bash
sbatch --array=1-2 scripts/job.sh \
    --command llm-m2m-link \
    --api-type huggingface \
    --model-name-or-path "Qwen/Qwen2.5-0.5B-Instruct" \
    --short-model-name qwen_0.5b \
    --batch-size 4 \
    --input-kind t2p \
    --projects "checkstyle,commons-io"
```

### `testlinker` example

```bash
sbatch --array=1-2 scripts/job.sh \
    --command testlinker \
    --stage all \
    --projects "checkstyle,commons-io" \
    --top-k 1
```

### All options

| Flag | Default | Description |
|------|---------|-------------|
| `--command` | required | Command to run |
| `--tool-name` | — | Tool name for `method-history`, `method-callgraph`, `complexity-analyzer` |
| `--java-options` | — | Extra JVM flags (e.g. `"-Xmx4g"`) |
| `--timeout-seconds` | `1800` | Per-method history timeout |
| `--merge-threshold` | `10000` | History JSON merge threshold; for scan/code commands, pending cache rows before an intermediate flush, with `0` or `-1` disabling the threshold trigger |
| `--merge-interval-seconds` | `900` | Time trigger for intermediate cache flushes in `method-scan`, `class-scan`, `method-code`, and `method-callgraph`; `0` disables the time trigger |
| `--merge-only` | off | Merge without running history tools |
| `--retry-errors` | `true` | Retry previous `__error_marker__` rows for `method-scan`, `class-scan`, `method-code`, and `method-callgraph`; set to `false` to skip them |
| `--stage` | `execute` | LLM or TestLinker stage |
| `--api-type` | `auto` | LLM provider: `auto`, `huggingface`, `openai-responses` |
| `--model-name-or-path` | — | HuggingFace model id or path |
| `--short-model-name` | derived | Short name used in output paths |
| `--prompt-format` | `auto` | LLM prompt format: `auto`, `json`, `text` |
| `--batch-size` | `4` | LLM batch size |
| `--max-new-tokens` | `256` | LLM token generation cap |
| `--resume` | `none` | Resume mode: `none`, `all`, `error` |
| `--input-kind` | `t2p` | LLM input direction: `t2p` or `p2t` |
| `--shards` | `1` | Total shard count per project |
| `--job-index-shift` | `0` | Offset added to `SLURM_ARRAY_TASK_ID` before project/shard derivation |
| `--top-k` | `1` | TestLinker top-k invocations |
| `--workspace-directory` | `workspace` | Cache root |
| `--history-directory` | `ME_HISTORY_DIRECTORY` or `$HOME/scratch/$USER/method-co-evolution/.cache` | Method history JSON/archive root |
| `--data-directory` | `<cache>/data` | Data output root |

---

## `update_oracle_method_metadata.py`

Backfills method metadata (`url`, `startLine`, `endLine`, `startCommitHash`) into oracle JSON files by matching against the method CSV index.

```bash
python scripts/update_oracle_method_metadata.py \
    --oracle-dir path/to/oracle \
    --method-dir workspace/data/method \
    --log-file update.log

# Dry run — report changes without writing files
python scripts/update_oracle_method_metadata.py \
    --oracle-dir path/to/oracle \
    --method-dir workspace/data/method \
    --dry-run
```

Matching strategy: exact `(file, element_name)` first; falls back to `element_name` only if no exact match. Ambiguous matches (multiple candidates) are skipped and logged. Also renames JSON files to the canonical `{number}-{repo}-{java-file}-{method}.json` format when metadata changes.
