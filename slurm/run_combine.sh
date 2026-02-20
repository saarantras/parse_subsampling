#!/usr/bin/env bash
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

touch "${done_flag}"
