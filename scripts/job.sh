#!/bin/bash
#SBATCH --job-name=MHC
#SBATCH --output=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/workspace/log/job/%x.%A_%a.out
#SBATCH --error=$HOME/projects/$SLURM_ACCOUNT/$USER/method-co-evolution/workspace/log/job/%x.%A_%a.err
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  job.sh --command method-history --tool-name codeShovel --java-options "-Xmx4g" --timeout-seconds 1800 --merge-threshold 10000 --command-options "--flag value" --projects "checkstyle,commons-io"
  job.sh --command method-history --tool-name codeShovel --merge-only --projects "checkstyle,commons-io"
  job.sh --command method-history --tool-name codeShovel --shards 10
  job.sh --command method-code --projects "commons-io"
  job.sh --command llm-m2m-link --api-type huggingface --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --prompt-format text --batch-size 1 --max-new-tokens 256 --resume none --projects "commons-io" --input-kind t2p
  job.sh --command llm-m2m-link --api-type huggingface --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --batch-size 1 --resume error --projects "commons-io" --input-kind t2p
  job.sh --command llm-m2m-link --stage parse --model-name-or-path openai/gpt-oss-20b --short-model-name gpt_oss_20b --projects "commons-io"
  job.sh --command testlinker --stage all --projects "commons-io" --top-k 1

Options:
  --command               Command to run: method-history, method-callgraph, method-scan, class-scan, method-code, artifact-update, method-complexity, llm-m2m-link, testlinker
  --tool-name             Tool name for non-LLM commands
  --java-options          Optional JVM arguments for Java-backed commands, e.g. "-Xmx4g"
  --timeout-seconds       Optional method-history command timeout in seconds (default: 30*60 = 1800)
  --merge-threshold       History JSON merge threshold; for scan/code commands, pending rows before flushing (default: 10000; history negative disables final merge; scan/code 0/-1 disables threshold trigger)
  --merge-interval-seconds Optional cache flush interval for method-scan, class-scan, method-code, and method-callgraph (default: 900; 0 disables time trigger)
  --merge-only            Merge existing loose history JSON files without generating new history
  --retry-errors          Whether method-scan, class-scan, method-code, and method-callgraph retry previous __error_marker__ rows (default: true)
  --artifact-config-path  Artifact detection YAML file or directory
  --command-options       Optional extra arguments forwarded to the selected command
  --stage                 LLM stage: execute or parse (default: execute)
  --api-type              LLM provider API type: auto, huggingface, or openai-responses (default: auto)
  --model-name-or-path    Hugging Face model id or local path for llm-m2m-link
  --short-model-name      Short model directory name for llm-m2m-link outputs
  --prompt-format         LLM prompt format: auto, json, or text (default: auto)
  --batch-size            LLM grouped case batch size (default: 4)
  --max-new-tokens        LLM generation cap per grouped case (default: 256)
  --resume                Resume mode: none, all, or error (default: none)
  --project               Single project name
  --projects              Comma-separated project list for the array job
  --project-index         Python-style project index or slice from repository.csv, for example 10, -1, 10:20, :10, 10:, or :
  --shards                Total method-history, method-scan, class-scan, method-code, or method-callgraph shards per project (default: 1)
  --job-index-shift       Offset added to SLURM_ARRAY_TASK_ID before deriving project/shard indexes (default: 0)
  --input-kind            LLM input kind: t2p or p2t (default: t2p)
  --top-k                 TestLinker top-k invocation count (default: 1)
  --workspace-directory       Relative or absolute cache directory (default: .cache)
  --history-directory     Relative or absolute method history directory (default: ME_HISTORY_DIRECTORY or $HOME/scratch/$USER/method-co-evolution/workspace)
  --data-directory        Relative or absolute data directory (default: <workspace-directory>/data)
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
MERGE_INTERVAL_SECONDS="900"
MERGE_ONLY="false"
RETRY_ERRORS="true"
COMMAND_OPTIONS=""
STAGE="execute"
API_TYPE="auto"
MODEL_NAME_OR_PATH=""
SHORT_MODEL_NAME=""
PROMPT_FORMAT="auto"
BATCH_SIZE="4"
MAX_NEW_TOKENS="256"
RESUME_MODE="none"
PROJECT_NAME=""
PROJECTS_CSV=""
PROJECT_INDEX=""
SHARDS="1"
JOB_INDEX_SHIFT="0"
INPUT_KIND="t2p"
TOP_K="1"
WORKSPACE_DIRECTORY="$PROJECT_DIRECTORY/workspace"
HISTORY_DIRECTORY="${ME_HISTORY_DIRECTORY:-}"
DATA_DIRECTORY=""
ARTIFACT_CONFIG_PATH=""

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
        --merge-interval-seconds)
            MERGE_INTERVAL_SECONDS="$2"
            shift 2
            ;;
        --merge-interval-seconds=*)
            MERGE_INTERVAL_SECONDS="${1#*=}"
            shift
            ;;
        --merge-only)
            MERGE_ONLY="true"
            shift
            ;;
        --retry-errors)
            if [[ $# -lt 2 || "$2" == --* ]]; then
                RETRY_ERRORS="true"
                shift
            else
                RETRY_ERRORS="$2"
                shift 2
            fi
            ;;
        --retry-errors=*)
            RETRY_ERRORS="${1#*=}"
            shift
            ;;
        --artifact-config-path)
            ARTIFACT_CONFIG_PATH="$2"
            shift 2
            ;;
        --artifact-config-path=*)
            ARTIFACT_CONFIG_PATH="${1#*=}"
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
        --project)
            PROJECT_NAME="$2"
            shift 2
            ;;
        --projects)
            PROJECTS_CSV="$2"
            shift 2
            ;;
        --project-index)
            PROJECT_INDEX="$2"
            shift 2
            ;;
        --shards)
            SHARDS="$2"
            shift 2
            ;;
        --job-index-shift)
            JOB_INDEX_SHIFT="$2"
            shift 2
            ;;
        --input-kind)
            INPUT_KIND="$2"
            shift 2
            ;;
        --top-k)
            TOP_K="$2"
            shift 2
            ;;
        --workspace-directory)
            WORKSPACE_DIRECTORY="$2"
            shift 2
            ;;
        --history-directory)
            HISTORY_DIRECTORY="$2"
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
    DATA_DIRECTORY="$WORKSPACE_DIRECTORY/data"
fi

if [[ -z "$HISTORY_DIRECTORY" ]]; then
    HISTORY_DIRECTORY="$HOME/scratch/$USER/method-co-evolution/workspace/history"
fi

if [[ -z "$COMMAND_NAME" ]]; then
    echo "Error: --command is required."
    usage
    exit 1
fi

case "$COMMAND_NAME" in
    history)
        COMMAND_NAME="method-history"
        ;;
    call-graph)
        COMMAND_NAME="method-callgraph"
        ;;
    scan-method)
        COMMAND_NAME="method-scan"
        ;;
    scan-class)
        COMMAND_NAME="class-scan"
        ;;
esac

SELECTION_COUNT=0
if [[ -n "$PROJECT_NAME" ]]; then
    SELECTION_COUNT=$((SELECTION_COUNT + 1))
fi
if [[ -n "$PROJECTS_CSV" ]]; then
    SELECTION_COUNT=$((SELECTION_COUNT + 1))
fi
if [[ -n "$PROJECT_INDEX" ]]; then
    SELECTION_COUNT=$((SELECTION_COUNT + 1))
fi

if ! [[ "$SHARDS" =~ ^[0-9]+$ ]] || [[ "$SHARDS" -le 0 ]]; then
    echo "Error: --shards must be a positive integer."
    usage
    exit 1
fi

if ! [[ "$JOB_INDEX_SHIFT" =~ ^[0-9]+$ ]]; then
    echo "Error: --job-index-shift must be a non-negative integer."
    usage
    exit 1
fi

if [[ "$SELECTION_COUNT" -eq 0 && "$COMMAND_NAME" != "index" \
    && ! ( "$COMMAND_NAME" == "method-history" && "$SHARDS" -gt 1 ) \
    && -z "${SLURM_ARRAY_TASK_ID:-}" ]]; then
    echo "Error: one of --project, --projects, or --project-index is required."
    usage
    exit 1
fi

if [[ -n "$PROJECT_NAME" && -n "$PROJECTS_CSV" ]]; then
    echo "Error: use either --project or --projects, not both."
    usage
    exit 1
fi

if [[ "$SHARDS" -eq 1 && -n "$PROJECT_INDEX" && ( -n "$PROJECT_NAME" || -n "$PROJECTS_CSV" ) ]]; then
    echo "Error: use --project-index by itself unless --shards is greater than 1."
    usage
    exit 1
fi

if ! [[ "$MERGE_THRESHOLD" =~ ^-?[0-9]+$ ]]; then
    echo "Error: --merge-threshold must be an integer."
    usage
    exit 1
fi

if ! [[ "$MERGE_INTERVAL_SECONDS" =~ ^-?[0-9]+$ ]]; then
    echo "Error: --merge-interval-seconds must be an integer."
    usage
    exit 1
fi

RETRY_ERRORS_NORMALIZED="$(printf '%s' "$RETRY_ERRORS" | tr '[:upper:]' '[:lower:]')"
case "$RETRY_ERRORS_NORMALIZED" in
    true|false)
        RETRY_ERRORS="$RETRY_ERRORS_NORMALIZED"
        ;;
    *)
        echo "Error: --retry-errors must be true or false."
        usage
        exit 1
        ;;
esac

if [[ "$SHARDS" -gt 1 && "$COMMAND_NAME" != "method-history" && "$COMMAND_NAME" != "method-callgraph" && "$COMMAND_NAME" != "method-scan" && "$COMMAND_NAME" != "class-scan" && "$COMMAND_NAME" != "method-code" ]]; then
    echo "Error: --shards greater than 1 is supported only for method-history, method-scan, class-scan, method-code, and method-callgraph."
    usage
    exit 1
fi

if [[ "$SHARDS" -gt 1 && -n "$PROJECT_INDEX" ]]; then
    echo "Error: --project-index is derived from SLURM_ARRAY_TASK_ID in shard mode."
    usage
    exit 1
fi

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    if [[ -z "$MODEL_NAME_OR_PATH" ]]; then
        echo "Error: --model-name-or-path is required for $COMMAND_NAME."
        usage
        exit 1
    fi
elif [[ "$COMMAND_NAME" != "method-scan" && "$COMMAND_NAME" != "class-scan" && "$COMMAND_NAME" != "method-code" && "$COMMAND_NAME" != "artifact-update" && "$COMMAND_NAME" != "index" && "$COMMAND_NAME" != "testlinker" ]]; then
    if [[ -z "$TOOL_NAME" ]]; then
        echo "Error: --tool-name is required for $COMMAND_NAME."
        usage
        exit 1
    fi
fi

if ! [[ "$TOP_K" =~ ^[0-9]+$ ]] || [[ "$TOP_K" -le 0 ]]; then
    echo "Error: --top-k must be a positive integer."
    usage
    exit 1
fi

cd "$PROJECT_DIRECTORY"
source "$PROJECT_DIRECTORY/.venv/bin/activate"

# Prefer the explicit --java-options value over cluster/module-injected JVM flags.
if [[ -n "$JAVA_OPTIONS" ]]; then
    unset JAVA_TOOL_OPTIONS _JAVA_OPTIONS
fi

PROJECT=""
SHARD="1"
ARRAY_TASK_ID=""

if [[ "$COMMAND_NAME" != "index" ]]; then
    if [[ -n "${SLURM_ARRAY_TASK_ID:-}" ]]; then
        if ! [[ "$SLURM_ARRAY_TASK_ID" =~ ^[0-9]+$ ]]; then
            echo "Invalid SLURM_ARRAY_TASK_ID: ${SLURM_ARRAY_TASK_ID:-unset}"
            exit 1
        fi
        ARRAY_TASK_ID=$((SLURM_ARRAY_TASK_ID + JOB_INDEX_SHIFT))
    fi
    if [[ "$SHARDS" -gt 1 ]]; then
        if [[ -z "$ARRAY_TASK_ID" ]]; then
            echo "Invalid SLURM_ARRAY_TASK_ID for shard mode: ${SLURM_ARRAY_TASK_ID:-unset}"
            exit 1
        fi
        PROJECT_INDEX=$((ARRAY_TASK_ID / SHARDS))
        SHARD=$((ARRAY_TASK_ID % SHARDS + 1))
    elif [[ -n "$PROJECT_NAME" ]]; then
        PROJECT="$PROJECT_NAME"
    elif [[ -n "$PROJECTS_CSV" ]]; then
        IFS=',' read -r -a PROJECTS <<< "$PROJECTS_CSV"
        if [[ -z "$ARRAY_TASK_ID" || $ARRAY_TASK_ID -le 0 || $ARRAY_TASK_ID -gt ${#PROJECTS[@]} ]]; then
            echo "Invalid SLURM_ARRAY_TASK_ID: ${SLURM_ARRAY_TASK_ID:-unset}"
            exit 1
        fi
        IDX=$((ARRAY_TASK_ID - 1))
        PROJECT=${PROJECTS[$IDX]}
    elif [[ -z "$PROJECT_INDEX" && -n "$ARRAY_TASK_ID" ]]; then
        PROJECT_INDEX="$ARRAY_TASK_ID"
    fi
fi

if [[ "$COMMAND_NAME" == "llm-m2m-link" ]]; then
    if [[ "$RESUME_MODE" != "none" && "$RESUME_MODE" != "all" && "$RESUME_MODE" != "error" ]]; then
        echo "Error: --resume must be one of: none, all, error"
        usage
        exit 1
    fi
    srun ptc-llm llm-m2m-link \
        --workspace-directory "$WORKSPACE_DIRECTORY" \
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
elif [[ "$COMMAND_NAME" == "testlinker" ]]; then
    TESTLINKER_ARGS=(
        testlinker
        --workspace-directory "$WORKSPACE_DIRECTORY"
        --stage "$STAGE"
        --top-k "$TOP_K"
        --testlinker-directory "$WORKSPACE_DIRECTORY/testlinker"
        --checkpoint "best-acc_and_f1"
        --model-mode "codet5"
        --tokenizer-mode "original"
        --include-labels
    )
    if [[ -n "$PROJECT" ]]; then
        TESTLINKER_ARGS+=(--project "$PROJECT")
    elif [[ -n "$PROJECTS_CSV" ]]; then
        TESTLINKER_ARGS+=(--projects "$PROJECTS_CSV")
    elif [[ -n "$PROJECT_INDEX" ]]; then
        TESTLINKER_ARGS+=(--project-index "$PROJECT_INDEX")
    fi
    srun ptc-testlinker "${TESTLINKER_ARGS[@]}"
    echo "Task finished on $(hostname) at $(date) for TestLinker stage $STAGE, project $PROJECT, and top-k $TOP_K"
else
    MHC_ARGS=(
        "$COMMAND_NAME"
        --workspace-directory "$WORKSPACE_DIRECTORY"
        --history-directory "$HISTORY_DIRECTORY"
        --repository-directory "$SLURM_TMPDIR/repository"
        --data-directory "$DATA_DIRECTORY"
        --jar-directory "$WORKSPACE_DIRECTORY/jar"
        --timeout-seconds "$TIMEOUT_SECONDS"
        --merge-threshold "$MERGE_THRESHOLD"
    )
    if [[ "$COMMAND_NAME" == "method-scan" || "$COMMAND_NAME" == "class-scan" || "$COMMAND_NAME" == "method-code" || "$COMMAND_NAME" == "method-callgraph" ]]; then
        MHC_ARGS+=(--merge-interval-seconds "$MERGE_INTERVAL_SECONDS")
    fi
    if [[ -n "$TOOL_NAME" ]]; then
        MHC_ARGS+=(--tool-name "$TOOL_NAME")
    fi
    if [[ -n "$JAVA_OPTIONS" ]]; then
        MHC_ARGS+=(--java-options="$JAVA_OPTIONS")
    fi
    if [[ -n "$COMMAND_OPTIONS" ]]; then
        MHC_ARGS+=(--command-options "$COMMAND_OPTIONS")
    fi
    if [[ "$COMMAND_NAME" == "method-history" || "$COMMAND_NAME" == "method-scan" || "$COMMAND_NAME" == "class-scan" || "$COMMAND_NAME" == "method-code" || "$COMMAND_NAME" == "method-callgraph" ]]; then
        MHC_ARGS+=(--shards "$SHARDS" --shard "$SHARD")
        if [[ "$MERGE_ONLY" == "true" ]]; then
            MHC_ARGS+=(--merge-only)
        fi
    fi
    if [[ "$COMMAND_NAME" == "method-scan" || "$COMMAND_NAME" == "class-scan" || "$COMMAND_NAME" == "method-code" || "$COMMAND_NAME" == "method-callgraph" ]]; then
        MHC_ARGS+=(--retry-errors "$RETRY_ERRORS")
    fi
    if [[ -n "$ARTIFACT_CONFIG_PATH" ]]; then
        MHC_ARGS+=(--artifact-config-path "$ARTIFACT_CONFIG_PATH")
    fi
    if [[ -n "$PROJECT_NAME" ]]; then
        MHC_ARGS+=(--project "$PROJECT_NAME")
    elif [[ -n "$PROJECT" ]]; then
        MHC_ARGS+=(--project "$PROJECT")
    elif [[ -n "$PROJECTS_CSV" ]]; then
        MHC_ARGS+=(--projects "$PROJECTS_CSV")
    fi
    if [[ -n "$PROJECT_INDEX" ]]; then
        MHC_ARGS+=(--project-index "$PROJECT_INDEX")
    fi

    echo "Resolved Java options: ${JAVA_OPTIONS:-unset}"
    srun mhc "${MHC_ARGS[@]}"
    echo "Task finished on $(hostname) at $(date) for tool name $TOOL_NAME, project selection ${PROJECT:-$PROJECTS_CSV$PROJECT_INDEX}, shard $SHARD/$SHARDS"
fi
