#!/bin/bash
#SBATCH --job-name=method-history-collector
#SBATCH --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-level-maintenance/.cache/log/job/%x.%A_%a.out
#SBATCH --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-level-maintenance/.cache/log/job/%x.%A_%a.err
set -euo pipefail
module load python
module load scipy-stack
module load ipykernel
module load StdEnv
module load cuda
module load arrow
export PROJECT_DIRECTORY="$HOME/projects/$SLURM_ACCOUNT/$USER/method-level-maintenance"
export CACHE_DIRECTORY="$PROJECT_DIRECTORY/.cache"
LOG_DIR="$CACHE_DIRECTORY/log/job"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIRECTORY"
source "$PROJECT_DIRECTORY/.venv/bin/activate"
TOOL_NAME=$1
IFS=',' read -r -a REPOSITORIES <<< "$2"
NUM_REPOS=${#REPOSITORIES[@]}
if [[ "$NUM_REPOS" -lt "$SLURM_ARRAY_TASK_COUNT" ]]; then
    echo "Error: Number of repositories ($NUM_REPOS) less than SLURM array task count ($SLURM_ARRAY_TASK_COUNT)."
    exit 1
fi

REPOSITORY=${REPOSITORIES[$SLURM_ARRAY_TASK_ID]}

srun python method-history-collector/src/mhc/main.py history \
    --cache_directory "$CACHE_DIRECTORY" \
    --repository_directory "$CACHE_DIRECTORY/repository" \
    --data_directory "$CACHE_DIRECTORY/data" \
    --jar_directory "$CACHE_DIRECTORY/jar" \
    --tool_name "$TOOL_NAME" \
    --repository_name "$REPOSITORY"
echo "Task started on $(hostname) at $(date) for tool name $TOOL_NAME and repository $REPOSITORY"