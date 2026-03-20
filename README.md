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
```

### LLM M2M Link

The `co-evolution` package now includes a reusable LLM classification runner with:

- Hugging Face model backend abstraction
- Durable CSV persistence for resumable long runs
- Batch execution for large method-linking jobs
- Zero-shot prompting for `t2p` and `p2t` linking
- Multi-label predictions for cases where one method maps to multiple targets


```bash
ptc-llm llm-m2m-link \
    --cache-directory ".cache" \
    --project "commons-io" \
    --input-kind "t2p" \
    --model-name-or-path "openai/gpt-oss-20b" \
    --batch-size 8 \
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

For example, with `openai/gpt-oss-20b`, the model folder name becomes `gpt-oss-20b`.

The primary files are:

- `prediction/<input-file>.csv`
- `request/<input-file>.csv`
- `error/<input-file>.csv`

`prediction/<input-file>.csv` is the original input dataframe plus the added LLM columns such as `llm_label`, `llm_confidence`, `llm_predicted_candidate_confidences`, `llm_predicted_sigs`, `llm_predicted_urls`, `llm_predicted_candidate_confidence`, and row-level `llm_predicted_match`.

For `t2p` input, rows are grouped by `from_url`. For `p2t` input, rows are grouped by `to_url`. Each group becomes one prompt, and the LLM output is merged back onto all rows in that group.
