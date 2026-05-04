# method-history-collector

Python package exposing the `mhc` CLI. Collects method indexes, change histories, call graphs, complexity metrics, and source code snippets for Java repositories.

## Install

```bash
pip install -e ./method-history-collector
```

## Common flags

All subcommands accept:

```
--cache-directory       Root cache directory (default: .cache)
--history-directory     Method history JSON/archive root (default: ME_HISTORY_DIRECTORY or <cache>/history)
--repository-directory  Where repositories are cloned
--data-directory        Where output CSVs are written (default: <cache>/data)
--jar-directory         Directory containing the method-parser JAR
```

### Project selection

Exactly one of the following must be provided:

| Flag | Example | Effect |
|------|---------|--------|
| `--project` | `checkstyle` | Single project |
| `--projects` | `checkstyle,commons-io` | Explicit comma-separated list |
| `--project-range` | `10:20` | 1-based inclusive row range from `repository.csv` |
| `--project-range` | `:` | All projects |

## Commands

### `mhc method-scan`

Extracts all methods and constructors from a repository at its current HEAD and writes `data/method/{project}.csv`. See [method-parser/README.md](../method-parser/README.md) for the column schema.

```bash
mhc method-scan \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --java-options "-Xmx2g" \
    --project "checkstyle"
```

Use `--replace` to regenerate the CSV even if it already exists.

If `<cache-directory>/config/logback.xml` exists it is passed to the JVM automatically as `-Dlogback.configurationFile=...`.

---

### `mhc history`

Traces the change history of each method using a history tool (CodeShovel, HistoryFinder, or CodeTracker) and stores loose JSON files and `.tar.gz` archives under `<history-directory>/{tool}/{project}`. If `--history-directory` is omitted, MHC uses `ME_HISTORY_DIRECTORY`; if that environment variable is unset, it falls back to `<cache-directory>/history`.

```bash
mhc history \
    --cache-directory ".cache" \
    --history-directory "/scratch/method-history" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --java-options "-Xmx2g" \
    --timeout-seconds 1800 \
    --merge-threshold 10000 \
    --project "checkstyle"
```

#### Sharding

Split work across parallel workers deterministically (hash-based, disjoint):

```bash
mhc history ... --project "checkstyle" --shards 20 --shard 7
```

#### Merging

Merge loose `.json` files into the `.tar.gz` archive without generating new history:

```bash
mhc history ... --project "checkstyle" --merge-only
# with cleanup:
mhc history ... --project "checkstyle" --merge-only delete-empty delete-tmp delete-lock
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

Generates fan-out and fan-in call-graph CSVs via the method-parser JAR. See [method-parser/README.md](../method-parser/README.md) for the column schema.

```bash
mhc method-callgraph \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "methodParser" \
    --project "checkstyle"
```

Use `--replace` to regenerate even if the CSV already exists.

---

### `mhc complexity-analyzer`

Computes cyclomatic complexity for each method.

```bash
mhc complexity-analyzer \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "complexityAnalyzer" \
    --project "checkstyle"
```

---

### `mhc method-code`

Reads `data/method/{project}.csv`, checks out the repository at the indexed `hash`, and extracts the source lines for each method. Writes `data/method-code/{project}.csv`.

```bash
mhc method-code \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --project "checkstyle"
```

Output columns: `project`, `name`, `url`, `artifact`, `start_line`, `end_line`, `code`.
