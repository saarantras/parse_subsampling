#!/usr/bin/env python3
"""Aggregate run-level metrics and generate identity recovery plots."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing analysis dependency. Activate ANALYSIS_CONDA_ENV with numpy, pandas, and matplotlib installed."
    ) from exc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--grid", required=True, type=Path)
    p.add_argument("--runs-dir", required=True, type=Path)
    p.add_argument("--per-run-out", required=True, type=Path)
    p.add_argument("--curve-out", required=True, type=Path)
    p.add_argument("--main-fig", required=True, type=Path)
    p.add_argument("--class-fig", required=True, type=Path)
    return p.parse_args()


def load_metrics(grid: pd.DataFrame, runs_dir: Path) -> pd.DataFrame:
    rows = []
    for _, row in grid.iterrows():
        run_id = row["run_id"]
        metric_path = runs_dir / run_id / "score_metrics.tsv"
        if not metric_path.exists():
            continue
        metric = pd.read_csv(metric_path, sep="\t")
        if metric.empty:
            continue
        rows.append(metric.iloc[0])

    if not rows:
        raise RuntimeError("No run metric files found under runs directory")

    df = pd.DataFrame(rows)
    df["fraction"] = df["fraction"].astype(float)
    df["replicate"] = df["replicate"].astype(int)
    numeric_cols = [
        "sampled_read_pairs",
        "called_cells_total",
        "reads_per_cell",
        "mean_true_class_corr",
        "k562_corr",
        "sknsh_corr",
        "hepg2_corr",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_curve(per_run: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        per_run.groupby("fraction", as_index=False)
        .agg(
            reads_per_cell=("reads_per_cell", "mean"),
            mean_corr=("mean_true_class_corr", "mean"),
            sd_corr=("mean_true_class_corr", "std"),
            n_reps=("mean_true_class_corr", "count"),
        )
        .sort_values("reads_per_cell")
    )
    grouped["sd_corr"] = grouped["sd_corr"].fillna(0.0)
    return grouped[["reads_per_cell", "mean_corr", "sd_corr", "n_reps"]]


def required_depth(curve: pd.DataFrame) -> float:
    plateau = float(curve["mean_corr"].max())
    threshold = 0.95 * plateau
    meets = curve[curve["mean_corr"] >= threshold]
    if meets.empty:
        return float("nan")
    return float(meets.sort_values("reads_per_cell").iloc[0]["reads_per_cell"])


def plot_main(curve: pd.DataFrame, out_path: Path) -> None:
    req_x = required_depth(curve)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(
        curve["reads_per_cell"],
        curve["mean_corr"],
        yerr=curve["sd_corr"],
        fmt="o-",
        capsize=4,
        linewidth=1.5,
    )
    if np.isfinite(req_x):
        ax.axvline(req_x, linestyle="--", linewidth=1.2, label=f"95% plateau depth = {req_x:.1f}")
        ax.legend(frameon=False)

    ax.set_xlabel("Reads per cell (realized)")
    ax.set_ylabel("Mean true-class correlation")
    ax.set_title("Cell identity recovery vs read depth")
    ax.grid(alpha=0.25)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def plot_by_class(per_run: pd.DataFrame, out_path: Path) -> None:
    class_cols = ["k562_corr", "sknsh_corr", "hepg2_corr"]
    labels = {
        "k562_corr": "K562",
        "sknsh_corr": "SK-N-SH",
        "hepg2_corr": "HepG2",
    }

    grouped = per_run.groupby("fraction", as_index=False).agg(reads_per_cell=("reads_per_cell", "mean"))
    grouped = grouped.sort_values("reads_per_cell")

    fig, ax = plt.subplots(figsize=(8, 5))
    for col in class_cols:
        stats = (
            per_run.groupby("fraction", as_index=False)
            .agg(mean=(col, "mean"), sd=(col, "std"))
            .merge(grouped, on="fraction", how="left")
            .sort_values("reads_per_cell")
        )
        stats["sd"] = stats["sd"].fillna(0.0)
        ax.errorbar(
            stats["reads_per_cell"],
            stats["mean"],
            yerr=stats["sd"],
            fmt="o-",
            capsize=3,
            linewidth=1.2,
            label=labels[col],
        )

    ax.set_xlabel("Reads per cell (realized)")
    ax.set_ylabel("True-class correlation")
    ax.set_title("Per-class identity recovery")
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    grid = pd.read_csv(args.grid, sep="\t")
    per_run = load_metrics(grid, args.runs_dir).sort_values("reads_per_cell")

    args.per_run_out.parent.mkdir(parents=True, exist_ok=True)
    per_run.to_csv(args.per_run_out, sep="\t", index=False)

    curve = compute_curve(per_run)
    args.curve_out.parent.mkdir(parents=True, exist_ok=True)
    curve.to_csv(args.curve_out, sep="\t", index=False)

    plot_main(curve, args.main_fig)
    plot_by_class(per_run, args.class_fig)


if __name__ == "__main__":
    main()
