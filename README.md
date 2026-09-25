# radmeridional-opt

[![Build](https://github.com/ihs-ustutt/hydroFoil_bwRSE4HPC/actions/workflows/ci.yml/badge.svg)](https://github.com/ihs-ustutt/hydroFoil_bwRSE4HPC/actions)

`radmeridional-opt` is the radmeridional case plugin for
[`hydroflow-opt`](../hydroflow-opt). It has no Pyro5 dependency and does not implement
its own scheduler or worker pool. `hydroflow-opt` starts an isolated worker for
each candidate and owns the global resource budget.

## Runtime prerequisites

The package can be installed and unit-tested without CFD software. Running a
real radmeridional evaluation requires a separately provisioned Linux environment
with dtOO, foamlib, OpenFOAM, and an MPI launcher. Set up those tools as usual
before invoking `hydroflow-opt`; this package deliberately does not load them until
its worker executes a candidate.

Check the currently active shell before running a real case:

```bash
radmeridional-opt check-runtime
```

This prints a compact checklist for the dtOO Python bindings, OpenFOAM tools,
MPI launcher, and relevant environment variables. It does not run a CFD case.

For instructions covering OpenFOAM, foamFine, dtOO, its third-party
dependencies, and the Python environment, see
[`docs/installation.md`](docs/installation.md).

## Example

Install the orchestration package and this plugin in the same environment.
Then run either explicit candidates or the pygmo island optimizer via

```bash
hydroflow-opt check examples/radmeridional_candidate.toml
hydroflow-opt run examples/radmeridional_candidate.toml
```

or

```bash
hydroflow-opt check examples/radmeridional_optimization.toml
hydroflow-opt optimize examples/radmeridional_optimization.toml
```
respectively.

The resource shape is explicit. For example, four two-rank CFD evaluations
need at least eight CPUs:

```toml
[resources]
available_cpus = 8
concurrent_evaluations = 4
mpi_ranks = 2
threads_per_rank = 1
```

The local worker uses `mpiexec -n <mpi_ranks>` and never passes
`--oversubscribe`.

For Slurm execution, add:

```toml
[execution]
backend = "slurm"
```

and run `hydroflow-opt` inside an existing `sbatch` or `salloc` allocation.
The allocation may span nodes, but each candidate must fit on one node.
The radmeridional worker is a controller: geometry generation and meshing run
once, while each OpenFOAM solver stage is launched directly as:

```text
srun --exclusive --nodes=1 --ntasks=<mpi_ranks> \
  --cpus-per-task=<threads_per_rank> --cpu-bind=cores --mpi=pmix \
  simpleFoam -parallel
```

There is no nested `mpiexec` in Slurm mode. Local execution continues to use
`mpiexec -n <mpi_ranks>`. For four islands with two one-thread MPI ranks per
candidate, request eight Slurm tasks with one CPU each:

```bash
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread
```

Before a production run, verify that the cluster supports direct Open MPI
launching with `srun --mpi=list`; the available plugin list must include
`pmix`.

## Baseline-compatible optimization

The original submission requested 64 islands, used populations of eight
pre-evaluated designs from `start_db.json`, applied one DE generation at a
time with a fully connected topology and evicted delivered migrants, and
stopped after approximately 35,000 new simulations.

Start with the four-island reproduction smoke test:

```bash
hydroflow-opt check examples/radmeridional_baseline_smoke_slurm.toml
hydroflow-opt optimize examples/radmeridional_baseline_smoke_slurm.toml
```

It initializes four populations from the historical database without running
32 initialization simulations, then evaluates one generation: 32 new CFD
cases, with at most four cases running concurrently.

The full configuration is
`examples/radmeridional_baseline_reproduction_slurm.toml`. It uses 64 islands,
eight individuals per island, 69 generations, and 128 CPUs. This produces
35,328 new evaluations, the nearest whole-generation equivalent of the
baseline's 35,000-evaluation asynchronous stopping condition.

The new run is reproducible but cannot recreate an old random trajectory:
the original did not record a seed and accidentally excluded database entry
100. The new configuration records a seed and samples all valid records.

For a large multi-node run, note that the Python island controllers originate
on the batch node; their `simpleFoam` stages are distributed by Slurm. Validate
controller-side meshing and memory load at smaller scale before attempting all
64 islands.
