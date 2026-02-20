#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

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

if [[ ! -f "${stats_tsv}" ]]; then
  if [[ "${is_reference}" == "1" ]]; then
    python "${PROJECT_ROOT}/scripts/subsample_fastq_pairs.py" \
      --fq1 "${orig_fq1}" \
      --fq2 "${orig_fq2}" \
      --out1 "${in_fq1}" \
      --out2 "${in_fq2}" \
      --stats-out "${stats_tsv}" \
      --fraction "${fraction}" \
      --seed "${seed}" \
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
  --chemistry v2 \
  --genome_dir "${GENOME_DIR}" \
  --fq1 "${in_fq1}" \
  --fq2 "${in_fq2}" \
  --output_dir "${out_dir}" \
  --sample xcond_1 A1-A2 \
  --sample xcond_2 A3-A7 \
  --sample xcond_3 A8-A12

touch "${done_flag}"
