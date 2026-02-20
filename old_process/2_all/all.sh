cd /home/mcn26/palmer_scratch/analysis

#i=1
i=$SLURM_ARRAY_TASK_ID

if [ $i == 0 ]; then
    fwd="raw_data/ryan-sublib-1_L1_ds.6cea746bf1ed4d7a8266237195f20760/ryan-sublib-1_S1_L001_R1_001.fastq.gz"
    rev="raw_data/ryan-sublib-1_L1_ds.6cea746bf1ed4d7a8266237195f20760/ryan-sublib-1_S1_L001_R2_001.fastq.gz"
elif [ $i == 1 ]; then
    fwd="raw_data/ryan-sublib-2_L1_ds.696133ab3cd34034bbaaea07e4dab17f/ryan-sublib-2_S2_L001_R1_001.fastq.gz"
    rev="raw_data/ryan-sublib-2_L1_ds.696133ab3cd34034bbaaea07e4dab17f/ryan-sublib-2_S2_L001_R2_001.fastq.gz"
fi
   
echo $fwd

mkdir -p sublib_$i

 

split-pipe \
    --mode all \
    --chemistry v2 \
    --genome_dir ./genome/ \
    --fq1 $fwd \
    --fq2 $rev \
    --output_dir sublib_$i \
    --sample xcond_1 A1-A2 \
    --sample xcond_2 A3-A7 \
    --sample xcond_3 A8-A12
