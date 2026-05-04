# scripts

Helper scripts for building, distributed execution, and dataset maintenance.

---

## `build-method-parser.sh`

Builds the `method-parser` Maven module and copies the resulting fat JAR into the cache.

```bash
scripts/build-method-parser.sh
```

Reads `ME_CACHE_DIRECTORY` from `.env` (defaults to `.white`). Copies the JAR to `<cache>/jar/`.

---

## `job.sh`

Slurm `sbatch` wrapper for all `mhc`, `ptc-llm`, and `ptc-testlinker` commands. Loads the required environment modules (StdEnv, scipy-stack, arrow, cuda, java/21) and activates the project virtualenv automatically.

### Usage

```
job.sh --command <cmd> [options]
```

`--command` must be one of: `history`, `method-callgraph`, `method-scan`, `class-scan`, `method-code`, `complexity-analyzer`, `llm-m2m-link`, `testlinker`.

### Project selection

Use exactly one of:

| Flag | Example |
|------|---------|
| `--projects` | `"checkstyle,commons-io"` |
| `--project-range` | `"10:20"` |

### Execution modes

**Project-array mode** — one Slurm array task per project:

```bash
sbatch --array=1-2 scripts/job.sh \
    --command method-scan \
    --projects "checkstyle,commons-io"
```

Each array task index maps to the corresponding project in the list.

**Shard mode** — one Slurm array task per history shard:

```bash
sbatch --array=1-20 scripts/job.sh \
    --command history \
    --tool-name codeShovel \
    --projects "checkstyle" \
    --shards 20
```

Array task index maps directly to `--shard $SLURM_ARRAY_TASK_ID`.

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
| `--tool-name` | — | Tool name for `history`, `method-callgraph`, `complexity-analyzer` |
| `--java-options` | — | Extra JVM flags (e.g. `"-Xmx4g"`) |
| `--timeout-seconds` | `1800` | Per-method history timeout |
| `--merge-threshold` | `10000` | History JSON merge threshold |
| `--merge-only` | off | Merge without running history tools |
| `--stage` | `execute` | LLM or TestLinker stage |
| `--api-type` | `auto` | LLM provider: `auto`, `huggingface`, `openai-responses` |
| `--model-name-or-path` | — | HuggingFace model id or path |
| `--short-model-name` | derived | Short name used in output paths |
| `--prompt-format` | `auto` | LLM prompt format: `auto`, `json`, `text` |
| `--batch-size` | `4` | LLM batch size |
| `--max-new-tokens` | `256` | LLM token generation cap |
| `--resume` | `none` | Resume mode: `none`, `all`, `error` |
| `--input-kind` | `t2p` | LLM input direction: `t2p` or `p2t` |
| `--shards` | `1` | Total shard count |
| `--top-k` | `1` | TestLinker top-k invocations |
| `--cache-directory` | `.cache` | Cache root |
| `--history-directory` | `ME_HISTORY_DIRECTORY` or `$HOME/scratch/$USER/method-co-evolution/.cache` | Method history JSON/archive root |
| `--data-directory` | `<cache>/data` | Data output root |

---

## `update_oracle_method_metadata.py`

Backfills method metadata (`url`, `startLine`, `endLine`, `startCommitHash`) into oracle JSON files by matching against the method CSV index.

```bash
python scripts/update_oracle_method_metadata.py \
    --oracle-dir path/to/oracle \
    --method-dir .cache/data/method \
    --log-file update.log

# Dry run — report changes without writing files
python scripts/update_oracle_method_metadata.py \
    --oracle-dir path/to/oracle \
    --method-dir .cache/data/method \
    --dry-run
```

Matching strategy: exact `(file, element_name)` first; falls back to `element_name` only if no exact match. Ambiguous matches (multiple candidates) are skipped and logged. Also renames JSON files to the canonical `{number}-{repo}-{java-file}-{method}.json` format when metadata changes.
