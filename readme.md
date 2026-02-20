# Parse Split-Pipe Subsampling Analysis

This repository implements a FASTQ-level read-depth subsampling workflow for Parse Biosciences split-pool scRNA-seq data to estimate how many reads per cell are required to recover cell identity. Data from `initial_parse_analysis_dw02aaQXFLuCidCjhGcm28ZUOVLeaelJ`

## Implemented Plan

### Goal
Generate a recovery curve with:
- `x`: realized reads per cell
- `y`: mean true-class correlation to full-depth reference centroids

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
- `scripts/submit_subsampling_pipeline.sh`: main SLURM submitter
- `scripts/submit_smoke_test.sh`: smoke-test submitter
- `scripts/validate_outputs.py`: schema/pairing/sanity checks
- `slurm/run_all_sublib.sh`: worker for sublibrary all-mode run
- `slurm/run_combine.sh`: worker for combine run
- `slurm/run_score.sh`: worker for scoring run
- `slurm/run_aggregate.sh`: worker for aggregation run
- `slurm/common.sh`: shared env/defaults

## Outputs

- `results/per_run_metrics.tsv`
  - Columns: `run_id,fraction,replicate,sampled_read_pairs,called_cells_total,reads_per_cell,mean_true_class_corr,k562_corr,sknsh_corr,hepg2_corr`
- `results/identity_curve.tsv`
  - Columns: `reads_per_cell,mean_corr,sd_corr,n_reps`
- `figures/reads_vs_identity_corr.png`
- `figures/reads_vs_identity_corr_by_class.png`

Run-level artifacts are stored under `runs/<run_id>/`.

## Setup

1. Copy env template and set local values:
```bash
cp config/pipeline.env.example config/pipeline.env
```
2. Edit `config/pipeline.env`:
- `GENOME_DIR` must point to your split-pipe reference directory.
- Set `SPLIT_PIPE_CONDA_ENV` / `ANALYSIS_CONDA_ENV`.
- Adjust partition/resources if needed.

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

## Validation

After aggregate job completes:
```bash
python scripts/validate_outputs.py --per-run results/per_run_metrics.tsv
```

## Runtime Notes

- `reads_per_cell` is computed as `(total sampled read pairs across both sublibs * 2) / called_cells_total`.
- The required read depth is annotated in the main figure as the smallest depth reaching 95% of the observed plateau.

## Cluster References

- Bouchet overview: https://docs.ycrc.yale.edu/clusters/bouchet/
- Scavenge policy: https://docs.ycrc.yale.edu/clusters-at-yale/job-scheduling/scavenge/
- Storage policy: https://docs.ycrc.yale.edu/clusters-at-yale/storage/
