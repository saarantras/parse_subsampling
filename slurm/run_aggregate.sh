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
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

ensure_dirs
activate_conda_env "${ANALYSIS_CONDA_ENV}"

python "${PROJECT_ROOT}/scripts/aggregate_metrics.py" \
  --grid "${GRID_TSV}" \
  --runs-dir "${RUNS_DIR}" \
  --per-run-out "${RESULTS_DIR}/per_run_metrics.tsv" \
  --curve-out "${RESULTS_DIR}/identity_curve.tsv" \
  --main-fig "${FIGURES_DIR}/reads_vs_identity_accuracy.png" \
  --class-fig "${FIGURES_DIR}/reads_vs_identity_accuracy_by_class.png"
