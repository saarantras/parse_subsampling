#!/usr/bin/env bash
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
  --main-fig "${FIGURES_DIR}/reads_vs_identity_corr.png" \
  --class-fig "${FIGURES_DIR}/reads_vs_identity_corr_by_class.png"
