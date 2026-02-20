#!/usr/bin/env python3
"""Validate key outputs and sanity checks for subsampling analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import pandas as pd
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: pandas. Activate your analysis environment first.") from exc


EXPECTED_COLUMNS = [
    "run_id",
    "fraction",
    "replicate",
    "sampled_read_pairs",
    "called_cells_total",
    "reads_per_cell",
    "mean_true_class_corr",
    "k562_corr",
    "sknsh_corr",
    "hepg2_corr",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--per-run", default="results/per_run_metrics.tsv", type=Path)
    p.add_argument("--sampling-glob", default="runs/*/sampling/sublib_*.tsv")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.per_run.exists():
        raise SystemExit(f"missing per-run metrics file: {args.per_run}")

    per_run = pd.read_csv(args.per_run, sep="\t")
    missing = [c for c in EXPECTED_COLUMNS if c not in per_run.columns]
    if missing:
        raise SystemExit(f"missing columns in per-run metrics: {missing}")

    sampling_paths = sorted(Path().glob(args.sampling_glob))
    if not sampling_paths:
        raise SystemExit("no sampling stats found for pairing check")

    mismatch_total = 0
    for path in sampling_paths:
        df = pd.read_csv(path, sep="\t")
        mismatch_total += int(df.loc[0, "header_mismatches"])

    if mismatch_total != 0:
        raise SystemExit(f"pairing check failed: found {mismatch_total} mismatches")

    if "ref_full" in set(per_run["run_id"]):
        ref = float(per_run.loc[per_run["run_id"] == "ref_full", "mean_true_class_corr"].max())
        low = per_run[per_run["fraction"].astype(float) <= 0.02]["mean_true_class_corr"]
        if not low.empty and low.mean() > ref:
            raise SystemExit("metric sanity check failed: low-depth average exceeds reference")

    print("Validation passed: schema, pairing integrity, and basic metric sanity checks.")


if __name__ == "__main__":
    main()
