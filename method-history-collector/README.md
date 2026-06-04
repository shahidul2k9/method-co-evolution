# method-history-collector

Python package exposing the `mhc` CLI. It collects method and class indexes, call graphs, method histories, complexity metrics, method source snippets, and jNose test-smell outputs for Java repositories.

Install from the repository root:

```bash
pip install -e ./method-history-collector
```

## Paths and Defaults

`mhc` requires `--workspace-directory` and an experiment name. The experiment name is resolved from `--experiment-name` or `ME_EXPERIMENT_NAME`.

| Path | Default |
|------|---------|
| Workspace root | `--workspace-directory` or `ME_WORKSPACE_DIRECTORY` in wrapper scripts |
| Experiment directory | `WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME` |
| Repository clones | `WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/repository` |
| Data outputs | `WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/<dataset>/` |
| Method histories | `--history-directory`, else `WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/history` |
| Java JARs | `--jar-directory`, else `WORKSPACE_DIRECTORY/jar` |
| Artifact config | `--artifact-config-path`, commonly `config/artifact-detection` |

The project index is read from:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/project.csv
```

## Common Flags

| Flag | Description |
|------|-------------|
| `--workspace-directory` | Shared workspace root. Required by `mhc`. |
| `--experiment-name` | Experiment name. Defaults to `ME_EXPERIMENT_NAME`. |
| `--repository-directory` | Override clone directory. Defaults to the experiment repository directory. |
| `--history-directory` | Override method-history JSON/archive directory. |
| `--jar-directory` | Override JAR directory. Defaults to `WORKSPACE_DIRECTORY/jar`. |
| `--java-options` | JVM flags passed before `-jar`, for example `"-Xmx4g"`. |
| `--command-options` | Extra arguments forwarded to the underlying command or JAR. |
| `--artifact-config-path` | YAML file or directory for artifact role detection. |

### Project Selection

Use exactly one selector unless otherwise stated:

| Flag | Example | Effect |
|------|---------|--------|
| `--project` | `checkstyle` | Run one project |
| `--projects` | `checkstyle,commons-io` | Run an explicit comma-separated list |
| `--project-index` | `10:20` | Select rows 10 through 19 from `project.csv` |
| `--project-index` | `-1` | Select the last project |
| `--project-index` | `:` | Select all projects |

`--project-index` can be combined with `--project` or `--projects` to index within that explicit project set. This is mainly used by Slurm wrappers that derive the project index from an array task.

### Sharding and Merging

`method-history`, `method-scan`, `class-scan`, `method-code`, and `method-callgraph` support deterministic sharding:

```bash
mhc method-history ... --project "checkstyle" --shards 20 --shard 7
```

`--shards` is the total shard count and `--shard` is 1-based.

`--merge-threshold` has command-specific behavior:

| Command family | Behavior |
|----------------|----------|
| `method-history` | Loose JSON files are merged into `.tar.gz` archives when the threshold is reached. `0` disables intermediate merges; negative values also disable final merge. |
| Scan/code/callgraph commands | Pending cache rows are flushed when the threshold is reached. `0` or negative disables threshold-triggered intermediate flushes, but final output finalization still runs. |

For `method-scan`, `class-scan`, `method-code`, and `method-callgraph`, `--merge-interval-seconds` also flushes pending rows after the configured interval. Use `0` to disable time-triggered intermediate flushing.

`method-history` supports merge-only cleanup:

```bash
mhc method-history ... --project "checkstyle" --merge-only
mhc method-history ... --project "checkstyle" --merge-only delete-empty delete-tmp delete-lock
```

Use `delete-tmp` and `delete-lock` only when no worker is running against the same history directory.

### Retry Behavior

`method-scan`, `class-scan`, `method-code`, and `method-callgraph` retry previous `__error_marker__` rows by default. Pass:

```bash
--retry-errors false
```

to treat previous failures as already attempted and skip them.

## Commands

### `mhc method-scan`

Extracts all methods and constructors from the project checkout and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method/<project>.csv
```

```bash
mhc method-scan \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --artifact-config-path "config/artifact-detection" \
  --project "checkstyle"
```

Use `--replace` to regenerate existing output. If `WORKSPACE_DIRECTORY/config/logback.xml` exists, it is passed to the JVM as `-Dlogback.configurationFile=...`.

### `mhc class-scan`

Extracts class-level metadata needed by artifact detection and JavaParser fallback resolution. It writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/class/<project>.csv
```

```bash
mhc class-scan \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --artifact-config-path "config/artifact-detection" \
  --project "checkstyle"
```

Run this before `method-callgraph` when fallback resolution or TestLinker mapping files are needed.

### `mhc artifact-update`

Updates artifact role columns in existing `method/<project>.csv` and `class/<project>.csv` files without regenerating scans.

```bash
mhc artifact-update \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --artifact-config-path "config/artifact-detection" \
  --project "jgit" \
  --target method,class \
  --backup
```

`--target` accepts `method`, `class`, or both. `--backup` saves `bk_<project>.csv` beside the original. `--dry-run` previews changes without writing files.

### `mhc method-history`

Traces method histories using CodeShovel, HistoryFinder, or CodeTracker. Output is stored under:

```text
HISTORY_DIRECTORY/<tool>/<project>/
```

where `HISTORY_DIRECTORY` is `--history-directory` or the experiment `history/` directory.

```bash
mhc method-history \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --tool-name "historyFinder" \
  --java-options "-Xmx4g" \
  --timeout-seconds 1800 \
  --merge-threshold 10000 \
  --project "checkstyle"
```

Tool names are `codeShovel`, `historyFinder`, and `codeTracker`.

### `mhc method-callgraph`

Generates callgraph and fanin datasets with the `method-parser` JAR. Outputs:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/callgraph/<project>.csv
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/fanin/<project>.csv
```

```bash
mhc method-callgraph \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --tool-name "methodParser" \
  --project "checkstyle"
```

Use `--replace` to regenerate existing outputs. For sharded callgraph runs, run the same command with `--merge-only` after all shards complete to finalize shared cache rows into `callgraph/` and `fanin/`.

### `mhc method-complexity`

Computes cyclomatic complexity for methods.

```bash
mhc method-complexity \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --tool-name "complexityAnalyzer" \
  --project "checkstyle"
```

### `mhc test-smell`

Runs the jNose-based test-smell workflow. It requires the executable `jnose-adapter` JAR in `WORKSPACE_DIRECTORY/jar`; see [../jnose-adapter/README.md](../jnose-adapter/README.md).

```bash
mhc test-smell \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
  --tool-name jnose \
  --stage all \
  --project "commons-io"
```

To analyze only links from one or more t2p strategies at the linked method's introduction commit, add:

```bash
  --strategies nc,ncc
```

Stages:

| Stage | Description |
|-------|-------------|
| `preprocess` | Generate jNose input from `method/` + `callgraph/`, or from `t2p-link/<strategy>/` when `--strategies` is set |
| `execute` | Run `jnose-adapter` and write raw jNose output |
| `postprocess` | Normalize jNose smells to MHC method-level output |
| `all` | Run all stages in order |

Callgraph intermediate files live under `.test-smell/jnose/callgraph/`; final rows are written under `test-smell/jnose/callgraph/output/`.

Strategy intermediate files live under `.test-smell/jnose/<strategy>/`; downloaded adapter input files are under `adapter-input-file/`, bridge rows under `test-smell/jnose/<strategy>/t2p-link-bridge/`, and final rows under `test-smell/jnose/<strategy>/output/`.

Final rows use columns:

```text
project,name,smell,smell_detector,url,smell_begin,smell_end
```

### `mhc method-code`

Checks out the repository at each method row's indexed `hash`, extracts source lines, and writes:

```text
WORKSPACE_DIRECTORY/experiment/EXPERIMENT_NAME/method-code/<project>.csv
```

```bash
mhc method-code \
  --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
  --experiment-name "$ME_EXPERIMENT_NAME" \
  --project "checkstyle"
```

Output columns are:

```text
project,name,url,artifact,start_line,end_line,code
```
