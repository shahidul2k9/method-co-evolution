# Understanding Method-Level Test Code Evolution

This repository supports an empirical study of method-level test code evolution. It evaluates test method history tracking, production-to-test mapping, and downstream analyses of revision frequency and test smells.

## Research Questions

**RQ1: Can existing history tracking tools effectively track test method revision histories?**  
We evaluate state-of-the-art method history tracking tools using a manually constructed oracle of 120 test methods from 40 open-source Java projects.

**RQ2: What is the most accurate approach for method-level production-to-test mapping?**  
We evaluate static analysis-based mapping techniques using existing benchmarks and a newly created oracle for 20 projects.

**RQ3: Are test methods revised less frequently?**  
Using the most effective history tracking and mapping approaches, we compare revision frequencies between test methods and the production methods they exercise.

**RQ4: Are test smells associated with high revisions?**  
We study whether test smells are more common in test methods that accumulate more revisions than their corresponding production methods.

Ground-truth datasets for RQ1 and RQ2 are documented in [data/ground-truth.md](data/ground-truth.md).

## Prerequisites

- Python 3.12+
- Java 21
- Maven 3.6+
- Git

## Project Layout

| Path | Role |
|------|------|
| `method-history-collector/` | Python package exposing `mhc`, the main collection CLI |
| `method-parser/` | JavaParser-based Maven module for method, class, and callgraph extraction |
| `co-evolution/` | Python package exposing `ptc-llm`, `ptc-history-viewer`, `ptc-testlinker`, and `ptc-sbatch` |
| `co-evolution/src/ptc/testlinker/` | Neural TestLinker integration and model pipeline notes |
| `jnose-adapter/` | Executable wrapper used by the `mhc test-smell` workflow |
| `scripts/` | Build, Slurm, and maintenance helpers |
| `config/` and `docs/` | Artifact-detection and experiment configuration references |

Each tracked README is a focused reference for its module. Generated cache READMEs, such as `.pytest_cache/README.md`, are not part of the project documentation.

## Workspace Layout

`ME_WORKSPACE_DIRECTORY` stores experimental data and generated artifacts. Multiple experiments can run concurrently under `workspace/experiment/<name>/` by changing `ME_EXPERIMENT_NAME`, which is useful for different project sets, tool configurations, or study runs.

Example workspace layout:

```text
workspace/
  jar/
    method-parser.jar
  experiment/
    main/
      aggregate                      Concatenated individual project csvs or resultant csv across project.
      project.csv                    Project index and repository metadata for the experiment.
      method/                        Method index CSVs extracted from each project.
      method-code/                   Method source and code metadata for downstream linking and filtering.
      method-history/                Method revision count.
      method-history-gz/             Compressed method history archives.
      class/                         Class index CSVs extracted from each project.
      callgraph/                     Method call graph (fan-out).
      t2p-candidate-expanded/        Expanded production-to-test mapping candidates.
      t2p-candidate-filtered/        Filtered production-to-test candidates used by linkers.
      t2p-tech/                      Per-technique mapping predictions and intermediate technique outputs.
      t2p-link/                      Final production-to-test links by strategy/technique.
      t2p-change/                    Linked production/test revision comparison data.
      t2p-revision-review/           Sampled or review-oriented revision comparison data.
      test-smell/                    Test smell detector outputs.
      t2p-test-smell/                Test smells joined with production-to-test links.
      t2p-test-smell-with-revision/  Linked test smell rows with revision-group information.
```

The Python packages load `.env` from the repository root. A typical local file contains:

```bash
# Repository root used by scripts to resolve project-relative paths.
ME_PROJECT_DIRECTORY=/path/to/method-co-evolution

# Shared workspace for experimental data and generated artifacts.
ME_WORKSPACE_DIRECTORY=/path/to/method-co-evolution/workspace

# Active experiment under ME_WORKSPACE_DIRECTORY/experiment/.
ME_EXPERIMENT_NAME=main

# Optional: faster repository checkout and GitHub API access.
GITHUB_API_KEY=ghp_...

# Optional: store method histories outside the main workspace.
ME_HISTORY_DIRECTORY=/scratch/method-co-evolution/history

# Optional: Hugging Face access for local model downloads or gated models.
HF_TOKEN=hf_...

# Optional: OpenAI access for LLM-based linking experiments.
OPENAI_API_KEY=sk_...
```

## Python Environment

Run these commands from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./method-history-collector
pip install -e ./co-evolution

# Optional backends
pip install -e './co-evolution[llm]'
pip install -e './co-evolution[testlinker]'
```

## Data Collection

If you already have data from the replication package, skip this section and follow [replication-package.md](replication-package.md) for copying data into the workspace experiment. If you are experimenting with a new project set or collecting data from scratch, follow the collection workflow and see [scripts/README.md](scripts/README.md) for local wrapper and Slurm command details.

## Running Experiment

Run the code in each notebook cell in order. Before running notebook commands, make sure the required raw data already exists; see [Data Collection](#data-collection) for collecting data from scratch. Each step in the notebooks may depend on intermediate results produced by earlier cells or earlier notebooks.

```text
co-evolution/src/ptc/run/method_link_run.ipynb
co-evolution/src/ptc/run/method_history_run.ipynb
co-evolution/src/ptc/run/method_linker_evaluation.ipynb
co-evolution/src/ptc/run/rq_plot_run.ipynb
```

## Common Documentation

- [method-history-collector/README.md](method-history-collector/README.md) for `mhc` commands and experiment path defaults.
- [method-parser/README.md](method-parser/README.md) for Java build steps and CSV schemas.
- [co-evolution/README.md](co-evolution/README.md) for LLM linking, history viewer, TestLinker entrypoints, and Slurm command expansion.
- [co-evolution/src/ptc/testlinker/README.md](co-evolution/src/ptc/testlinker/README.md) for neural TestLinker setup and model artifacts.
- [scripts/README.md](scripts/README.md) for helper scripts and Slurm usage.
- [jnose-adapter/README.md](jnose-adapter/README.md) for test-smell adapter build steps.
