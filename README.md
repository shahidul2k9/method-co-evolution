# method-co-evolution

A research pipeline for studying co-evolution of production and test methods in open-source Java projects. It extracts methods, traces their change histories, links test methods to production methods using heuristics, LLMs, and neural models, then analyzes the correlation of their changes.

## Prerequisites

- Python 3.10+
- Java 21
- Maven 3

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ./method-history-collector
pip install -e ./co-evolution
pip install -e ./co-evolution[llm]        # optional: LLM/neural backends
pip install -e ./co-evolution[testlinker] # optional: TestLinker/CodeT5 backend
```

Build the Java method-parser module and copy the JAR into the cache:

```bash
scripts/build_mp.sh
# or manually:
cd method-parser && mvn clean install -DskipTests
```

## Modules

| Module | README | Description |
|--------|--------|-------------|
| `method-parser/` | [README](method-parser/README.md) | Java module — method extraction and call-graph generation; dataset schemas |
| `method-history-collector/` | [README](method-history-collector/README.md) | `mhc` CLI — history collection, sharding, call-graph, method-code |
| `co-evolution/` | [README](co-evolution/README.md) | `ptc-llm`, `ptc-history-viewer` — LLM linking, history viewer |
| `co-evolution/src/ptc/testlinker/` | [README](co-evolution/src/ptc/testlinker/README.md) | `ptc-testlinker` — neural test-to-production linking (CodeT5) |
| `scripts/` | [README](scripts/README.md) | Build script, Slurm job wrapper, oracle metadata utility |

## Pipeline Overview

```
repository.csv
  → mhc scan-method        → data/method/{project}.csv
  → mhc call-graph         → data/call-graph/{project}.csv (fan-in / fan-out)
  → mhc history            → data/history/{tool}/{project}/ (.tar.gz archives)
  → mhc method-code        → data/method-code/{project}.csv
  → generator scripts      → data/fan-in/, data/fan-out/   (candidate pairs)
  → ptc-llm / testlinker   → data/llm/{model}/             (ranked predictions)
```

Cache layout is controlled by `--cache-directory` (default `.cache`). See `.env` for path overrides and API keys.
