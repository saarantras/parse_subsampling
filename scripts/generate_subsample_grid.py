#!/usr/bin/env python3
"""Generate the default balanced subsampling grid TSV."""

from __future__ import annotations

import csv
from pathlib import Path

OUT_PATH = Path("config/subsample_grid.tsv")
FRACTIONS = [0.01, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75]


def run_id_for_fraction(frac: float, rep: int) -> str:
    return f"f{int(round(frac * 100)):03d}_r{rep}"


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["run_id", "fraction", "replicate", "seed", "is_reference"])
        writer.writerow(["ref_full", "1.0", "0", "424242", "1"])
        for frac in FRACTIONS:
            frac_key = int(round(frac * 10000))
            for rep in (1, 2, 3):
                seed = 100000 + frac_key * 10 + rep
                writer.writerow([run_id_for_fraction(frac, rep), f"{frac:.2f}", str(rep), str(seed), "0"])


if __name__ == "__main__":
    main()
