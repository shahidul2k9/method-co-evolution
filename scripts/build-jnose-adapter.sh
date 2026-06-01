#!/usr/bin/env bash
set -euo pipefail

# Pass --load-modules to load Java and Maven environment modules before building.
LOAD_MODULES=false
for arg in "$@"; do
  if [[ "${arg}" == "--load-modules" ]]; then
    LOAD_MODULES=true
  fi
done

if [[ "${LOAD_MODULES}" == true ]]; then
  module load java/21.0.1
  module load maven
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

WORKSPACE_DIRECTORY="${ME_WORKSPACE_DIRECTORY:-workspace}"
if [[ "${WORKSPACE_DIRECTORY}" != /* ]]; then
  WORKSPACE_DIRECTORY="${ROOT_DIR}/${WORKSPACE_DIRECTORY}"
fi

JAR_DIRECTORY="${WORKSPACE_DIRECTORY}/jar"
JNOSE_ADAPTER_DIR="${ROOT_DIR}/jnose-adapter"

echo "Building jnose-adapter..."
(cd "${JNOSE_ADAPTER_DIR}" && mvn clean install -DskipTests)

JAR_FILE="$(find "${JNOSE_ADAPTER_DIR}/target" -maxdepth 1 -type f -name 'jnose-adapter*.jar' | head -n 1)"
if [[ -z "${JAR_FILE}" ]]; then
  echo "No jnose-adapter jar found in ${JNOSE_ADAPTER_DIR}/target" >&2
  exit 1
fi

mkdir -p "${JAR_DIRECTORY}"
cp "${JAR_FILE}" "${JAR_DIRECTORY}/"

echo "Copied $(basename "${JAR_FILE}") to ${JAR_DIRECTORY}"
