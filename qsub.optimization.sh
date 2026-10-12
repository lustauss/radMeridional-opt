#!/bin/bash

#SBATCH --nodes=2
#SBATCH --ntasks-per-node=8
#SBATCH --mem=10G
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
#SBATCH --nodelist=mars,ruehrer

##export TMPDIR="$PWD"
##export TMPDIR="/mnt/tscratch/lstauss-MA2"

# OpenFOAM environment
. source-dtoo

hostname 
date

echo "JOB ID: $SLURM_JOB_ID"
echo "NODE LIST: $SLURM_JOB_NODELIST"
echo "NUM NODES: $SLURM_JOB_NUM_NODES"

scontrol show hostnames "$SLURM_JOB_NODELIST"

#hydroflow-opt optimize examples/radmeridional_optimization.toml
hydroflow-opt resume examples/runs/radmeridional_optimization

date

