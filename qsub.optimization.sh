#!/bin/bash

#SBATCH --job-name=optimization
#SBATCH --partition=cpuonly
#SBATCH --nodes=1
##SBATCH --ntasks=8
#SBATCH --ntasks-per-node=76
#SBATCH --mem=40G
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --hint=nomultithread

# environment
source ~/pe

hostname 
date

#hydroflow-opt optimize examples/radmeridional_optimization.toml
hydroflow-opt resume examples/runs/radmeridional_optimization

date

