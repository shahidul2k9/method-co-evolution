#!/bin/bash
#SBATCH --job-name=MHC
#SBATCH --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.out
#SBATCH --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/.cache/log/job/%x.%A_%a.err
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  job.sh --command history --tool-name codeShovel --java-options "-Xmx4g" --timeout-seconds 1800 --merge-threshold 10000 --command-options "--flag value" --projects "checkstyle,commons-io"
  job.sh --command history --tool-name codeShovel --merge-only --projects "checkstyle,commons-io"
  job.sh --command history --tool-name codeShovel --projects "checkstyle" --shards 20
  job.sh --command method-code --projects "commons-io"
  job.sh --command llm-m2m-link --api-type huggingface --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --prompt-format text --batch-size 1 --max-new-tokens 256 --resume none --projects "commons-io" --input-kind t2p
  job.sh --command llm-m2m-link --api-type huggingface --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --batch-size 1 --resume error --projects "commons-io" --input-kind t2p
  job.sh --command llm-m2m-link --stage parse --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --projects "commons-io"

Options:
  --command               Command to run: history, call-graph, scan-method, method-code, complexity-analyzer, llm-m2m-link
  --tool-name             Tool name for non-LLM commands
  --java-options          Optional JVM arguments for history commands, e.g. "-Xmx4g"
  --timeout-seconds       Optional history command timeout in seconds (default: 30*60 = 1800)
  --merge-threshold       Optional history JSON merge threshold (default: 10000; 0 disables intermediate merging; negative values disable final merging too)
  --merge-only            Merge existing loose history JSON files without generating new history
  --command-options       Optional extra arguments forwarded to the selected command
  --stage                 LLM stage: execute or parse (default: execute)
  --api-type              LLM provider API type: auto, huggingface, or openai-responses (default: auto)
  --model-name-or-path    Hugging Face model id or local path for llm-m2m-link
  --short-model-name      Short model directory name for llm-m2m-link outputs
  --prompt-format         LLM prompt format: auto, json, or text (default: auto)
  --batch-size            LLM grouped case batch size (default: 4)
  --max-new-tokens        LLM generation cap per grouped case (default: 256)
  --resume                Resume mode: none, all, or error (default: none)
  --projects              Comma-separated project list for the array job
  --project-range         1-based inclusive project range from repository.csv, for example 10:20
  --shards                Total method-history shards to run in parallel (default: 1)
  --input-kind            LLM input kind: t2p or p2t (default: t2p)
  --cache-directory       Relative or absolute cache directory (default: .cache)
  --data-directory        Relative or absolute data directory (default: <cache-directory>/data)
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
MERGE_THRESHOLD="10000"
MERGE_ONLY="false"
COMMAND_OPTIONS=""
STAGE="execute"
API_TYPE="auto"
MODEL_NAME_OR_PATH=""
SHORT_MODEL_NAME=""
PROMPT_FORMAT="auto"
BATCH_SIZE="4"
MAX_NEW_TOKENS="256"
RESUME_MODE="none"
PROJECTS_CSV=""
PROJECT_RANGE=""
SHARDS="1"
INPUT_KIND="t2p"
CACHE_DIRECTORY="$PROJECT_DIRECTORY/.cache"
DATA_DIRECTORY=""

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
        --merge-threshold)
            MERGE_THRESHOLD="$2"
            shift 2
            ;;
        --merge-only)
            MERGE_ONLY="true"
            shift
            ;;
        --command-options)
            COMMAND_OPTIONS="$2"
            shift 2
            ;;
        --stage)
            STAGE="$2"
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
        --batch-size)
            BATCH_SIZE="$2"
            shift 2
            ;;
        --max-new-tokens)
            MAX_NEW_TOKENS="$2"
            shift 2
            ;;
        --resume)
            RESUME_MODE="$2"
            shift 2
            ;;
        --projects)
            PROJECTS_CSV="$2"
            shift 2
            ;;
        --project-range)
            PROJECT_RANGE="$2"
            shift 2
            ;;
        --shards)
            SHARDS="$2"
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
        --data-directory)
            DATA_DIRECTORY="$2"
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

if [[ -z "$DATA_DIRECTORY" ]]; then
    DATA_DIRECTORY="$CACHE_DIRECTORY/data"
fi

if [[ -z "$COMMAND_NAME" ]]; then
    echo "Error: --command is required."
    usage
    exit 1
fi

if [[ -z "$PROJECTS_CSV" && -z "$PROJECT_RANGE" && "$COMMAND_NAME" != "index" ]]; then
    echo "Error: one of --projects or --project-range is required."
    usage
    exit 1
fi

if [[ -n "$PROJECTS_CSV" && -n "$PROJECT_RANGE" ]]; then
    echo "Error: use either --projects or --project-range, not both."
    usage
    exit 1
fi

if ! [[ "$SHARDS" =~ ^[0-9]+$ ]] || [[ "$SHARDS" -le 0 ]]; then
    echo "Error: --shards must be a positive integer."
    usage
    exit 1
fi

if ! [[ "$MERGE_THRESHOLD" =~ ^-?[0-9]+$ ]]; then
    echo "Error: --merge-threshold must be an integer."
    usage
    exit 1
fi

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    if [[ -z "$MODEL_NAME_OR_PATH" ]]; then
        echo "Error: --model-name-or-path is required for $COMMAND_NAME."
        usage
        exit 1
    fi
elif [[ "$COMMAND_NAME" != "scan-method" && "$COMMAND_NAME" != "method-code" && "$COMMAND_NAME" != "index" ]]; then
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

PROJECT=""
SHARD="1"

if [[ "$COMMAND_NAME" != "index" ]]; then
    if [[ "$SHARDS" -gt 1 ]]; then
        if [[ -z "$PROJECTS_CSV" ]]; then
            echo "Error: shard mode currently requires --projects with exactly one project."
            usage
            exit 1
        fi
        IFS=',' read -r -a PROJECTS <<< "$PROJECTS_CSV"
        if [[ ${#PROJECTS[@]} -ne 1 ]]; then
            echo "Error: shard mode requires exactly one project in --projects."
            usage
            exit 1
        fi
        if [[ -z "${SLURM_ARRAY_TASK_ID:-}" || $SLURM_ARRAY_TASK_ID -le 0 || $SLURM_ARRAY_TASK_ID -gt "$SHARDS" ]]; then
            echo "Invalid SLURM_ARRAY_TASK_ID for shard mode: ${SLURM_ARRAY_TASK_ID:-unset}"
            exit 1
        fi
        PROJECT=${PROJECTS[0]}
        SHARD="$SLURM_ARRAY_TASK_ID"
    elif [[ -n "$PROJECTS_CSV" ]]; then
        IFS=',' read -r -a PROJECTS <<< "$PROJECTS_CSV"
        if [[ -z "${SLURM_ARRAY_TASK_ID:-}" || $SLURM_ARRAY_TASK_ID -le 0 || $SLURM_ARRAY_TASK_ID -gt ${#PROJECTS[@]} ]]; then
            echo "Invalid SLURM_ARRAY_TASK_ID: ${SLURM_ARRAY_TASK_ID:-unset}"
            exit 1
        fi
        IDX=$((SLURM_ARRAY_TASK_ID - 1))
        PROJECT=${PROJECTS[$IDX]}
    fi
fi

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    if [[ "$RESUME_MODE" != "none" && "$RESUME_MODE" != "all" && "$RESUME_MODE" != "error" ]]; then
        echo "Error: --resume must be one of: none, all, error"
        usage
        exit 1
    fi
    srun ptc-llm llm-m2m-link \
        --cache-directory "$CACHE_DIRECTORY" \
        --stage "$STAGE" \
        --api-type "$API_TYPE" \
        --model-name-or-path "$MODEL_NAME_OR_PATH" \
        --short-model-name "$SHORT_MODEL_NAME" \
        --prompt-format "$PROMPT_FORMAT" \
        --batch-size "$BATCH_SIZE" \
        --max-new-tokens "$MAX_NEW_TOKENS" \
        --resume "$RESUME_MODE" \
        --input-kind "$INPUT_KIND" \
        --project "$PROJECT"
    echo "Task finished on $(hostname) at $(date) for llm stage $STAGE, model $MODEL_NAME_OR_PATH, input kind $INPUT_KIND, and project $PROJECT"
else
    MHC_ARGS=(
        "$COMMAND_NAME"
        --cache-directory "$CACHE_DIRECTORY"
        --repository-directory "$SLURM_TMPDIR/repository"
        --data-directory "$DATA_DIRECTORY"
        --jar-directory "$CACHE_DIRECTORY/jar"
        --timeout-seconds "$TIMEOUT_SECONDS"
        --merge-threshold "$MERGE_THRESHOLD"
    )
    if [[ -n "$TOOL_NAME" ]]; then
        MHC_ARGS+=(--tool-name "$TOOL_NAME")
    fi
    if [[ -n "$JAVA_OPTIONS" ]]; then
        MHC_ARGS+=(--java-options="$JAVA_OPTIONS")
    fi
    if [[ -n "$COMMAND_OPTIONS" ]]; then
        MHC_ARGS+=(--command-options "$COMMAND_OPTIONS")
    fi
    if [[ "$COMMAND_NAME" == "history" ]]; then
        MHC_ARGS+=(--shards "$SHARDS" --shard "$SHARD")
        if [[ "$MERGE_ONLY" == "true" ]]; then
            MHC_ARGS+=(--merge-only)
        fi
    fi
    if [[ -n "$PROJECTS_CSV" ]]; then
        if [[ "$SHARDS" -gt 1 ]]; then
            MHC_ARGS+=(--project "$PROJECT")
        elif [[ -n "$PROJECT" ]]; then
            MHC_ARGS+=(--project "$PROJECT")
        else
            MHC_ARGS+=(--projects "$PROJECTS_CSV")
        fi
    elif [[ -n "$PROJECT_RANGE" ]]; then
        MHC_ARGS+=(--project-range "$PROJECT_RANGE")
    fi

    srun mhc "${MHC_ARGS[@]}"
    echo "Task finished on $(hostname) at $(date) for tool name $TOOL_NAME, project selection ${PROJECT:-$PROJECTS_CSV$PROJECT_RANGE}, shard $SHARD/$SHARDS"
fi
