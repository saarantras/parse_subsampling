#!/bin/bash
#SBATCH -c 3 --mem=64g
#SBATCH -t 8:00:00
#SBATCH --mail-user=mackenziecnoon@gmail.com
#SBATCH --mail-type=END,FAIL

date


module unload Python

~/fixconda.sh
module load miniconda
conda activate /gpfs/gibbs/project/reilly/mcn26/conda_envs/spipe

cd /home/mcn26/palmer_scratch/analysis
mkdir -p combined 
split-pipe --mode combine --sublibraries sublib_0 sublib_1 --output_dir combined
