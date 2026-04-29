# method-co-evolution

Method Co-Evolution

---

## Build and Run

### Create virtual environment

```bash
python -m venv .venv
```

### Install Dependencies

```bash
source .venv/bin/activate
pip install -e ./method-history-collector
pip install -e ./co-evolution
pip install -e ./co-evolution[llm]
```

### Compile `method-parser`

From the `method-parser` directory, run:

```bash
mvn clean install -DskipTests
```

### Run
```bash
mhc scan-method \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --java-options "-Xmx2g" \
    --project "checkstyle"
    
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --java-options "-Xmx2g" \
    --timeout-seconds 1800 \
    --merge-threshold 10000 \
    --project "checkstyle"

mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --merge-only \
    --project "checkstyle"

mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --projects "checkstyle,commons-io" \
    --shards 20 \
    --shard 7

mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --project-range "10:20"
    
mhc call-graph \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "methodParser" \
    --project "checkstyle"

mhc complexity-analyzer \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "complexityAnalyzer" \
    --project "checkstyle"

mhc method-code \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --project "checkstyle"
```

### Project Selection And History Sharding

All project-scoped `mhc` commands now support exactly one of:

- `--project "checkstyle"` for a single project
- `--projects "checkstyle,commons-io"` for an explicit list
- `--project-range "10:20"` for a 1-based inclusive range from `repository.csv`

For `mhc history`, you can additionally split method-history generation into deterministic shards:

- `--shards N` sets the total shard count
- `--shard K` selects the 1-based shard to run
- `--merge-threshold N` sets how many unarchived history JSON files are kept before intermediate merging into the `.tar.gz` archive (default: `10000`; `0` disables intermediate merging; negative values disable the final merge too)
- `--merge-only` merges existing loose history JSON files without cloning repositories or generating new history
- `--merge-only delete-empty delete-tmp delete-lock` enables optional cleanup after merging. `delete-empty` removes empty history directories, `delete-tmp` removes leftover `.tmp` files, and `delete-lock` removes the archive lock file. Use `delete-tmp` and `delete-lock` only when no history generation process is running for the same cache.

Examples:

```bash
# Unchanged single-project execution
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --project "checkstyle"

# Run shard 7 of 20 for one project
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --project "checkstyle" \
    --shards 20 \
    --shard 7

# Merge existing loose JSONs without generating new history
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --project "checkstyle" \
    --merge-only

# Merge existing loose JSONs and opt into cleanup
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --project "checkstyle" \
    --merge-only delete-empty delete-tmp delete-lock

# Run the same shard across an explicit project list
mhc history \
    --cache-directory ".cache" \
    --repository-directory ".cache/repository" \
    --data-directory ".cache/data" \
    --jar-directory ".cache/jar" \
    --tool-name "codeShovel" \
    --projects "checkstyle,commons-io" \
    --shards 20 \
    --shard 7
```

Sharding is deterministic: the method-history output path is hashed to assign each method to exactly one shard. As long as you launch distinct shard numbers for the same `--shards` value, the workers will process disjoint method sets.

History compaction into `.tar.gz` archives is now coordinated per `(tool, project)` and only archives completed `.json` files. This keeps concurrent shard runs consistent while still allowing workers to continue writing new method-history files in parallel.

### Method Code Output

`mhc method-code` reads `<data_directory>/method/{project}.csv`, checks out the repository at the indexed `updated_hash`, extracts the source lines from `start_line` through `end_line` inclusive for each method, and writes:

- `<data_directory>/method-code/{project}.csv`

The output columns are:

- `project`
- `name`
- `url`
- `artifact`
- `start_line`
- `end_line`
- `code`

For batch execution through Slurm:

```bash
# Project-array mode: one array task per project
sbatch \
    --job-name=method-code \
    --time=00:05:00 \
    --array=1-2 \
    --mem=8GB \
    --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.out \
    --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.err \
    job/job.sh \
    --command method-code \
    --cache-directory "$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache" \
    --projects "checkstyle,commons-io"

# Shard mode: one array task per history shard for a single project
sbatch \
    --job-name=history-shards \
    --time=02:00:00 \
    --array=1-20 \
    --mem=8GB \
    --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.out \
    --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.err \
    job/job.sh \
    --command history \
    --tool-name codeShovel \
    --cache-directory "$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache" \
    --projects "checkstyle" \
    --shards 20
```

`job/job.sh` now supports two history execution styles:

- Project-array mode:
  Use `--projects` with `--shards 1` or omit `--shards`. Each array task selects one project and runs the normal single-shard command.
- Shard mode:
  Use `--projects` with exactly one project and set `--shards N`. Submit the job as `--array=1-N`. Each array task maps directly to `--shard $SLURM_ARRAY_TASK_ID`.

`--project-range` is also supported by `job/job.sh` for non-sharded runs when you want to target a contiguous slice from `repository.csv`.

### LLM M2M Link

The `co-evolution` package now includes a reusable LLM classification runner with:

- API-driven provider abstraction
- OpenAI Responses API support for GPT-family models with native structured outputs
- Hugging Face model backend support for local and self-hosted models
- Durable CSV persistence for resumable long runs
- Batch execution for large method-linking jobs
- Zero-shot prompting for `t2p` and `p2t` linking
- Multi-label predictions for cases where one method maps to multiple targets


```bash
ptc-llm llm-m2m-link \
    --cache-directory ".cache" \
    --project "commons-io" \
    --input-kind "t2p" \
    --api-type "openai-responses" \
    --model-name-or-path "openai/gpt-oss-20b" \
    --api-key "$OPENAI_API_KEY" \
    --batch-size 8
```

For local or self-hosted Hugging Face models:

```bash
ptc-llm llm-m2m-link \
    --cache-directory ".cache" \
    --project "commons-io" \
    --input-kind "t2p" \
    --api-type "huggingface" \
    --model-name-or-path "Qwen/Qwen2.5-0.5B-Instruct" \
    --batch-size 4 \
    --dtype "auto"
```


For `llm-m2m-link`, the input CSV is resolved automatically from:

- `t2p` -> `<data_directory>/fan-out/<project>.csv`
- `p2t` -> `<data_directory>/fan-in/<project>.csv`

By default, outputs are written under `<cache_directory>/data/llm` using this layout:

- `<cache_directory>/data/llm/t2p/<model-name>/prediction/<input-file>.csv`
- `<cache_directory>/data/llm/t2p/<model-name>/request/<input-file>.csv`
- `<cache_directory>/data/llm/t2p/<model-name>/error/<input-file>.csv`
- `<cache_directory>/data/llm/p2t/<model-name>/prediction/<input-file>.csv`
- `<cache_directory>/data/llm/p2t/<model-name>/request/<input-file>.csv`
- `<cache_directory>/data/llm/p2t/<model-name>/error/<input-file>.csv`

If `--api-type auto` is used, GPT-family models such as `openai/gpt-oss-20b` route to the OpenAI Responses API, while other models route to Hugging Face.

For example, with `openai/gpt-oss-20b`, the model folder name becomes `gpt-oss-20b` unless `--short-model-name` is provided.

The primary files are:

- `prediction/<input-file>.csv`
- `request/<input-file>.csv`
- `error/<input-file>.csv`

`prediction/<input-file>.csv` is the original input dataframe plus the added LLM columns such as `llm_label`, `llm_confidence`, `llm_predicted_candidate_confidences`, `llm_predicted_sigs`, `llm_predicted_urls`, `llm_predicted_candidate_confidence`, and row-level `llm_predicted_match`.

For `t2p` input, rows are grouped by `from_url`. For `p2t` input, rows are grouped by `to_url`. Each group becomes one prompt, and the LLM output is merged back onto all rows in that group.

### Method History Viewer

The `co-evolution` package also includes a local browser UI for comparing test vs production method evolution.

Start the viewer:

```bash
ptc-history-viewer serve --host 127.0.0.1 --port 8765
```

For local UI development with automatic restarts after Python changes:

```bash
ptc-history-viewer serve --host 127.0.0.1 --port 8765 --reload
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

The viewer supports:

- Comparing two methods by GitHub blob URL plus `tool` (`historyFinder` or `codeShovel`)
- Comparing two cached method-history JSON files directly
- Browsing a sample directory under `.cache/data/aggregate`, then choosing one CSV in the browser
- Writing a `revision_url` column back into a sampled CSV so DBeaver can open each row in the browser
- Saving manual review notes from the browser back into the sampled CSV `note` column

To write `revision_url` into a sampled CSV from the command line:

```bash
ptc-history-viewer add-revision-links \
    --csv ".cache/data/aggregate/t2p-extreme-test-historyFinder-ncc.csv" \
    --base-url "http://127.0.0.1:8765"
```
