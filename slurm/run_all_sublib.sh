#!/usr/bin/env bash
#SBATCH --job-name=parse_subsample_all
#SBATCH --partition=day
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=24:00:00
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

if [[ "$#" -ne 5 ]]; then
  echo "Usage: $0 <run_id> <sublib_idx> <fraction> <seed> <is_reference>" >&2
  exit 1
fi

run_id="$1"
sublib_idx="$2"
fraction="$3"
seed="$4"
is_reference="$5"

ensure_dirs
activate_conda_env "${SPLIT_PIPE_CONDA_ENV}"

run_dir="${RUNS_DIR}/${run_id}"
mkdir -p "${run_dir}" "${run_dir}/input/sublib_${sublib_idx}" "${run_dir}/sampling" "${run_dir}/.done"

done_flag="${run_dir}/.done/all_sublib_${sublib_idx}.done"
if [[ -f "${done_flag}" ]]; then
  echo "Skipping ${run_id} sublib_${sublib_idx}; done marker present"
  exit 0
fi

meta_json="${run_dir}/run_meta.json"
if [[ ! -f "${meta_json}" ]]; then
  python "${PROJECT_ROOT}/scripts/capture_run_meta.py" \
    --out "${meta_json}" \
    --run-id "${run_id}" \
    --fraction "${fraction}" \
    --replicate "NA" \
    --seed "${seed}" \
    --is-reference "${is_reference}"
fi

fastq_row="$(get_sublib_fastqs "${sublib_idx}")"
if [[ -z "${fastq_row}" ]]; then
  echo "No FASTQ row for sublib ${sublib_idx} in ${SUBLIB_TSV}" >&2
  exit 1
fi

orig_fq1_rel="$(printf '%s' "${fastq_row}" | cut -f1)"
orig_fq2_rel="$(printf '%s' "${fastq_row}" | cut -f2)"
orig_fq1="$(abs_path_from_root "${orig_fq1_rel}")"
orig_fq2="$(abs_path_from_root "${orig_fq2_rel}")"

in_fq1="${run_dir}/input/sublib_${sublib_idx}/R1.fastq.gz"
in_fq2="${run_dir}/input/sublib_${sublib_idx}/R2.fastq.gz"
stats_tsv="${run_dir}/sampling/sublib_${sublib_idx}.tsv"

need_sampling=0
if [[ ! -f "${stats_tsv}" ]]; then
  need_sampling=1
fi

if [[ "${need_sampling}" -eq 0 ]]; then
  # Cached stats can exist while staged files are missing or point to old source paths.
  if [[ ! -r "${in_fq1}" || ! -r "${in_fq2}" ]]; then
    need_sampling=1
  else
    cached_fq1="$(awk -F '\t' 'NR==2 {print $1}' "${stats_tsv}")"
    cached_fq2="$(awk -F '\t' 'NR==2 {print $2}' "${stats_tsv}")"
    if [[ "${cached_fq1}" != "${orig_fq1}" || "${cached_fq2}" != "${orig_fq2}" ]]; then
      need_sampling=1
    fi
  fi
fi

if [[ "${need_sampling}" -eq 1 ]]; then
  rm -f "${in_fq1}" "${in_fq2}" "${stats_tsv}"
  if [[ "${is_reference}" == "1" ]]; then
    python "${PROJECT_ROOT}/scripts/subsample_fastq_pairs.py" \
      --fq1 "${orig_fq1}" \
      --fq2 "${orig_fq2}" \
      --out1 "${in_fq1}" \
      --out2 "${in_fq2}" \
      --stats-out "${stats_tsv}" \
      --fraction "${fraction}" \
      --seed "${seed}" \
      --threads "${SLURM_CPUS_PER_TASK:-1}" \
      --check-prefix 10000 \
      --passthrough
  else
    python "${PROJECT_ROOT}/scripts/subsample_fastq_pairs.py" \
      --fq1 "${orig_fq1}" \
      --fq2 "${orig_fq2}" \
      --out1 "${in_fq1}" \
      --out2 "${in_fq2}" \
      --stats-out "${stats_tsv}" \
      --fraction "${fraction}" \
      --seed "${seed}" \
      --threads "${SLURM_CPUS_PER_TASK:-1}" \
      --check-prefix 10000
  fi
fi

if [[ ! -d "${GENOME_DIR}" ]]; then
  echo "GENOME_DIR not found: ${GENOME_DIR}" >&2
  exit 1
fi

out_dir="${run_dir}/sublib_${sublib_idx}"
split-pipe \
  --mode all \
  --chemistry v3 \
  --kit WT \
  --nthreads "${SLURM_CPUS_PER_TASK:-1}" \
  --genome_dir "${GENOME_DIR}" \
  --fq1 "${in_fq1}" \
  --fq2 "${in_fq2}" \
  --output_dir "${out_dir}" \
  --sample xcond_1 A1-B4 \
  --sample xcond_2 B5-C8 \
  --sample xcond_3 C9-D12

if ! ls "${out_dir}"/*_analysis_summary.html >/dev/null 2>&1; then
  echo "Expected split-pipe report HTML files not found in ${out_dir}" >&2
  exit 1
fi

touch "${done_flag}"
