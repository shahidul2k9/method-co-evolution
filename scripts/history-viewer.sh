#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi

: "${ME_WORKSPACE_DIRECTORY:?ME_WORKSPACE_DIRECTORY must be set in .env}"
ME_EXPERIMENT_NAME="${ME_EXPERIMENT_NAME:-main}"

ptc-history-viewer serve \
    --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
    --experiment-name "$ME_EXPERIMENT_NAME" \
    --host 127.0.0.1 \
    --port 8765
