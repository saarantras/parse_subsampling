#!/usr/bin/env python3
"""Score cell identity recovery as a 3-way classification task."""

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
CLASS_ORDER = ["k562", "sknsh", "hepg2"]
CLASS_TO_INDEX = {name: idx for idx, name in enumerate(CLASS_ORDER)}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", required=True)
    p.add_argument("--fraction", required=True, type=float)
    p.add_argument("--replicate", required=True, type=int)
    p.add_argument("--run-dir", required=True, type=Path)
    p.add_argument("--reference-run-dir", required=True, type=Path)
    p.add_argument("--sampling-dir", required=True, type=Path)
    p.add_argument("--output-tsv", required=True, type=Path)
    p.add_argument("--confusion-counts-out", type=Path)
    p.add_argument("--confusion-rowfrac-out", type=Path)
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


def analysis_dir(run_dir: Path) -> Path:
    combined = run_dir / "combined"
    if combined.exists():
        return combined
    sublib0 = run_dir / "sublib_0"
    if sublib0.exists():
        return sublib0
    raise FileNotFoundError(f"missing analysis output under {run_dir} (expected combined/ or sublib_0/)")


def count_cells(cell_meta_path: Path) -> int:
    if not cell_meta_path.exists():
        raise FileNotFoundError(f"missing cell metadata: {cell_meta_path}")
    return sum(1 for _ in open(cell_meta_path)) - 1


def called_cells_total(run_dir: Path) -> int:
    root = analysis_dir(run_dir)
    all_well = root / "all-well" / "DGE_filtered" / "cell_metadata.csv"
    if all_well.exists():
        return count_cells(all_well)

    # Single-input runs may not have a combined all-well sample; sum called cells across xcond outputs.
    return sum(
        count_cells(root / sample_name / "DGE_filtered" / "cell_metadata.csv")
        for sample_name in SAMPLE_TO_CLASS
    )


def build_reference_centroids(reference_run_dir: Path, target_sum: float) -> dict[str, np.ndarray]:
    ref_root = analysis_dir(reference_run_dir)
    centroids: dict[str, np.ndarray] = {}
    for sample_name, class_name in SAMPLE_TO_CLASS.items():
        ref_x = load_dge_filtered(ref_root / sample_name)
        ref_x = normalize_log1p(ref_x, target_sum)
        centroids[class_name] = centroid_from_matrix(ref_x)
    return centroids


def classify_run(run_dir: Path, centroids: dict[str, np.ndarray], target_sum: float) -> tuple[np.ndarray, dict[str, float], int]:
    run_root = analysis_dir(run_dir)
    confusion = np.zeros((len(CLASS_ORDER), len(CLASS_ORDER)), dtype=int)
    total_cells = 0

    for sample_name, true_class in SAMPLE_TO_CLASS.items():
        run_x = load_dge_filtered(run_root / sample_name)
        run_x = normalize_log1p(run_x, target_sum)

        score_cols = []
        for class_name in CLASS_ORDER:
            score_cols.append(rowwise_pearson(run_x, centroids[class_name]))
        scores = np.column_stack(score_cols)

        # Hard-assign every cell by argmax correlation.
        safe_scores = np.where(np.isnan(scores), -1.0, scores)
        pred_idx = np.argmax(safe_scores, axis=1)
        true_idx = CLASS_TO_INDEX[true_class]

        for p_idx in pred_idx:
            confusion[true_idx, int(p_idx)] += 1
        total_cells += run_x.shape[0]

    class_recall = {}
    for class_name, idx in CLASS_TO_INDEX.items():
        support = confusion[idx, :].sum()
        class_recall[class_name] = float(confusion[idx, idx] / support) if support > 0 else float("nan")

    return confusion, class_recall, total_cells


def write_confusions(confusion: np.ndarray, counts_out: Path, rowfrac_out: Path) -> None:
    labels_true = [f"true_{x}" for x in CLASS_ORDER]
    labels_pred = [f"pred_{x}" for x in CLASS_ORDER]

    counts_df = pd.DataFrame(confusion, index=labels_true, columns=labels_pred)
    counts_out.parent.mkdir(parents=True, exist_ok=True)
    counts_df.to_csv(counts_out, sep="\t")

    row_sums = confusion.sum(axis=1, keepdims=True)
    rowfrac = np.divide(confusion, row_sums, out=np.zeros_like(confusion, dtype=float), where=row_sums > 0)
    rowfrac_df = pd.DataFrame(rowfrac, index=labels_true, columns=labels_pred)
    rowfrac_out.parent.mkdir(parents=True, exist_ok=True)
    rowfrac_df.to_csv(rowfrac_out, sep="\t")


def main() -> None:
    args = parse_args()

    confusion_counts_out = args.confusion_counts_out or (args.run_dir / "score_confusion_counts.tsv")
    confusion_rowfrac_out = args.confusion_rowfrac_out or (args.run_dir / "score_confusion_rowfrac.tsv")

    centroids = build_reference_centroids(args.reference_run_dir, args.target_sum)
    confusion, class_recall, evaluated_cells = classify_run(args.run_dir, centroids, args.target_sum)

    correct = int(np.trace(confusion))
    fraction_correct = float(correct / evaluated_cells) if evaluated_cells > 0 else float("nan")
    balanced_accuracy = float(np.nanmean([class_recall[c] for c in CLASS_ORDER]))

    write_confusions(confusion, confusion_counts_out, confusion_rowfrac_out)

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
                "evaluated_cells",
                "reads_per_cell",
                "fraction_correct",
                "balanced_accuracy",
                "k562_recall",
                "sknsh_recall",
                "hepg2_recall",
            ]
        )
        writer.writerow(
            [
                args.run_id,
                f"{args.fraction:.4f}",
                str(args.replicate),
                str(sampled_pairs),
                str(n_cells),
                str(evaluated_cells),
                f"{reads_per_cell:.6f}",
                f"{fraction_correct:.6f}",
                f"{balanced_accuracy:.6f}",
                f"{class_recall['k562']:.6f}",
                f"{class_recall['sknsh']:.6f}",
                f"{class_recall['hepg2']:.6f}",
            ]
        )


if __name__ == "__main__":
    main()
