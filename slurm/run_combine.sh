#!/usr/bin/env bash
#SBATCH --job-name=parse_subsample_combine
#SBATCH --partition=day
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --requeue
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/common.sh"

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 <run_id>" >&2
  exit 1
fi

run_id="$1"

ensure_dirs
activate_conda_env "${SPLIT_PIPE_CONDA_ENV}"

run_dir="${RUNS_DIR}/${run_id}"
mkdir -p "${run_dir}/.done"
done_flag="${run_dir}/.done/combine.done"
if [[ -f "${done_flag}" ]]; then
  echo "Skipping combine for ${run_id}; done marker present"
  exit 0
fi

if [[ ! -d "${run_dir}/sublib_0" || ! -d "${run_dir}/sublib_1" ]]; then
  echo "Missing sublibrary outputs for ${run_id}" >&2
  exit 1
fi

(
  cd "${run_dir}"
  split-pipe --mode combine --sublibraries sublib_0 sublib_1 --output_dir combined
)

if ! ls "${run_dir}/combined"/*_analysis_summary.html >/dev/null 2>&1; then
  echo "Expected split-pipe report HTML files not found in ${run_dir}/combined" >&2
  exit 1
fi

touch "${done_flag}"
