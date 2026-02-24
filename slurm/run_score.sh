#!/usr/bin/env bash
#SBATCH --job-name=parse_subsample_score
#SBATCH --partition=day
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --requeue
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SH="${SCRIPT_DIR}/common.sh"
if [[ ! -f "${COMMON_SH}" ]]; then
  root_hint="${PROJECT_ROOT:-${SLURM_SUBMIT_DIR:-}}"
  if [[ -n "${root_hint}" ]]; then
    COMMON_SH="${root_hint}/slurm/common.sh"
  fi
fi
if [[ ! -f "${COMMON_SH}" ]]; then
  echo "Could not locate slurm/common.sh. Set PROJECT_ROOT or submit from repo root." >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${COMMON_SH}"

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
