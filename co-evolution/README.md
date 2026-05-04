# co-evolution

Python package exposing the `ptc-llm` and `ptc-history-viewer` CLIs. Runs LLM-based test↔production method linking and serves a local browser UI for inspecting method history diffs.

For the neural TestLinker backend see [src/ptc/testlinker/README.md](src/ptc/testlinker/README.md).

## Install

```bash
pip install -e ./co-evolution          # base
pip install -e ./co-evolution[llm]     # adds OpenAI + HuggingFace backends
```

---

## `ptc-llm llm-m2m-link`

Classifies test↔production method pairs as linked or not using an LLM. Inputs are candidate-pair CSVs produced by the generator scripts (`data/fan-out/` for `t2p`, `data/fan-in/` for `p2t`). Rows are grouped by source method URL; each group becomes one prompt.

```bash
# OpenAI Responses API
ptc-llm llm-m2m-link \
    --cache-directory ".cache" \
    --project "commons-io" \
    --input-kind "t2p" \
    --api-type "openai-responses" \
    --model-name-or-path "openai/gpt-oss-20b" \
    --api-key "$OPENAI_API_KEY" \
    --batch-size 8

# Local or self-hosted HuggingFace model
ptc-llm llm-m2m-link \
    --cache-directory ".cache" \
    --project "commons-io" \
    --input-kind "t2p" \
    --api-type "huggingface" \
    --model-name-or-path "Qwen/Qwen2.5-0.5B-Instruct" \
    --batch-size 4 \
    --dtype "auto"
```

`--api-type auto` routes GPT-family model IDs to the OpenAI Responses API and everything else to HuggingFace.

### Output layout

```
<cache>/data/llm/<input-kind>/<model-name>/prediction/<project>.csv
<cache>/data/llm/<input-kind>/<model-name>/request/<project>.csv
<cache>/data/llm/<input-kind>/<model-name>/error/<project>.csv
```

`prediction/` is the input dataframe with added columns: `llm_label`, `llm_confidence`, `llm_predicted_candidate_confidences`, `llm_predicted_sigs`, `llm_predicted_urls`, `llm_predicted_candidate_confidence`, `llm_predicted_match`.

### Key options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-kind` | `t2p` | `t2p` (test→production) or `p2t` (production→test) |
| `--api-type` | `auto` | `auto`, `openai-responses`, or `huggingface` |
| `--model-name-or-path` | required | HuggingFace model id or local path |
| `--short-model-name` | derived | Override the model folder name in output paths |
| `--batch-size` | `4` | Number of method groups per batch |
| `--max-new-tokens` | `256` | Token generation cap per group |
| `--prompt-format` | `auto` | `auto`, `json`, or `text` |
| `--resume` | `none` | `none`, `all` (resume all), or `error` (retry only failed rows) |
| `--stage` | `execute` | `execute` (run LLM) or `parse` (re-parse existing responses) |

---

## `ptc-history-viewer`

Local FastAPI web UI for comparing test vs. production method evolution side by side.

```bash
# Start the server
ptc-history-viewer serve --host 127.0.0.1 --port 8765

# Auto-reload on Python changes (development)
ptc-history-viewer serve --host 127.0.0.1 --port 8765 --reload
```

Open `http://127.0.0.1:8765` in a browser.

### Features

- Compare two methods by GitHub blob URL + tool (`historyFinder` or `codeShovel`)
- Compare two cached method-history JSON files directly
- Browse a sample directory under `data/aggregate`, pick a CSV, and page through rows
- Write a `revision_url` column back into a sampled CSV for DBeaver integration
- Save manual review notes from the browser into the CSV `note` column

### Write revision links from the command line

```bash
ptc-history-viewer add-revision-links \
    --csv ".cache/data/aggregate/t2p-extreme-test-historyFinder-ncc.csv" \
    --base-url "http://127.0.0.1:8765"
```
