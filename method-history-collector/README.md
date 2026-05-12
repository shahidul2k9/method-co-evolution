# method-history-collector

Python package exposing the `mhc` CLI. Collects method indexes, change histories, call graphs, complexity metrics, and source code snippets for Java repositories.

## Install

```bash
pip install -e ./method-history-collector
```

## Common flags

All subcommands accept:

```
--workspace-directory       Root cache directory (default: .cache)
--history-directory     Method history JSON/archive root (default: ME_HISTORY_DIRECTORY or <cache>/history)
--repository-directory  Where repositories are cloned
--data-directory        Where output CSVs are written (default: <cache>/data)
--jar-directory         Directory containing the method-parser JAR
```

### Project selection

Provide one of the following selectors. `--project-index` may also be combined with `--project` or `--projects` to index within that explicit project set; this is useful when `scripts/job.sh` derives a project index for sharded array jobs.

| Flag | Example | Effect |
|------|---------|--------|
| `--project` | `checkstyle` | Single project |
| `--projects` | `checkstyle,commons-io` | Explicit comma-separated list |
| `--project-index` | `10:20` | Python-style 0-based row slice from `repository.csv` (`10` through `19`) |
| `--project-index` | `-1` | Last project |
| `--project-index` | `:` | All projects |

### Error retry behavior

`method-scan`, `class-scan`, `method-code`, and `method-callgraph` retry prior `__error_marker__` cache rows by default. Pass `--retry-errors false` to treat those failures as already attempted and skip them on the next run.

### Scan cache flushing

`method-scan`, `class-scan`, `method-code`, and `method-callgraph` buffer cache rows and flush them when either `--merge-threshold` pending rows accumulate or `--merge-interval-seconds` elapses. Defaults are `--merge-threshold 10000` and `--merge-interval-seconds 900`. For these scan/code commands, `--merge-threshold 0` or `--merge-threshold -1` disables only threshold-triggered intermediate flushing; final flushing and single-shard output finalization still run. Use `--merge-interval-seconds 0` to disable time-triggered intermediate flushing.

## Commands

### `mhc method-scan`

Extracts all methods and constructors from a repository at its current HEAD and writes `data/method/{project}.csv`. See [method-parser/README.md](../method-parser/README.md) for the column schema.

```bash
mhc method-scan \
    --workspace-directory "workspace" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --java-options "-Xmx2g" \
    --project "checkstyle"
```

Pass `--artifact-config-path "$ME_PROJECT_DIRECTORY/config/artifact-detection"` to use hierarchical artifact tags such as `#test-code #test-unit #test-method` and `#production-code`.

Use `--replace` to regenerate the CSV even if it already exists.

If `<workspace-directory>/config/logback.xml` exists it is passed to the JVM automatically as `-Dlogback.configurationFile=...`.

Previous `__error_marker__` cache rows are retried by default. Use `--retry-errors false` to treat those prior failures as already attempted and skip them on the next run.

Use `--merge-threshold` and `--merge-interval-seconds` to control intermediate cache flushes. The flush happens as soon as either limit is reached.

---

### `mhc artifact-update`

Updates existing `data/method/{project}.csv` and `data/class/{project}.csv` artifact columns without regenerating callgraphs.

```bash
mhc artifact-update \
    --workspace-directory "workspace" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --artifact-config-path "$ME_PROJECT_DIRECTORY/config/artifact-detection" \
    --project "jgit" \
    --target method,class \
    --backup
```

Artifact update always uses the Java artifact detector to parse method declarations and detect `#test-method`, `#test-fixture`, and `#test-utility` roles.
With `--backup`, the previous CSV is saved beside the original as `bk_<project>.csv`.

---

### `mhc method-history`

Traces the change history of each method using a history tool (CodeShovel, HistoryFinder, or CodeTracker) and stores loose JSON files and `.tar.gz` archives under `<history-directory>/{tool}/{project}`. If `--history-directory` is omitted, MHC uses `ME_HISTORY_DIRECTORY`; if that environment variable is unset, it falls back to `<workspace-directory>/history`.

```bash
mhc method-history \
    --workspace-directory "workspace" \
    --history-directory "/scratch/method-history" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --tool-name "codeShovel" \
    --java-options "-Xmx2g" \
    --timeout-seconds 1800 \
    --merge-threshold 10000 \
    --project "checkstyle"
```

#### Sharding

Split work across parallel workers deterministically (hash-based, disjoint):

```bash
mhc method-history ... --project "checkstyle" --shards 20 --shard 7
```

#### Merging

Merge loose `.json` files into the `.tar.gz` archive without generating new history:

```bash
mhc method-history ... --project "checkstyle" --merge-only
# with cleanup:
mhc method-history ... --project "checkstyle" --merge-only delete-empty delete-tmp delete-lock
```

`delete-tmp` and `delete-lock` are safe only when no history worker is running for the same cache.

Key options:

| Flag | Default | Description |
|------|---------|-------------|
| `--tool-name` | required | `codeShovel`, `historyFinder`, or `codeTracker` |
| `--history-directory` | `ME_HISTORY_DIRECTORY` or `<cache>/history` | Root directory for method history JSON files and archives |
| `--timeout-seconds` | `1800` | Per-method timeout |
| `--merge-threshold` | `10000` | Loose JSON files before an intermediate merge; `0` disables intermediate merges; negative disables final merge too |
| `--shards` | `1` | Total shard count |
| `--shard` | `1` | Which shard to run (1-based) |
| `--merge-only` | off | Merge without running history tools |

---

### `mhc method-callgraph`

Generates callgraph (fan-out) and fanin call-graph CSVs via the method-parser JAR. See [method-parser/README.md](../method-parser/README.md) for the column schema.

```bash
mhc method-callgraph \
    --workspace-directory "workspace" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --tool-name "methodParser" \
    --project "checkstyle"
```

Use `--replace` to regenerate even if the CSV already exists.

Previous `__error_marker__` cache rows are retried by default. Use `--retry-errors false` to skip files that already failed in a prior run.

Use `--merge-threshold` and `--merge-interval-seconds` to control intermediate cache flushes. The flush happens as soon as either limit is reached.

---

### `mhc method-complexity`

Computes cyclomatic complexity for each method.

```bash
mhc method-complexity \
    --workspace-directory "workspace" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --tool-name "complexityAnalyzer" \
    --project "checkstyle"
```

---

### `mhc method-code`

Reads `data/method/{project}.csv`, checks out the repository at the indexed `hash`, and extracts the source lines for each method. Writes `data/method-code/{project}.csv`.

```bash
mhc method-code \
    --workspace-directory "workspace" \
    --repository-directory "workspace/repository" \
    --data-directory "workspace/data" \
    --jar-directory "workspace/jar" \
    --project "checkstyle"
```

Previous `__error_marker__` cache rows are retried by default. Use `--retry-errors false` to skip methods that already failed in a prior run.

Use `--merge-threshold` and `--merge-interval-seconds` to control intermediate cache flushes. The flush happens as soon as either limit is reached.

Output columns: `project`, `name`, `url`, `artifact`, `start_line`, `end_line`, `code`.
