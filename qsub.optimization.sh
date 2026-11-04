#!/bin/bash

#SBATCH --job-name=optimization
#SBATCH --partition=cpuonly
#SBATCH --nodes=2
#SBATCH --ntasks=8
#SBATCH --mem=10G
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread

# environment
source ~/pe

hostname 
date

hydroflow-opt optimize examples/radmeridional_optimization.toml
#hydroflow-opt resume examples/runs/radmeridional_optimization

date

