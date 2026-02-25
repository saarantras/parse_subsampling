# Parse Split-Pipe Subsampling Analysis

This repository implements a FASTQ-level read-depth subsampling workflow for Parse Biosciences split-pool scRNA-seq data to estimate how many reads per cell are required to recover cell identity. Data from `single_cell_iXd75a0jCZ6MNZL88FTcHoTI4L9r51p5`

## Implemented Plan

### Goal
Generate a recovery curve with:
- `x`: realized reads per cell
- `y`: fraction of cells correctly assigned to cell type (primary metric)

Ground truth is encoded by split-pipe sample/well definitions:
- `xcond_1` (`A1-A2`) -> `K562`
- `xcond_2` (`A3-A7`) -> `SK-N-SH`
- `xcond_3` (`A8-A12`) -> `HepG2`

### Experimental Design
- Full reference run: `fraction=1.0`, `replicate=0`
- Balanced grid: fractions `[0.01, 0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.75]`
- Replicates per fraction: `3`
- Total runs: `25`
- Scope: both sublibraries for every run

Grid file: `config/subsample_grid.tsv`

### Pipeline Stages
1. Subsample paired FASTQs per run and per sublibrary (R1/R2 synchronized, header pairing check).
2. Run `split-pipe --mode all` for each sublibrary with fixed sample definitions.
3. Run `split-pipe --mode combine` across `sublib_0` and `sublib_1`.
4. Score each run against full-depth reference centroids using filtered DGE matrices.
5. Aggregate all runs into final tables/figures.

Classification assignment in each run:
- Build 3 full-depth reference centroids from `ref_full` (`K562`, `SK-N-SH`, `HepG2`).
- For each cell in `combined/xcond_1|xcond_2|xcond_3/DGE_filtered`, compute correlation to all 3 centroids.
- Predicted label is hard argmax correlation.
- Ground truth label is the `xcond_*` source (`xcond_1 -> K562`, `xcond_2 -> SK-N-SH`, `xcond_3 -> HepG2`).
- Primary metric is `fraction_correct = correct_assignments / evaluated_cells`.

### SLURM Orchestration
Dependency chain per run:
- `all_sublib0` + `all_sublib1` (parallel)
- `combine` (after both all-jobs)
- `score` (after combine)
- For non-reference runs, `score` also waits on `ref_full` combine completion.

Final `aggregate` job runs after all score jobs.

All jobs use `--requeue` and run-level done markers in `runs/<run_id>/.done/` for restart-safe execution.

## Repository Layout

- `config/subsample_grid.tsv`: run definitions (`run_id,fraction,replicate,seed,is_reference`)
- `config/sublibraries.tsv`: source FASTQ paths for sublibrary 0/1
- `config/pipeline.env.example`: optional overrides for genome/env/resources
- `scripts/subsample_fastq_pairs.py`: synchronized paired FASTQ subsampling
- `scripts/capture_run_meta.py`: writes `runs/<run_id>/run_meta.json`
- `scripts/score_identity.py`: computes run-level identity metrics
- `scripts/aggregate_metrics.py`: produces final tables and plots
- `scripts/submit_genome_build.sh`: submits standalone genome build job
- `scripts/submit_subsampling_pipeline.sh`: main SLURM submitter
- `scripts/submit_smoke_test.sh`: smoke-test submitter
- `scripts/validate_outputs.py`: schema/pairing/sanity checks
- `scripts/build_umap_sample_gallery.py`: builds a self-contained HTML gallery plus static SVG export of `Samples`-colored UMAPs extracted from split-pipe report HTMLs
- `slurm/run_all_sublib.sh`: worker for sublibrary all-mode run
- `slurm/run_combine.sh`: worker for combine run
- `slurm/run_score.sh`: worker for scoring run
- `slurm/run_aggregate.sh`: worker for aggregation run
- `slurm/build_genome_hg38_ensembl109.sh`: one-time standalone mkref build worker
- `slurm/common.sh`: shared env/defaults

## Outputs

- `results/per_run_metrics.tsv`
  - Columns: `run_id,fraction,replicate,sampled_read_pairs,called_cells_total,evaluated_cells,reads_per_cell,fraction_correct,balanced_accuracy,k562_recall,sknsh_recall,hepg2_recall`
- `results/identity_curve.tsv`
  - Columns: `reads_per_cell,mean_fraction_correct,sd_fraction_correct,n_reps`
- `figures/reads_vs_identity_accuracy.png`
- `figures/reads_vs_identity_accuracy_by_class.png`
- `figures/umap_sample_gallery.html` (optional helper artifact)
  - Self-contained Plotly gallery of per-run UMAPs in `Samples` mode (data extracted and baked in at generation time)
  - Publication-style layout currently displays one sublibrary UMAP per run (using the `sublib_0` report when present; `sublib_1` is omitted from the figure grid)
  - Can be opened directly via `file://` (no local web server required)
- `figures/umap_sample_gallery.svg` (optional publication helper artifact)
  - Static vector export arranged as fraction rows × replicate columns for Illustrator/publication assembly
  - Uses the same `sublib_0`-based gallery selection as the HTML output
  - Uses full point density from extracted UMAP coordinates (larger file, but directly editable as vector)
- Per-run confusion matrices:
  - `runs/<run_id>/score_confusion_counts.tsv`
  - `runs/<run_id>/score_confusion_rowfrac.tsv`

Run-level artifacts are stored under `runs/<run_id>/`.
All split-pipe run outputs are retained under each run directory, including report HTML visualizations for sublibrary and combined outputs.

## UMAP Gallery (Publication Helper)

To compare `Samples`-colored UMAPs across runs in one document, generate the standalone gallery:

```bash
python3 scripts/build_umap_sample_gallery.py
```

This script:
- scans `runs/<run_id>/sublib_*/all-sample_analysis_summary.html` and builds the publication matrix from one sublibrary UMAP per run (currently `sublib_0` when present)
- extracts `umap_x`, `umap_y`, and `samples_raw` from the embedded split-pipe JavaScript
- re-renders only the UMAP scatter plots (no embedded full report pages)
- relabels sample classes `xcond_1/2/3` as `K562`, `SK-N-SH`, `HEPG2`
- arranges non-reference panels as fraction rows × replicate columns (reference shown separately)
- writes:
  - `figures/umap_sample_gallery.html` (interactive Plotly)
  - `figures/umap_sample_gallery.svg` (static vector export for Illustrator)

Notes:
- The generated file is intended for visual comparison and figure prep; regenerate it after rerunning analysis outputs.
- The subsampling pipeline itself still runs/combines both sublibraries; the gallery is a visualization convenience and intentionally does not show a separate `sublib_1` panel.
- The SVG export is full-density (no point downsampling), so file size can grow with the number of cells.
- Current implementation targets Parse split-pipe report structure used here (tested with pipeline `v1.6.4` report HTMLs).
- The gallery HTML still loads Plotly from the CDN, but it does not require access to the original report HTML files when viewing.

## Setup

1. Copy env template and set local values:
```bash
cp config/pipeline.env.example config/pipeline.env
```
2. Edit `config/pipeline.env`:
- `GENOME_DIR` must point to your split-pipe reference directory.
- Set `SPLIT_PIPE_CONDA_ENV` / `ANALYSIS_CONDA_ENV`.
- Adjust partition/resources if needed.
- Defaults assume `splitpipe` conda env for both split-pipe and Python analysis steps.
- SLURM workers load miniconda and activate the requested conda env before invoking Python/split-pipe.

## Conda Environment (Documented Run)

Default env names in `config/pipeline.env.example`:
- `SPLIT_PIPE_CONDA_ENV=splitpipe`
- `ANALYSIS_CONDA_ENV=splitpipe` (defaults to the same env if unset)

Recorded from `runs/ref_full/run_meta.json` (captured during pipeline execution):
- Conda env name: `splitpipe`
- Conda prefix: `/home/mcn26/.conda/envs/splitpipe`
- Python: `3.13.12`
- `split-pipe --version`: `split-pipe v1.6.4`

Core Python packages used by this repository's analysis scripts (`score_identity.py`, `aggregate_metrics.py`):
- `numpy` `2.2.6` (installed as a direct wheel reference in `pip freeze`)
- `scipy` `1.16.3`
- `pandas` `2.3.3`
- `matplotlib` `3.10.8`

Additional packages present in the recorded `splitpipe` env and relevant to the Parse/scanpy stack:
- `scanpy` `1.12`
- `anndata` `0.12.10`
- `scikit-learn` `1.8.0`
- `seaborn` `0.13.2`
- `umap-learn` `0.5.11`

Notes:
- `scripts/build_umap_sample_gallery.py` itself uses only the Python standard library.
- `figures/umap_sample_gallery.html` loads Plotly from the CDN (`plotly-3.1.0.min.js`) at view time; Plotly is not required in the conda env for generation.
- Runtime metadata capture includes `pip freeze` and command versions in each `runs/<run_id>/run_meta.json` for reproducibility.

## Build Genome (One-Time, Separate)

The subsampling pipeline does **not** run `split-pipe --mode mkref` automatically.
Build the reference once using the standalone builder, then point `GENOME_DIR` to the built output.

Submit build:
```bash
bash scripts/submit_genome_build.sh
```

Default build/output paths:
- Downloads: `/home/mcn26/scratch_pi_skr2/mcn26/parse_splitpipe_genome_build/downloads`
- Reference output (`GENOME_DIR` target): `/home/mcn26/scratch_pi_skr2/mcn26/parse_splitpipe_genome_build/genome_hg38_ensembl109`

After build completes, set in `config/pipeline.env`:
```bash
GENOME_DIR=/home/mcn26/scratch_pi_skr2/mcn26/parse_splitpipe_genome_build/genome_hg38_ensembl109
```

## Run

Full experiment:
```bash
bash scripts/submit_subsampling_pipeline.sh
```

Smoke test (fractions 0.05 and 0.50, replicate 1, plus reference):
```bash
bash scripts/submit_smoke_test.sh
```

Force resubmission of already-completed runs:
```bash
bash scripts/submit_subsampling_pipeline.sh --force
```

Each worker script in `slurm/` includes full `#SBATCH` headers and can also be submitted directly with `sbatch` if desired.

## Validation

After aggregate job completes:
```bash
python scripts/validate_outputs.py --per-run results/per_run_metrics.tsv
```

## Runtime Notes

- `reads_per_cell` is computed as `(total sampled read pairs across both sublibs * 2) / called_cells_total`.
- The required read depth is annotated in the main figure as the smallest depth where mean `fraction_correct` reaches 95% of its observed maximum.

## Cluster References

- Bouchet overview: https://docs.ycrc.yale.edu/clusters/bouchet/
- Scavenge policy: https://docs.ycrc.yale.edu/clusters-at-yale/job-scheduling/scavenge/
- Storage policy: https://docs.ycrc.yale.edu/clusters-at-yale/storage/
