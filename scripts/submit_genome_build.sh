#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../slurm/common.sh"

if ! command -v sbatch >/dev/null 2>&1; then
  echo "sbatch not found in PATH" >&2
  exit 1
fi

jid="$(sbatch --parsable --requeue \
  --partition "${BUILD_PARTITION}" \
  --cpus-per-task "${BUILD_CPUS}" \
  --mem "${BUILD_MEM}" \
  --time "${BUILD_TIME}" \
  --job-name parse_splitpipe_mkref \
  "${PROJECT_ROOT}/slurm/build_genome_hg38_ensembl109.sh")"

echo "Submitted genome build job: ${jid}"
echo "Expected GENOME_DIR: ${GENOME_OUT_DIR}"
echo "After completion, set GENOME_DIR=${GENOME_OUT_DIR} in config/pipeline.env"
