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
ME_TEST_SMELL_STAGE="${ME_TEST_SMELL_STAGE:-all}"
ME_TEST_SMELL_CALLGRAPH_DIR="${ME_TEST_SMELL_CALLGRAPH_DIR:-callgraph}"
ME_TEST_SMELL_PROJECT_INDEX="${ME_TEST_SMELL_PROJECT_INDEX:-:}"
MHC_BIN="${MHC_BIN:-$SCRIPT_DIR/../.venv/bin/mhc}"

"$MHC_BIN" test-smell \
    --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
    --experiment-name "$ME_EXPERIMENT_NAME" \
    --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
    --tool-name jnose \
    --stage "$ME_TEST_SMELL_STAGE" \
    --callgraph-dir "$ME_TEST_SMELL_CALLGRAPH_DIR" \
    --project-index "$ME_TEST_SMELL_PROJECT_INDEX"
