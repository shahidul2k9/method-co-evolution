# T2P Ground Truth Sampler

`ptc.sample.sample_t2p_ground_truth` creates per-project test-to-production
ground-truth CSVs for labeling. It can sample new test methods, regenerate
existing candidate-backed rows, preserve manual labels, refresh selected
metadata columns, or append only the test methods needed to reach a target.

## Inputs And Outputs

| Purpose | Location |
|---|---|
| Existing ground truth input | `--t2p-ground-truth-dir/<project>.csv` |
| Project index | `workspace/experiment/{experiment}/project.csv` |
| Expanded candidate input | `workspace/experiment/{experiment}/t2p-candidate-expanded/<project>.csv` |
| Method metadata input | `workspace/experiment/{experiment}/method/<project>.csv` |
| Generated ground truth output | `workspace/experiment/{experiment}/t2p-ground-truth/<project>.csv` |
| Temporary atomic-write files | `workspace/experiment/{experiment}/.t2p-ground-truth/<project>.csv` |

The command writes generated files to the experiment output directory. It does
not write directly to `--t2p-ground-truth-dir` unless that directory is also
the experiment output directory.

## Common Commands

### Standard Regeneration And Top-Up

Use standard mode when existing candidate-backed rows should be regenerated
from the current expanded candidate files. Existing `label`, `tags`, and
`notes` values are carried forward by matching `from_url` and `to_url`.

The sample count is a target, not an amount to add. A project with 17 existing
test methods receives 3 fresh test methods when the target is 20.

```bash
PYTHONPATH=co-evolution/src:method-history-collector/src \
python -m ptc.sample.sample_t2p_ground_truth \
  --workspace-directory workspace \
  --experiment-name main \
  --project-index "12,13,14,22,29,36,40,41,47,49,53,54,59,60,63,68,79,92,94,96" \
  --sample-count-per-project 20 \
  --t2p-ground-truth-dir data/t2plinker/t2p-ground-truth
```

Standard mode may replace existing metadata such as `from_testlinker_fqs` and
`to_testlinker_fqs` because candidate-backed rows are rebuilt from current
expanded candidate data.

### Add-Only Top-Up

Use `--add-only` when existing rows must remain unchanged and only enough fresh
test methods should be appended to reach the target count.

```bash
PYTHONPATH=co-evolution/src:method-history-collector/src \
python -m ptc.sample.sample_t2p_ground_truth \
  --workspace-directory workspace \
  --experiment-name main \
  --project-index "12,13,14,22,29,36,40,41,47,49,53,54,59,60,63,68,79,92,94,96" \
  --sample-count-per-project 20 \
  --t2p-ground-truth-dir data/t2plinker/t2p-ground-truth \
  --add-only
```

Add-only mode:

- Counts unique, non-empty existing `from_url` values as selected test methods.
- Preserves every existing ground-truth column value.
- Appends candidate rows only for newly sampled test methods.
- Sets `candidate = 1` on appended rows.
- Does not recompute existing `candidate` values or refresh existing metadata.
- Cannot be combined with `--update-columns` or `--add-missing-candidates`.

### Normalize Or Refresh Existing Rows

Use a sample count of `0` to add no fresh test methods. Standard mode still
normalizes the schema, preserves existing rows, recomputes the `candidate`
column, and refreshes explicitly requested metadata when source data is
available.

```bash
PYTHONPATH=co-evolution/src:method-history-collector/src \
python -m ptc.sample.sample_t2p_ground_truth \
  --workspace-directory workspace \
  --experiment-name main \
  --project-index ":" \
  --sample-count-per-project 0 \
  --t2p-ground-truth-dir data/t2plinker/t2p-ground-truth \
  --update-columns from_fqs,from_testlinker_fqs,to_fqs,to_testlinker_fqs,to_call_depth
```

Use `--update-columns` only when the listed values should intentionally be
refreshed from current method or candidate metadata. Protected review fields
`from_url`, `to_url`, `label`, `tags`, and `notes` cannot be refreshed.

### Add Missing Candidates For Existing Test Methods

Use `--add-missing-candidates` to append expanded candidate pairs that are
missing from the ground truth for test methods already present in the input.
New rows receive blank labels.

```bash
PYTHONPATH=co-evolution/src:method-history-collector/src \
python -m ptc.sample.sample_t2p_ground_truth \
  --workspace-directory workspace \
  --experiment-name main \
  --project-index ":" \
  --sample-count-per-project 0 \
  --t2p-ground-truth-dir data/t2plinker/t2p-ground-truth \
  --add-missing-candidates
```

## Options

| Option | Required | Description |
|---|---:|---|
| `--workspace-directory PATH` | No | Workspace root containing `experiment/{experiment}`. Defaults to `ME_WORKSPACE_DIRECTORY`. |
| `--experiment-name NAME` | No | Experiment directory name. Defaults to `ME_EXPERIMENT_NAME`. |
| `--projects NAMES` | No | Comma-separated project names to process. Defaults to `ME_PROJECTS`. |
| `--project-index INDEX` | No | Select projects by zero-based integer, comma-separated integers such as `0,2,4`, Python slice such as `1:5` or `::2`, or `:` for all projects. |
| `--sample-count-per-project COUNT` | Yes | Target number of unique test methods per project. Use `0` to add no fresh methods. Existing methods above the target are retained. |
| `--t2p-ground-truth-dir PATH` | Yes | Directory containing existing per-project ground-truth CSVs used as working input. |
| `--exclude-test-artifact-regex REGEX` | No | Exclude matching test artifact tags from fresh random sampling. Existing selected methods remain included. |
| `--update-columns COLUMNS` | No | Comma-separated ground-truth columns to intentionally refresh when source metadata is available. Cannot be used with `--add-only`. |
| `--add-missing-candidates` | No | Append missing expanded candidate pairs for existing input test methods. Cannot be used with `--add-only`. |
| `--add-only` | No | Preserve all existing row values and append only fresh test methods needed to reach the sample target. |
| `-h`, `--help` | No | Print command help and exit. |

## Candidate And Label Columns

The output schema includes `candidate` immediately after `to_call_depth`.

- `candidate = 1`: the row exists in the matching expanded candidate CSV.
- `candidate = 0`: the row is not present, or the expanded candidate CSV is missing.
- `label`: the manually reviewed ground-truth decision; it is not inferred from `candidate`.

Candidate rows are matched by `project`, `from_url`, and `to_url`.
