#!/usr/bin/env python3
"""Score cell identity recovery using mean true-class correlation."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    from scipy import sparse
    from scipy.io import mmread
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing analysis dependency. Activate ANALYSIS_CONDA_ENV with numpy, pandas, and scipy installed."
    ) from exc

SAMPLE_TO_CLASS = {
    "xcond_1": "k562",
    "xcond_2": "sknsh",
    "xcond_3": "hepg2",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fraction", required=True, type=float)
    p.add_argument("--replicate", required=True, type=int)
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--reference-run-dir", required=True, type=Path)
    p.add_argument("--sampling-dir", required=True, type=Path)
    p.add_argument("--output-tsv", required=True, type=Path)
    p.add_argument("--target-sum", type=float, default=1e4)
    return p.parse_args()


def load_dge_filtered(sample_dir: Path) -> sparse.csr_matrix:
    mtx_path = sample_dir / "DGE_filtered" / "DGE.mtx"
    cell_meta_path = sample_dir / "DGE_filtered" / "cell_metadata.csv"

    if not mtx_path.exists():
        raise FileNotFoundError(f"missing matrix: {mtx_path}")
    if not cell_meta_path.exists():
        raise FileNotFoundError(f"missing cell metadata: {cell_meta_path}")

    x = mmread(mtx_path).tocsr()
    n_cells = sum(1 for _ in open(cell_meta_path)) - 1
    if n_cells < 1:
        raise ValueError(f"no cells found in {cell_meta_path}")

    if x.shape[0] == n_cells:
        return x
    if x.shape[1] == n_cells:
        return x.transpose().tocsr()
    raise ValueError(
        f"matrix/cell mismatch for {sample_dir}: matrix shape {x.shape}, cell rows {n_cells}"
    )


def normalize_log1p(x: sparse.csr_matrix, target_sum: float) -> sparse.csr_matrix:
    x = x.tocsr(copy=True)
    lib = np.asarray(x.sum(axis=1)).ravel()
    lib = np.where(lib <= 0, 1.0, lib)
    scales = target_sum / lib
    x = x.multiply(scales[:, None]).tocsr()
    x.data = np.log1p(x.data)
    return x


def centroid_from_matrix(x: sparse.csr_matrix) -> np.ndarray:
    return np.asarray(x.mean(axis=0)).ravel()


def rowwise_pearson(x: sparse.csr_matrix, centroid: np.ndarray) -> np.ndarray:
    x = x.tocsr()
    c = np.asarray(centroid).ravel()
    genes = x.shape[1]

    sum_x = np.asarray(x.sum(axis=1)).ravel()
    sum_x2 = np.asarray(x.multiply(x).sum(axis=1)).ravel()
    dot_xc = np.asarray(x.dot(c)).ravel()

    sum_c = float(c.sum())
    sum_c2 = float(np.dot(c, c))

    mean_x = sum_x / genes
    mean_c = sum_c / genes

    cov = dot_xc - genes * mean_x * mean_c
    var_x = sum_x2 - genes * mean_x * mean_x
    var_c = sum_c2 - genes * mean_c * mean_c

    denom = np.sqrt(np.clip(var_x, 0.0, None) * max(var_c, 0.0))
    corr = np.full(x.shape[0], np.nan, dtype=float)
    ok = denom > 0
    corr[ok] = cov[ok] / denom[ok]
    corr = np.clip(corr, -1.0, 1.0)
    return corr


def sampled_read_pairs(sampling_dir: Path) -> int:
    total = 0
    for path in sorted(sampling_dir.glob("sublib_*.tsv")):
        df = pd.read_csv(path, sep="\t")
        if "sampled_read_pairs" not in df.columns:
            raise ValueError(f"missing sampled_read_pairs in {path}")
        total += int(df.loc[0, "sampled_read_pairs"])
    if total == 0:
        raise ValueError(f"no sampling stats found in {sampling_dir}")
    return total


def called_cells_total(run_dir: Path) -> int:
    path = run_dir / "combined" / "all-well" / "DGE_filtered" / "cell_metadata.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing called-cell metadata: {path}")
    return sum(1 for _ in open(path)) - 1


def main() -> None:
    args = parse_args()

    ref_centroids: dict[str, np.ndarray] = {}
    for sample in SAMPLE_TO_CLASS:
        ref_x = load_dge_filtered(args.reference_run_dir / "combined" / sample)
        ref_x = normalize_log1p(ref_x, args.target_sum)
        ref_centroids[sample] = centroid_from_matrix(ref_x)

    class_scores: dict[str, float] = {}
    for sample, class_name in SAMPLE_TO_CLASS.items():
        run_x = load_dge_filtered(args.run_dir / "combined" / sample)
        run_x = normalize_log1p(run_x, args.target_sum)
        corr = rowwise_pearson(run_x, ref_centroids[sample])
        class_scores[class_name] = float(np.nanmean(corr))

    mean_true_class_corr = float(np.nanmean(list(class_scores.values())))

    sampled_pairs = sampled_read_pairs(args.sampling_dir)
    n_cells = called_cells_total(args.run_dir)
    reads_per_cell = (sampled_pairs * 2.0) / float(n_cells)

    args.output_tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_tsv.open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(
            [
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
        )
        writer.writerow(
            [
                args.run_id,
                f"{args.fraction:.4f}",
                str(args.replicate),
                str(sampled_pairs),
                str(n_cells),
                f"{reads_per_cell:.6f}",
                f"{mean_true_class_corr:.6f}",
                f"{class_scores['k562']:.6f}",
                f"{class_scores['sknsh']:.6f}",
                f"{class_scores['hepg2']:.6f}",
            ]
        )


if __name__ == "__main__":
    main()
