#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GRID_TSV="${GRID_TSV:-${PROJECT_ROOT}/config/subsample_grid.tsv}"
SUBLIB_TSV="${SUBLIB_TSV:-${PROJECT_ROOT}/config/sublibraries.tsv}"
RUNS_DIR="${RUNS_DIR:-${PROJECT_ROOT}/runs}"
RESULTS_DIR="${RESULTS_DIR:-${PROJECT_ROOT}/results}"
FIGURES_DIR="${FIGURES_DIR:-${PROJECT_ROOT}/figures}"

if [[ -f "${PROJECT_ROOT}/config/pipeline.env" ]]; then
  # shellcheck source=/dev/null
  source "${PROJECT_ROOT}/config/pipeline.env"
fi

GENOME_DIR="${GENOME_DIR:-/home/mcn26/palmer_scratch/analysis/genome}"
SPLIT_PIPE_CONDA_ENV="${SPLIT_PIPE_CONDA_ENV:-splitpipe}"
ANALYSIS_CONDA_ENV="${ANALYSIS_CONDA_ENV:-${SPLIT_PIPE_CONDA_ENV}}"

ALL_PARTITION="${ALL_PARTITION:-day}"
COMBINE_PARTITION="${COMBINE_PARTITION:-day}"
SCORE_PARTITION="${SCORE_PARTITION:-day}"
AGG_PARTITION="${AGG_PARTITION:-day}"

ALL_CPUS="${ALL_CPUS:-16}"
ALL_MEM="${ALL_MEM:-96G}"
ALL_TIME="${ALL_TIME:-08:00:00}"

COMBINE_CPUS="${COMBINE_CPUS:-4}"
COMBINE_MEM="${COMBINE_MEM:-32G}"
COMBINE_TIME="${COMBINE_TIME:-01:00:00}"

SCORE_CPUS="${SCORE_CPUS:-4}"
SCORE_MEM="${SCORE_MEM:-32G}"
SCORE_TIME="${SCORE_TIME:-01:00:00}"

AGG_CPUS="${AGG_CPUS:-2}"
AGG_MEM="${AGG_MEM:-16G}"
AGG_TIME="${AGG_TIME:-00:30:00}"

ensure_dirs() {
  mkdir -p "${RUNS_DIR}" "${RESULTS_DIR}" "${FIGURES_DIR}"
}

activate_conda_env() {
  local env_name="$1"

  if [[ -x "${HOME}/fixconda.sh" ]]; then
    "${HOME}/fixconda.sh" || true
  fi

  if command -v module >/dev/null 2>&1; then
    module load miniconda >/dev/null 2>&1 || true
  fi

  if ! command -v conda >/dev/null 2>&1; then
    echo "conda not found in PATH" >&2
    return 1
  fi

  local conda_base
  conda_base="$(conda info --base)"
  # shellcheck source=/dev/null
  source "${conda_base}/etc/profile.d/conda.sh"
  conda activate "${env_name}"
}

abs_path_from_root() {
  local path="$1"
  if [[ "${path}" = /* ]]; then
    printf '%s\n' "${path}"
  else
    printf '%s\n' "${PROJECT_ROOT}/${path}"
  fi
}

get_sublib_fastqs() {
  local sublib_idx="$1"
  awk -F '\t' -v idx="${sublib_idx}" 'NR>1 && $1==idx {print $2"\t"$3; exit}' "${SUBLIB_TSV}"
}

write_run_manifest() {
  local run_id="$1"
  local fraction="$2"
  local replicate="$3"
  local seed="$4"
  local is_reference="$5"

  local run_dir="${RUNS_DIR}/${run_id}"
  mkdir -p "${run_dir}" "${run_dir}/.done"
  cat > "${run_dir}/run_manifest.tsv" <<MANIFEST
run_id\tfraction\treplicate\tseed\tis_reference
${run_id}\t${fraction}\t${replicate}\t${seed}\t${is_reference}
MANIFEST
}
