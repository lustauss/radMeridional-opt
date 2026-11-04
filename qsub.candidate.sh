#!/bin/bash

#SBATCH --job-name=candidate
#SBATCH --partition=cpuonly
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem=10G
#SBATCH --time=03:00:00

# environment
source ~/pe

hostname 
date

# run 
hydroflow-opt run examples/radmeridional_candidate_slurm.toml

date

