#!/usr/bin/env bash
#SBATCH --job-name=parse_splitpipe_mkref
#SBATCH --partition=day
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=5
#SBATCH --mem=120G
#SBATCH --time=04:00:00
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

activate_conda_env "${SPLIT_PIPE_CONDA_ENV}"

if ! command -v wget >/dev/null 2>&1; then
  echo "wget not found in PATH" >&2
  exit 1
fi

if ! command -v split-pipe >/dev/null 2>&1; then
  echo "split-pipe not found in PATH after activating ${SPLIT_PIPE_CONDA_ENV}" >&2
  exit 1
fi

DOWNLOAD_DIR="${GENOME_BUILD_ROOT}/downloads"
MARKER_FILE="${GENOME_OUT_DIR}/.mkref_complete"
META_FILE="${GENOME_OUT_DIR}/build_meta.tsv"

if [[ -f "${MARKER_FILE}" ]]; then
  echo "Genome reference already built; marker found: ${MARKER_FILE}"
  echo "GENOME_DIR=${GENOME_OUT_DIR}"
  exit 0
fi

mkdir -p "${DOWNLOAD_DIR}" "${GENOME_OUT_DIR}"

FASTA_FILE="$(basename "${GENOME_FASTA_URL}")"
GTF_FILE="$(basename "${GENOME_GTF_URL}")"
FASTA_PATH="${DOWNLOAD_DIR}/${FASTA_FILE}"
GTF_PATH="${DOWNLOAD_DIR}/${GTF_FILE}"

(
  cd "${DOWNLOAD_DIR}"
  wget -nc "${GENOME_FASTA_URL}"
  wget -nc "${GENOME_GTF_URL}"
)

if [[ ! -f "${FASTA_PATH}" ]]; then
  echo "Missing FASTA after download: ${FASTA_PATH}" >&2
  exit 1
fi
if [[ ! -f "${GTF_PATH}" ]]; then
  echo "Missing GTF after download: ${GTF_PATH}" >&2
  exit 1
fi

split-pipe \
  --mode mkref \
  --genome_name "${GENOME_NAME}" \
  --fasta "${FASTA_PATH}" \
  --genes "${GTF_PATH}" \
  --output_dir "${GENOME_OUT_DIR}"

touch "${MARKER_FILE}"

{
  printf 'field\tvalue\n'
  printf 'timestamp_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'hostname\t%s\n' "$(hostname)"
  printf 'user\t%s\n' "${USER}"
  printf 'slurm_job_id\t%s\n' "${SLURM_JOB_ID:-NA}"
  printf 'conda_env\t%s\n' "${CONDA_DEFAULT_ENV:-NA}"
  printf 'split_pipe_version\t%s\n' "$(split-pipe --version 2>/dev/null | head -n 1 || echo NA)"
  printf 'genome_name\t%s\n' "${GENOME_NAME}"
  printf 'genome_build_root\t%s\n' "${GENOME_BUILD_ROOT}"
  printf 'genome_out_dir\t%s\n' "${GENOME_OUT_DIR}"
  printf 'genome_fasta_url\t%s\n' "${GENOME_FASTA_URL}"
  printf 'genome_gtf_url\t%s\n' "${GENOME_GTF_URL}"
  printf 'genome_fasta_path\t%s\n' "${FASTA_PATH}"
  printf 'genome_gtf_path\t%s\n' "${GTF_PATH}"
} > "${META_FILE}"

echo "Genome build complete."
echo "GENOME_DIR=${GENOME_OUT_DIR}"
