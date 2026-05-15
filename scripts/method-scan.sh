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

mhc method-scan \
    --workspace-directory "$ME_WORKSPACE_DIRECTORY" \
    --repository-directory "$ME_WORKSPACE_DIRECTORY/repository" \
    --data-directory "$ME_WORKSPACE_DIRECTORY/data" \
    --jar-directory "$ME_WORKSPACE_DIRECTORY/jar" \
    --artifact-config-path "$ME_WORKSPACE_DIRECTORY/config/artifact-detection" \
    --java-options "-Xmx4g -Xss16m -Dlogback.configurationFile=$ME_WORKSPACE_DIRECTORY/config/logback.xml" \
    --project-index "47" \
    --retry-errors true \
    --merge-threshold 500 \
    --merge-interval-seconds 0
