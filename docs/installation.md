# Runtime installation

Running a radmeridional evaluation requires more than the Python packages
`hydroflow-opt` and `radmeridional-opt`. The complete runtime consists of:

- Python 3.11, 3.12, or 3.13 and the Python dependencies declared by the two
  packages;
- OpenFOAM and an MPI implementation;
- [foamFine](https://github.com/ihs-ustutt/foamFine);
- [dtOO](https://github.com/ihs-ustutt/dtOO), its Python bindings, and the libraries built by [dtOO-ThirdParty](https://github.com/ihs-ustutt/dtOO-ThirdParty).

The exact compiler, package-manager, OpenFOAM, and scheduler setup depends on
the target system. This guide therefore uses configurable paths and does not
assume an environment-module system or a particular scheduler. It is based on
the dtOO [author's build recipe](https://github.com/ihs-ustutt/dtOO/issues/67).

The examples below use the following layout:

```text
<work-root>/
├── dtOO/
├── dtOO-install/
├── foamFine/
├── hydroflow-opt/
└── hydroFoil_bwRSE4HPC/
```

The repositories may be stored elsewhere as long as the corresponding
environment variables are adjusted.

Set three paths for the commands in this guide:

```bash
export WORK_ROOT="${HOME}/radmeridional-runtime"
export OPENFOAM_BASHRC=/absolute/path/to/OpenFOAM/etc/bashrc
export HYDROFOIL_VENV="${WORK_ROOT}/venv"
```

Change these values to suit the local installation.

## 1. Install system prerequisites

Install a C and C++ compiler, a Fortran compiler, Git, CMake, Make, and the
development files needed by dtOO and its third-party libraries. These include:

- BLAS, LAPACK, Eigen, and GFortran;
- Boost filesystem, program-options, regex, thread, and timer;
- FreeType, Tcl, and Tk;
- GMP, GSL, and muParser;
- Qt 5 Core and XML;
- RapidJSON and nlohmann-json;
- SWIG and Python development headers.

Package names differ between Linux distributions. The
`dtOO-ThirdParty/Dockerfile.ubuntu` and `Dockerfile.opensuse` files provide
concrete package lists for those distributions.

In particular, OCCT configuration requires the Tcl and Tk development
headers, not only the Tcl/Tk runtime libraries.

## 2. Install and initialize OpenFOAM

Install or compile OpenFOAM before building foamFine or dtOO. This project has
been developed with OpenFOAM v2412. Other versions may work but can require
source changes in foamFine or dtOO.

OpenFOAM provides a shell initialization script, usually named `etc/bashrc`.
Source the script supplied by the chosen installation:

```bash
source "${OPENFOAM_BASHRC}"
```

Verify that the compiler wrapper, solver, and MPI launcher are available:

```bash
command -v wmake
command -v simpleFoam
command -v mpiexec
```

Use an MPI implementation compatible with the OpenFOAM build.

## 3. Create a Python environment

Use a dedicated virtual environment. A standard `venv`, Conda environment, or
another environment manager can be used. For example:

```bash
python3 -m venv "${HYDROFOIL_VENV}"
source "${HYDROFOIL_VENV}/bin/activate"
python -m pip install --upgrade pip
```

Install `hydroflow-opt` and this radmeridional plugin. Editable installations are
convenient when working from source:

```bash
python -m pip install --editable "${WORK_ROOT}/hydroflow-opt"
python -m pip install --editable "${WORK_ROOT}/hydroFoil_bwRSE4HPC"
```

Their package metadata installs NumPy, pygmo, foamlib, oslo.concurrency, and
scikit-learn. Install SWIG separately when it is not supplied by the operating
system:

```bash
python -m pip install "swig==4.3.0"
```

The Python interpreter selected here must also be used when configuring dtOO.
The resulting dtOO bindings are tied to that Python version and environment.

## 4. Obtain dtOO and foamFine

Clone dtOO and its submodules, and clone foamFine:

```bash
git clone https://github.com/ihs-ustutt/dtOO.git "${WORK_ROOT}/dtOO"
git -C "${WORK_ROOT}/dtOO" submodule update --init --recursive

git clone https://github.com/ihs-ustutt/foamFine.git "${WORK_ROOT}/foamFine"
```

For reproducible installations, record the exact revisions:

```bash
git -C "${WORK_ROOT}/dtOO" rev-parse HEAD
git -C "${WORK_ROOT}/dtOO/dtOO-ThirdParty" rev-parse HEAD
git -C "${WORK_ROOT}/foamFine" rev-parse HEAD
```

## 5. Configure the shell environment

Create a shell script such as `${WORK_ROOT}/radmeridional-env.sh`. Set the first
three variables to absolute paths so that the script also works in a newly
opened shell:

```bash
#!/usr/bin/env bash

export WORK_ROOT=/absolute/path/to/radmeridional-runtime
export OPENFOAM_BASHRC=/absolute/path/to/OpenFOAM/etc/bashrc
export HYDROFOIL_VENV="${WORK_ROOT}/venv"

source "${OPENFOAM_BASHRC}"
source "${HYDROFOIL_VENV}/bin/activate"

export DTOO_SOURCE="${WORK_ROOT}/dtOO"
export DTOO_EXTERNLIBS="${WORK_ROOT}/dtOO-install"
export FOAMFINE_DIR="${WORK_ROOT}/foamFine"

export PATH="${DTOO_EXTERNLIBS}/bin${PATH:+:${PATH}}"
export PYTHONPATH="${DTOO_EXTERNLIBS}/tools:${DTOO_EXTERNLIBS}/scripts/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${DTOO_EXTERNLIBS}/lib:${DTOO_EXTERNLIBS}/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

export OSLO_LOCK_PATH="${WORK_ROOT}/oslo-lock"
```

Then create the writable directories and load the environment:

```bash
mkdir -p "${WORK_ROOT}/dtOO-install" "${WORK_ROOT}/oslo-lock"
source "${WORK_ROOT}/radmeridional-env.sh"
```

The same environment must be active while compiling foamFine and dtOO and
while running radmeridional evaluations.

## 6. Compile foamFine

With the OpenFOAM and radmeridional environments active:

```bash
cd "${FOAMFINE_DIR}/of"
wmake all
```

Check the output for failed libraries before continuing.

## 7. Compile dtOO third-party dependencies

Choose a parallel build count appropriate for the available memory. OCCT,
Gmsh, and some of the other C++ dependencies can consume substantial memory:

```bash
export BUILD_JOBS=2
cd "${DTOO_SOURCE}/dtOO-ThirdParty"
bash install.sh -n "${BUILD_JOBS}"
```

The script builds and installs the required libraries into
`DTOO_EXTERNLIBS`. It can be rerun after a failed or interrupted build; already
completed dependencies are skipped.

If the partial build was made with an older version of `install.sh` that did
not record completed dependencies, identify the dependency that failed and
resume from it once:

```bash
# Example when pythonocc-core was the first dependency that did not complete:
bash install.sh --resume-from pythonocc-core -n "${BUILD_JOBS}"
```

Use `bash install.sh --force -n "${BUILD_JOBS}"` only when all dependencies
should be rebuilt.

If compilation is killed because the system runs out of memory, reduce
`BUILD_JOBS` and rerun the command. The individual dependency logs are stored
under `dtOO-ThirdParty/ThirdParty/`.

## 8. Compile and install dtOO

Configure dtOO with the Python interpreter from the active environment and
the same installation prefix used for its dependencies:

```bash
cmake \
  -S "${DTOO_SOURCE}" \
  -B "${DTOO_SOURCE}/build" \
  -DPython3_EXECUTABLE="$(command -v python)" \
  -DCMAKE_INSTALL_PREFIX="${DTOO_EXTERNLIBS}" \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
```

Build and install it:

```bash
cmake \
  --build "${DTOO_SOURCE}/build" \
  --parallel "${BUILD_JOBS}" \
  --target install
```

Warnings from SWIG about shadowed C++ overloads are not necessarily build
failures. Use the final compiler or linker error, if present, to diagnose a
failed build.

## 9. Validate the installation

Run the dtOO tests:

```bash
ctest \
  --test-dir "${DTOO_SOURCE}/build" \
  --output-on-failure
```

Check the Python bindings and external executables:

```bash
python -c "import dtOOPythonSWIG; print('dtOOPythonSWIG ok')"
python -c "import pyDtOO; print('pyDtOO ok')"
python -c "from dtOOPythonApp.builder import ofOpenFOAMCase_turboMachine; print('dtOOPythonApp ok')"
python -c "import foamlib; print('foamlib ok')"
command -v simpleFoam
command -v mpiexec
```

Finally, run the plugin's complete runtime check:

```bash
radmeridional-opt check-runtime
```

This command reports missing imports, executables, or relevant environment
variables without running a CFD simulation.

## 10. Run the examples

From the `hydroFoil_bwRSE4HPC` repository, validate and run the known
candidate:

```bash
hydroflow-opt check examples/radmeridional_candidate.toml
hydroflow-opt run examples/radmeridional_candidate.toml
```

Run the small optimization example with:

```bash
hydroflow-opt check examples/radmeridional_optimization.toml
hydroflow-opt optimize examples/radmeridional_optimization.toml
```

The configured output and scratch directories contain a separate request,
result, standard-output log, standard-error log, and scratch directory for
each candidate.

### Slurm smoke test

Use the staged Slurm example to run the historical candidate with two
OpenFOAM ranks:

```bash
hydroflow-opt check examples/radmeridional_candidate_slurm.toml
```

Submit it from an allocation that provides two physical cores:

```bash
#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --hint=nomultithread

source /path/to/the/runtime-environment.sh
cd /path/to/hydroFoil_bwRSE4HPC

srun --mpi=list
radmeridional-opt check-runtime
hydroflow-opt run examples/radmeridional_candidate_slurm.toml
```

The Python worker runs once. Its two `simpleFoam` stages are launched as
exclusive two-task Slurm job steps. Do not wrap `hydroflow-opt` itself in
`srun`; the backend creates the solver steps from inside the allocation.

## Troubleshooting

### Python imports use the wrong interpreter

Confirm that `python`, pip, and the interpreter given to CMake all belong to
the same environment:

```bash
command -v python
python -m pip --version
grep Python3_EXECUTABLE "${DTOO_SOURCE}/build/CMakeCache.txt"
```

Reconfigure and rebuild dtOO if the Python environment or minor version
changes.

### A dtOO library cannot be found at runtime

Confirm that `DTOO_EXTERNLIBS`, `PYTHONPATH`, and `LD_LIBRARY_PATH` are set in
the shell that starts `hydroflow-opt`:

```bash
printf '%s\n' "${DTOO_EXTERNLIBS}" "${PYTHONPATH}" "${LD_LIBRARY_PATH}"
```

### An evaluation immediately reuses an earlier failure

`hydroflow-opt` caches terminal results for identical candidate requests. Use
a new candidate identifier or remove the failed candidate's `result.json`
before retrying after repairing the runtime. When `result.json` is absent,
the previous request and logs are archived automatically before the retry.

### Preserve the software versions

Store the dtOO, dtOO-ThirdParty, and foamFine revisions together with the
Python environment:

```bash
python -m pip freeze > python-requirements.lock
git -C "${DTOO_SOURCE}" rev-parse HEAD
git -C "${DTOO_SOURCE}/dtOO-ThirdParty" rev-parse HEAD
git -C "${FOAMFINE_DIR}" rev-parse HEAD
```
