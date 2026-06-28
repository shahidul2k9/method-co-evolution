# Replication Package

This document explains how to use the Zenodo replication package to reproduce the method co-evolution experiment results. It is written for researchers who have downloaded the artifact and want to replay the analysis from the packaged data.

## 1. Get the Code

Clone the anonymous GitHub repository:

```text
https://anonymous.4open.science/r/test-evolution
```

After cloning the repository, read `README.md` in the project root and complete the project setup, dependency installation, and build steps described there.

## 2. Download the Data

Download the replication package from Zenodo:

```text
https://zenodo.org/records/0000000
```

The Zenodo URL is a placeholder and should be replaced with the final record URL before publication.

The extracted package contains a `.env` file and a `workspace/` directory. The `workspace/` directory preserves the same relative paths used by the project.

## 3. Copy the Package into the Project

Copy the packaged `.env` file into the cloned project root:

```bash
cp /path/to/replication-package/.env /path/to/method-co-evolution/.env
```

Copy the packaged `workspace/` directory into the cloned project root:

```bash
cp -R /path/to/replication-package/workspace /path/to/method-co-evolution/
```

After copying, the cloned project should contain paths such as:

```text
workspace/experiment/main/project.csv
workspace/experiment/main/method/
workspace/experiment/main/method-history/
```

## 4. Configure `.env`

Open the copied `.env` file and set `PROJECT_DIRECTORY` to the local path of the cloned project. The path configuration should follow this pattern:

```bash
PROJECT_DIRECTORY=/path/to/method-co-evolution
ME_PROJECT_DIRECTORY=${PROJECT_DIRECTORY}
ME_WORKSPACE_DIRECTORY=${PROJECT_DIRECTORY}/workspace
```

The packaged `.env` should not contain private local paths or secret tokens. Keep API token variables blank unless you intentionally run optional regeneration steps that require remote services.

## 5. Package Contents

The package contains raw input data and selected shareable derived inputs needed to replay the experiment notebooks. Method-history CSV files are included. Method-history JSON files and compressed archives are not included.

Main experiment contents:

```text
workspace/experiment/main/callgraph
workspace/experiment/main/class
workspace/experiment/main/method
workspace/experiment/main/method-code
workspace/experiment/main/method-history
workspace/experiment/main/project.csv
workspace/experiment/main/t2p-link/nc
workspace/experiment/main/t2p-link/omc
workspace/experiment/main/t2p-link/omc--nc
workspace/experiment/main/test-smell/jnose/omc--nc
```

Evaluation experiment contents are included for `tctracer-2020`, `tctracer-2022`, `testlinker`, and `t2plinker`. Each experiment contains:

```text
workspace/experiment/<experiment>/callgraph
workspace/experiment/<experiment>/class
workspace/experiment/<experiment>/method
workspace/experiment/<experiment>/method-code
workspace/experiment/<experiment>/project.csv
workspace/experiment/<experiment>/t2p-link/combined
workspace/experiment/<experiment>/t2p-link/lc
workspace/experiment/<experiment>/t2p-link/lcba
workspace/experiment/<experiment>/t2p-link/lcs-b
workspace/experiment/<experiment>/t2p-link/lcs-u
workspace/experiment/<experiment>/t2p-link/leven
workspace/experiment/<experiment>/t2p-link/nc
workspace/experiment/<experiment>/t2p-link/ncc
workspace/experiment/<experiment>/t2p-link/omc
workspace/experiment/<experiment>/t2p-link/omc--nc
workspace/experiment/<experiment>/t2p-link/tarantula
workspace/experiment/<experiment>/t2p-link/testlinkerv2
workspace/experiment/<experiment>/t2p-link/tfidf
workspace/experiment/<experiment>/t2p-tech
workspace/experiment/<experiment>/testlinker/output/codet5/testlinkerv2
```

The package does not include:

```text
method-history JSON files or compressed archives
repository clones
caches and intermediate generated outputs
personal or local-only files
```

## 6. Replay the Experiments

Complete the setup instructions in `README.md` before running the notebooks. Then run the notebooks in this order from the cloned project:

```text
co-evolution/src/ptc/run/method_link_run.ipynb
co-evolution/src/ptc/run/method_history_run.ipynb
co-evolution/src/ptc/run/method_linker_evaluation.ipynb
co-evolution/src/ptc/run/rq_plot_run.ipynb
```

The replay workflow regenerates analysis and reporting outputs from the packaged data. Expected outputs include:

```text
workspace/experiment/main/aggregate/
workspace/experiment/main/t2p-change/
workspace/experiment/main/t2p-test-smell-with-revision/
workspace/experiment/main/figure/
workspace/experiment/all/t2p-link-metric/
workspace/t2p_link_overall_metric.csv
```
