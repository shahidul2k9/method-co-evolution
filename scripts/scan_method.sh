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

: "${ME_CACHE_DIRECTORY:?ME_CACHE_DIRECTORY must be set in .env}"

mhc scan-method \
    --cache-directory "$ME_CACHE_DIRECTORY" \
    --repository-directory "$ME_CACHE_DIRECTORY/repository" \
    --data-directory "$ME_CACHE_DIRECTORY/data" \
    --jar-directory "$ME_CACHE_DIRECTORY/jar" \
    --java-options "-Xmx2g -Dlogback.configurationFile=$ME_CACHE_DIRECTORY/config/logback.xml" \
    --project-range "1:" \
    --replace
