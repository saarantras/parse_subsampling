#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 <run_id> <fraction> <replicate>" >&2
  exit 1
fi

run_id="$1"
fraction="$2"
replicate="$3"

ensure_dirs
activate_conda_env "${ANALYSIS_CONDA_ENV}"

run_dir="${RUNS_DIR}/${run_id}"
mkdir -p "${run_dir}/.done"
done_flag="${run_dir}/.done/score.done"
if [[ -f "${done_flag}" ]]; then
  echo "Skipping score for ${run_id}; done marker present"
  exit 0
fi

python "${PROJECT_ROOT}/scripts/score_identity.py" \
  --run-id "${run_id}" \
  --fraction "${fraction}" \
  --replicate "${replicate}" \
  --run-dir "${run_dir}" \
  --reference-run-dir "${RUNS_DIR}/ref_full" \
  --sampling-dir "${run_dir}/sampling" \
  --output-tsv "${run_dir}/score_metrics.tsv"

touch "${done_flag}"
