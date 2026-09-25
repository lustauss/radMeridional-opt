#!/bin/bash

#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --nodelist=mars

##export TMPDIR="$PWD"
##export TMPDIR="/mnt/tscratch/lstauss-MA2/testDir"

# OpenFOAM environment
. source-dtoo

hostname 
date

echo "SLURM_NTASKS=$SLURM_NTASKS"
echo "SLURM_CPUS_PER_TASK=$SLURM_CPUS_PER_TASK"
echo "SLURM_NTASKS_PER_NODE=$SLURM_NTASKS_PER_NODE"

hydroflow-opt optimize examples/radmeridional_candidate.toml

date

