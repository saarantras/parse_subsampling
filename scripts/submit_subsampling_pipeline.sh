#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/../slurm/common.sh"

smoke_mode=0
force_mode=0
for arg in "$@"; do
  case "${arg}" in
    --smoke) smoke_mode=1 ;;
    --force) force_mode=1 ;;
    *)
      echo "Unknown arg: ${arg}" >&2
      echo "Usage: $0 [--smoke] [--force]" >&2
      exit 1
      ;;
  esac
done

ensure_dirs

if ! command -v sbatch >/dev/null 2>&1; then
  echo "sbatch not found in PATH" >&2
  exit 1
fi

sbatch_common=(--chdir "${PROJECT_ROOT}" --export "ALL,PROJECT_ROOT=${PROJECT_ROOT}")

submission_log="${RESULTS_DIR}/job_submission_$(date +%Y%m%d_%H%M%S).tsv"
echo -e "run_id\tfraction\treplicate\tjob_all_0\tjob_all_1\tjob_combine\tjob_score\tstatus" > "${submission_log}"

declare -a score_job_ids=()
reference_combine_job=""

auto_include_run() {
  local run_id="$1"
  if [[ "${smoke_mode}" -eq 0 ]]; then
    return 0
  fi
  [[ "${run_id}" == "ref_full" || "${run_id}" == "f005_r1" || "${run_id}" == "f050_r1" ]]
}

while IFS=$'\t' read -r run_id fraction replicate seed is_reference; do
  [[ "${run_id}" == "run_id" ]] && continue

  if ! auto_include_run "${run_id}"; then
    continue
  fi

  write_run_manifest "${run_id}" "${fraction}" "${replicate}" "${seed}" "${is_reference}"

  run_dir="${RUNS_DIR}/${run_id}"
  score_done="${run_dir}/.done/score.done"
  if [[ "${force_mode}" -eq 0 && -f "${score_done}" ]]; then
    if [[ "${run_id}" == "ref_full" ]]; then
      if [[ ! -d "${run_dir}/combined" ]]; then
        echo "ref_full score marker exists but combined output is missing: ${run_dir}/combined" >&2
        exit 1
      fi
      reference_combine_job=""
    fi
    echo -e "${run_id}\t${fraction}\t${replicate}\tNA\tNA\tNA\tNA\talready_done" >> "${submission_log}"
    continue
  fi

  jid0="$(sbatch --parsable --requeue \
    "${sbatch_common[@]}" \
    --partition "${ALL_PARTITION}" \
    --cpus-per-task "${ALL_CPUS}" \
    --mem "${ALL_MEM}" \
    --time "${ALL_TIME}" \
    --job-name "pss_a0_${run_id}" \
    "${PROJECT_ROOT}/slurm/run_all_sublib.sh" \
    "${run_id}" "0" "${fraction}" "${seed}" "${is_reference}")"

  jid1="$(sbatch --parsable --requeue \
    "${sbatch_common[@]}" \
    --partition "${ALL_PARTITION}" \
    --cpus-per-task "${ALL_CPUS}" \
    --mem "${ALL_MEM}" \
    --time "${ALL_TIME}" \
    --job-name "pss_a1_${run_id}" \
    "${PROJECT_ROOT}/slurm/run_all_sublib.sh" \
    "${run_id}" "1" "${fraction}" "${seed}" "${is_reference}")"

  jidc="$(sbatch --parsable --requeue \
    "${sbatch_common[@]}" \
    --dependency "afterok:${jid0}:${jid1}" \
    --partition "${COMBINE_PARTITION}" \
    --cpus-per-task "${COMBINE_CPUS}" \
    --mem "${COMBINE_MEM}" \
    --time "${COMBINE_TIME}" \
    --job-name "pss_c_${run_id}" \
    "${PROJECT_ROOT}/slurm/run_combine.sh" \
    "${run_id}")"

  if [[ "${run_id}" == "ref_full" ]]; then
    reference_combine_job="${jidc}"
  fi

  score_dep="afterok:${jidc}"
  if [[ "${run_id}" != "ref_full" && -n "${reference_combine_job}" ]]; then
    score_dep="afterok:${jidc}:${reference_combine_job}"
  fi

  jids="$(sbatch --parsable --requeue \
    "${sbatch_common[@]}" \
    --dependency "${score_dep}" \
    --partition "${SCORE_PARTITION}" \
    --cpus-per-task "${SCORE_CPUS}" \
    --mem "${SCORE_MEM}" \
    --time "${SCORE_TIME}" \
    --job-name "pss_s_${run_id}" \
    "${PROJECT_ROOT}/slurm/run_score.sh" \
    "${run_id}" "${fraction}" "${replicate}")"

  score_job_ids+=("${jids}")
  echo -e "${run_id}\t${fraction}\t${replicate}\t${jid0}\t${jid1}\t${jidc}\t${jids}\tsubmitted" >> "${submission_log}"
done < "${GRID_TSV}"

agg_dependency=()
if [[ "${#score_job_ids[@]}" -gt 0 ]]; then
  dep_str="$(IFS=:; echo "${score_job_ids[*]}")"
  agg_dependency=(--dependency "afterok:${dep_str}")
fi

jid_agg="$(sbatch --parsable --requeue \
  "${sbatch_common[@]}" \
  "${agg_dependency[@]}" \
  --partition "${AGG_PARTITION}" \
  --cpus-per-task "${AGG_CPUS}" \
  --mem "${AGG_MEM}" \
  --time "${AGG_TIME}" \
  --job-name "pss_aggregate" \
  "${PROJECT_ROOT}/slurm/run_aggregate.sh")"

echo -e "aggregate\tNA\tNA\tNA\tNA\tNA\t${jid_agg}\tsubmitted" >> "${submission_log}"

echo "Submission complete. Log: ${submission_log}"
echo "Aggregate job id: ${jid_agg}"
