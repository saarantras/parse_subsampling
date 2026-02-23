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

if [[ ! -d "${run_dir}/sublib_0" ]]; then
  echo "Missing analysis output for ${run_id}: expected ${run_dir}/sublib_0" >&2
  exit 1
fi
if [[ -d "${run_dir}/sublib_1" ]]; then
  echo "Unexpected ${run_dir}/sublib_1 found; this pipeline now expects a single paired-end input only." >&2
  exit 1
fi

# Single paired-end input: expose sublib_0 as combined/ for downstream tools that still read combined/.
if [[ -e "${run_dir}/combined" && ! -L "${run_dir}/combined" ]]; then
  echo "combined exists and is not a symlink: ${run_dir}/combined" >&2
  exit 1
fi
(
  cd "${run_dir}"
  ln -sfn "sublib_0" "combined"
)

if ! ls "${run_dir}/combined"/*_analysis_summary.html >/dev/null 2>&1; then
  echo "Expected split-pipe report HTML files not found in ${run_dir}/combined" >&2
  exit 1
fi

touch "${done_flag}"
