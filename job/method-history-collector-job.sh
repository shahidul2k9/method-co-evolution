#!/bin/bash
#SBATCH --job-name=MHC
#SBATCH --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.out
#SBATCH --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.err
set -euo pipefail
module load StdEnv
module load scipy-stack/2025a
module load ipykernel/2025a
module load arrow
module load cuda
module load java/21.0.1
export PROJECT_DIRECTORY="$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution"
export CACHE_DIRECTORY="$PROJECT_DIRECTORY/.cache"
LOG_DIR="$CACHE_DIRECTORY/log/job"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIRECTORY"
source "$PROJECT_DIRECTORY/.venv/bin/activate"
#pip install -e ./method-history-collector
COMMAND_NAME=$1
TOOL_NAME=$2
IFS=',' read -r -a REPOSITORIES <<< "$3"
if [[ $SLURM_ARRAY_TASK_ID -le 0 || $SLURM_ARRAY_TASK_ID -gt ${#REPOSITORIES[@]} ]]; then
    echo "Invalid SLURM_ARRAY_TASK_ID: $SLURM_ARRAY_TASK_ID"
    exit 1
fi

IDX=$((SLURM_ARRAY_TASK_ID - 1))
REPOSITORY=${REPOSITORIES[$IDX]}

srun mhc "$COMMAND_NAME" \
    --cache_directory "$CACHE_DIRECTORY" \
    --repository_directory "$SLURM_TMPDIR/repository" \
    --data_directory "$CACHE_DIRECTORY/data" \
    --jar_directory "$CACHE_DIRECTORY/jar" \
    --tool_name "$TOOL_NAME" \
    --repository_name "$REPOSITORY"
echo "Task started on $(hostname) at $(date) for tool name $TOOL_NAME and repository $REPOSITORY"