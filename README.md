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
    --project "checkstyle"
    
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
```

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
