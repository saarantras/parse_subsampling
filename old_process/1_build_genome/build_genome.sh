#!/bin/bash
#SBATCH -c 5 --mem=120g
#SBATCH -t 4:00:00
#SBATCH --mail-user=mackenziecnoon@gmail.com
#SBATCH --mail-type=END,FAIL

date

~/fixconda.sh

module load miniconda
conda activate spipe


cd ~/palmer_scratch/analysis
mkdir -p genome
cd genome
#wget https://ftp.ensembl.org/pub/release-109/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz
#wget https://ftp.ensembl.org/pub/release-109/gtf/homo_sapiens/Homo_sapiens.GRCh38.109.gtf.gz

split-pipe --mode mkref --genome_name hg38 --fasta Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz --genes Homo_sapiens.GRCh38.109.gtf.gz --output_dir .

#run commands...
