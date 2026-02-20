#!/usr/bin/env python3
"""Capture runtime metadata for reproducibility."""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def run_cmd(cmd: list[str]) -> dict[str, object]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {"cmd": cmd, "error": str(exc)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fraction", required=True)
    p.add_argument("--replicate", required=True)
    p.add_argument("--seed", required=True)
    p.add_argument("--is-reference", required=True)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "run": {
            "run_id": args.run_id,
            "fraction": args.fraction,
            "replicate": args.replicate,
            "seed": args.seed,
            "is_reference": args.is_reference,
        },
        "env": {
            "CONDA_DEFAULT_ENV": os.environ.get("CONDA_DEFAULT_ENV"),
            "CONDA_PREFIX": os.environ.get("CONDA_PREFIX"),
            "SLURM_JOB_ID": os.environ.get("SLURM_JOB_ID"),
            "SLURM_JOB_NAME": os.environ.get("SLURM_JOB_NAME"),
            "SLURM_CPUS_PER_TASK": os.environ.get("SLURM_CPUS_PER_TASK"),
        },
        "commands": {
            "split_pipe_version": run_cmd(["split-pipe", "--version"]),
            "python_version": run_cmd(["python", "--version"]),
            "pip_freeze": run_cmd(["python", "-m", "pip", "freeze"]),
            "conda_env_list": run_cmd(["conda", "env", "list"]),
        },
    }

    with args.out.open("w") as handle:
        json.dump(payload, handle, indent=2)


if __name__ == "__main__":
    main()
