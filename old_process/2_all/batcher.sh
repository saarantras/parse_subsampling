#!/bin/bash
#SBATCH -c 10 --mem=64g
#SBATCH -t 8:00:00
#SBATCH --mail-user=mackenziecnoon@gmail.com
#SBATCH --mail-type=END,FAIL
#SBATCH --array=0-1

date

~/fixconda.sh

module load miniconda
conda activate spipe

cd /home/mcn26/palmer_scratch/analysis/process/2_all
./all.sh
