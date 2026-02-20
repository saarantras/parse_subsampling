#!/usr/bin/env bash
#SBATCH --job-name=parse_subsample_aggregate
#SBATCH --partition=day
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:30:00
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

ensure_dirs
activate_conda_env "${ANALYSIS_CONDA_ENV}"

python "${PROJECT_ROOT}/scripts/aggregate_metrics.py" \
  --grid "${GRID_TSV}" \
  --runs-dir "${RUNS_DIR}" \
  --per-run-out "${RESULTS_DIR}/per_run_metrics.tsv" \
  --curve-out "${RESULTS_DIR}/identity_curve.tsv" \
  --main-fig "${FIGURES_DIR}/reads_vs_identity_accuracy.png" \
  --class-fig "${FIGURES_DIR}/reads_vs_identity_accuracy_by_class.png"
