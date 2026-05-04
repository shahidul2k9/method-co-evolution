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

: "${ME_PROJECT_DIRECTORY:?ME_PROJECT_DIRECTORY must be set in .env}"
: "${ME_CACHE_DIRECTORY:?ME_CACHE_DIRECTORY must be set in .env}"

ptc-testlinker testlinker \
    --stage all \
    --project-directory "$ME_PROJECT_DIRECTORY" \
    --cache-directory "$ME_CACHE_DIRECTORY" \
    --tokenizer-mode auto \
    --include-labels \
    --mapping-mode testlinker-heuristics \
    --project-range "2:" \
    --order-production-method testlinker \
    --replace \
    --model-name-or-path Salesforce/codet5-base
