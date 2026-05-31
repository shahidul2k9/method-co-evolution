#!/bin/bash
module load StdEnv
module load scipy-stack/2025a
module load ipykernel/2025a
module load arrow
module load cuda
module load java/21.0.1

source .venv/bin/activate

python co-evolution/src/ptc/drac/main.py "$@"
