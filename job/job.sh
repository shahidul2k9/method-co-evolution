#!/bin/bash
#SBATCH --job-name=MHC
#SBATCH --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.out
#SBATCH --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.err
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  job.sh --command history --tool-name codeShovel --java-options "-Xmx4g" --timeout-seconds 1800 --command-options "--flag value" --projects "checkstyle,commons-io"
  job.sh --command llm-m2m-link --api-type huggingface --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --prompt-format text --max-new-tokens 256 --projects "commons-io" --input-kind t2p

Options:
  --command               Command to run: history, call-graph, scan-method, complexity-analyzer, llm-m2m-link
  --tool-name             Tool name for non-LLM commands
  --java-options          Optional JVM arguments for history commands, e.g. "-Xmx4g"
  --timeout-seconds       Optional history command timeout in seconds (default: 30*60 = 1800)
  --command-options       Optional extra arguments forwarded to the selected command
  --api-type              LLM provider API type: auto, huggingface, or openai-responses (default: auto)
  --model-name-or-path    Hugging Face model id or local path for llm-m2m-link
  --short-model-name      Short model directory name for llm-m2m-link outputs
  --prompt-format         LLM prompt format: auto, json, or text (default: auto)
  --max-new-tokens        LLM generation cap per grouped case (default: 256)
  --projects              Comma-separated project list for the array job
  --input-kind            LLM input kind: t2p or p2t (default: t2p)
  --cache-directory       Relative or absolute cache directory (default: .cache)
  --help                  Show this message
EOF
}

module load StdEnv
module load scipy-stack/2025a
module load ipykernel/2025a
module load arrow
module load cuda
module load java/21.0.1

export PROJECT_DIRECTORY="$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution"
COMMAND_NAME=""
TOOL_NAME=""
JAVA_OPTIONS=""
TIMEOUT_SECONDS="1800"
COMMAND_OPTIONS=""
API_TYPE="auto"
MODEL_NAME_OR_PATH=""
SHORT_MODEL_NAME=""
PROMPT_FORMAT="auto"
MAX_NEW_TOKENS="256"
PROJECTS_CSV=""
INPUT_KIND="t2p"
CACHE_DIRECTORY="$PROJECT_DIRECTORY/.cache"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --command)
            COMMAND_NAME="$2"
            shift 2
            ;;
        --tool-name)
            TOOL_NAME="$2"
            shift 2
            ;;
        --java-options)
            JAVA_OPTIONS="$2"
            shift 2
            ;;
        --timeout-seconds)
            TIMEOUT_SECONDS="$2"
            shift 2
            ;;
        --command-options)
            COMMAND_OPTIONS="$2"
            shift 2
            ;;
        --api-type)
            API_TYPE="$2"
            shift 2
            ;;
        --model-name-or-path)
            MODEL_NAME_OR_PATH="$2"
            shift 2
            ;;
        --short-model-name)
            SHORT_MODEL_NAME="$2"
            shift 2
            ;;
        --prompt-format)
            PROMPT_FORMAT="$2"
            shift 2
            ;;
        --max-new-tokens)
            MAX_NEW_TOKENS="$2"
            shift 2
            ;;
        --projects)
            PROJECTS_CSV="$2"
            shift 2
            ;;
        --input-kind)
            INPUT_KIND="$2"
            shift 2
            ;;
        --cache-directory)
            CACHE_DIRECTORY="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ -z "$COMMAND_NAME" || -z "$PROJECTS_CSV" ]]; then
    echo "Error: --command and --projects are required."
    usage
    exit 1
fi

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    if [[ -z "$MODEL_NAME_OR_PATH" ]]; then
        echo "Error: --model-name-or-path is required for llm-m2m-link."
        usage
        exit 1
    fi
else
    if [[ -z "$TOOL_NAME" ]]; then
        echo "Error: --tool-name is required for $COMMAND_NAME."
        usage
        exit 1
    fi
fi

LOG_DIR="$CACHE_DIRECTORY/log/job"
mkdir -p "$LOG_DIR"
cd "$PROJECT_DIRECTORY"
source "$PROJECT_DIRECTORY/.venv/bin/activate"

IFS=',' read -r -a PROJECTS <<< "$PROJECTS_CSV"
if [[ $SLURM_ARRAY_TASK_ID -le 0 || $SLURM_ARRAY_TASK_ID -gt ${#PROJECTS[@]} ]]; then
    echo "Invalid SLURM_ARRAY_TASK_ID: $SLURM_ARRAY_TASK_ID"
    exit 1
fi

IDX=$((SLURM_ARRAY_TASK_ID - 1))
PROJECT=${PROJECTS[$IDX]}

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    srun ptc-llm llm-m2m-link \
        --cache-directory "$CACHE_DIRECTORY" \
        --api-type "$API_TYPE" \
        --model-name-or-path "$MODEL_NAME_OR_PATH" \
        --short-model-name "$SHORT_MODEL_NAME" \
        --prompt-format "$PROMPT_FORMAT" \
        --max-new-tokens "$MAX_NEW_TOKENS" \
        --input-kind "$INPUT_KIND" \
        --project "$PROJECT"
    echo "Task started on $(hostname) at $(date) for model $MODEL_NAME_OR_PATH, input kind $INPUT_KIND, and project $PROJECT"
else
    srun mhc "$COMMAND_NAME" \
        --cache-directory "$CACHE_DIRECTORY" \
        --repository-directory "$SLURM_TMPDIR/repository" \
        --data-directory "$CACHE_DIRECTORY/data" \
        --jar-directory "$CACHE_DIRECTORY/jar" \
        --tool-name "$TOOL_NAME" \
        --java-options="$JAVA_OPTIONS" \
        --timeout-seconds "$TIMEOUT_SECONDS" \
        --command-options "$COMMAND_OPTIONS" \
        --project "$PROJECT"
    echo "Task started on $(hostname) at $(date) for tool name $TOOL_NAME and project $PROJECT"
fi
