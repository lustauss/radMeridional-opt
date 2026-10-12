"""Implementation of the explicit radMeridional evaluation stages.

The external dtOO runtime is imported only after a candidate-local copy of the
supplied case has been created. This keeps plugin discovery lightweight and
prevents concurrent candidates from sharing mutable files.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from hydroflow_opt.models import EvaluationResult
from hydroflow_opt.results import write_result

from radmeridional_opt.case import PARAMETERS, _state_label
from radmeridional_opt.options import SolverOptions

# prepare stage 
def prepare(request_path: Path, state_path: Path) -> None:
    """Generate and decompose one case, ready for the laminar solve."""
    # hydroflow-opt information management
    request = _read_json(request_path)
    options = SolverOptions.from_options(
        request.get("case", {}).get("options", {})
    )
    candidate = request["candidate"]
    candidate_id = str(candidate["id"])
    # state name of the of-case is of_rad_<id>
    state = _state_label(candidate_id)

    # optimization parameters
    parameters = candidate["parameters"]
    vector = [float(parameters[item.name]) for item in PARAMETERS]

    # solver resources
    resources = request["context"]["resources"]
    mpi_ranks = int(resources["mpi_ranks"])
    if mpi_ranks < 1:
        raise ValueError("mpi_ranks must be at least one")
    
    # scratch dir specified in CONFIG
    scratch_dir = Path(request["context"]["scratch_dir"]).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    # "TMPDIR" only works for mpi_ranks = 1
    os.environ["TMPDIR"] = str(scratch_dir)
    # directory where the of-case is located and solved
    work_dir = _stage_case(scratch_dir)

    # run the following steps in the work_dir
    with _working_directory(work_dir):
        # import runRadMeridional.py as implementation of radMeridional
        implementation = _load_implementation(work_dir)
        # create runRadMeridional object
        # hand over parameter list (vector) and state name (state)
        evaluation = implementation.runRadMeridional(vector, state)
        # run pre
        #   - geometry generation
        #   - openfoam case creation (mesh gen with timeout)
        #   - simulation setup
        evaluation.pre()
        
        # mesh ok is True if of-case was created sucesfully
        if not evaluation.MeshOk_:
            raise RuntimeError(f"mesh generation failed for {state}")
        history = evaluation.get_history()
    
    # run checkMesh
    case_dir = work_dir / f"of_{state}"
    _run_case_command(case_dir, ["checkMesh"], "log.checkMesh")
    
    # case decomposition
    if mpi_ranks > 1:
        _configure_decomposition(case_dir, mpi_ranks)
        _run_case_command(
            case_dir,
            ["decomposePar", "-fileHandler", "collated"],
            "log.decomposePar",
        )
    # edit of-case to laminar settings
    #   - laminar end time
    #   - write interval
    #   - turbulence off
    _configure_laminar(case_dir, options.laminar_iterations)

    _write_json(
        state_path,
        {
            "candidate_id": candidate_id,
            "state": state,
            "vector": vector,
            "mpi_ranks": mpi_ranks,
            "solver_options": asdict(options),
            "work_dir": str(work_dir),
            "case_dir": str(case_dir),
            "mesh_path": str(work_dir / f"{state}_ru_gridGmsh.msh"),
            "history": _json_compatible(history),
        },
    )

# configure turbulent stage
def configure_turbulent(state_path: Path) -> None:
    """Switch a prepared case from laminar to turbulent settings."""
    state = _read_state(state_path)
    # simulation end time is specified in options.py
    options = SolverOptions.from_options(state.get("solver_options", {}))
    _configure_turbulent(Path(state["case_dir"]), options.end_time)

# finalize stage
def finalize(
    request_path: Path,
    state_path: Path,
    result_path: Path,
) -> None:
    """Reconstruct, evaluate, persist, and then clean a completed case."""
    request = _read_json(request_path)
    state_data = _read_state(state_path)
    options = SolverOptions.from_options(state_data.get("solver_options", {}))
    candidate_id = str(request["candidate"]["id"])
    if state_data["candidate_id"] != candidate_id:
        raise ValueError("radMeridional state does not match the candidate request")

    work_dir = Path(state_data["work_dir"])
    case_dir = Path(state_data["case_dir"])
    mpi_ranks = int(state_data["mpi_ranks"])
    state = str(state_data["state"])
    vector = [float(value) for value in state_data["vector"]]

    # reconstruct simulation
    if mpi_ranks > 1:
        _run_case_command(case_dir, ["reconstructPar"], "log.reconstructPar")
        for processor_dir in case_dir.glob("processor*"):
            # remove processor folders
            if processor_dir.is_dir():
                shutil.rmtree(processor_dir)
    
    # execute the following steps in th working directory
    with _working_directory(work_dir):
        # import runRadMeridional class
        implementation = _load_implementation(work_dir)
        evaluation = implementation.runRadMeridional(vector, state)
        # get history
        evaluation.history_.update(state_data.get("history", {}))
        # run evaluate method to return fitness values
        #   - fitness: defined fitness function
        #   - extra: eta, moment, head
        fitness, extra = evaluation.evaluate(
            laminar_end_time=options.laminar_iterations,
            end_time=options.end_time,
        )
        history = evaluation.get_history()

    result = EvaluationResult.success(
        candidate_id,
        float(fitness),
        metadata={
            "state": state,
            "solver_options": asdict(options),
            "fitness_components": _json_compatible(extra),
            "history": _json_compatible(history),
        },
    )
    write_result(result_path, result)
    
    ## delete case data from working directory
    #with _working_directory(work_dir):
    #    implementation.cleanup(state)


def _configure_decomposition(case_dir: Path, mpi_ranks: int) -> None:
    path = case_dir / "system" / "decomposeParDict"
    _replace_assignment(path, "numberOfSubdomains", str(mpi_ranks))
    #_replace_assignment(path, "method", "scotch")
    _replace_assignment(path, "method", "metis")


def _configure_laminar(case_dir: Path, end_time: int = 100) -> None:
    _replace_assignment(
        case_dir / "system" / "controlDict", "endTime", str(end_time)
    )
    _replace_assignment(
        case_dir / "system" / "controlDict", "writeInterval", str(end_time)
    )
    _replace_assignment(
        case_dir / "constant" / "turbulenceProperties",
        "turbulence",
        "off",
    )
    #_replace_text(case_dir / "system" / "fvSchemes", "cellL", "faceL")


def _configure_turbulent(case_dir: Path, end_time: int = 500) -> None:
    _replace_assignment(
        case_dir / "system" / "controlDict", "endTime", str(end_time)
    )
    _replace_assignment(
        case_dir / "system" / "controlDict", "writeInterval", str(end_time)
    )
    _replace_assignment(
        case_dir / "constant" / "turbulenceProperties",
        "turbulence",
        "on",
    )
    #_replace_text(case_dir / "system" / "fvSchemes", "faceL", "cellL")


def _replace_assignment(path: Path, name: str, value: str) -> None:
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*{re.escape(name)}\s+)[^;]+;", re.MULTILINE)
    updated, count = pattern.subn(rf"\g<1>{value};", content)
    if count == 0:
        raise RuntimeError(f"cannot find '{name}' assignment in {path}")
    path.write_text(updated, encoding="utf-8")


def _replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    if old not in content:
        raise RuntimeError(f"cannot find '{old}' in {path}")
    path.write_text(content.replace(old, new), encoding="utf-8")


def _run_case_command(
    case_dir: Path, command: list[str], log_name: str
) -> None:
    with (case_dir / log_name).open("w", encoding="utf-8") as log:
        subprocess.run(
            command,
            check=True,
            cwd=case_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

def _stage_case(scratch_dir: Path) -> Path:
    """Copy immutable package resources into a candidate-local work tree."""
    work_dir = scratch_dir / "radmeridional"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    package_root = _package_root()
    legacy_root = package_root / "_legacy"
    #data_root = package_root / "_case_data"
    shutil.copy2(legacy_root / "runRadMeridional.py", work_dir / "runRadMeridional.py")
    _copy_tree(legacy_root / "radmeridional_files", work_dir / "radmeridional_files")
    #_copy_tree(data_root / "xml", work_dir / "xml")
    #_copy_tree(
    #    data_root / "boundaryData_RU_INLET",
    #    work_dir / "boundaryData_RU_INLET",
    #)
    return work_dir

def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"radMeridional package resource is missing: {source}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _load_implementation(work_dir: Path) -> Any:
    source = work_dir / "runRadMeridional.py"
    sys.path.insert(0, str(work_dir))

    try:
        spec = importlib.util.spec_from_file_location(
            "radmeridional_implementation", source
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(
                f"cannot load radMeridional implementation from {source}"
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(work_dir))


def _package_root() -> Path:
    root = files("radmeridional_opt")
    if not isinstance(root, Path):
        raise RuntimeError("radmeridional-opt requires an unpacked installation")
    return root


def _implementation_path() -> Path:
    """Return the bundled legacy entry point for diagnostics."""
    return _package_root() / "_legacy" / "runRadMeridional.py"


def _read_state(path: Path) -> dict[str, Any]:
    state = _read_json(path)
    required = {
        "candidate_id",
        "state",
        "vector",
        "mpi_ranks",
        "work_dir",
        "case_dir",
    }
    missing = required.difference(state)
    if missing:
        raise ValueError(
            "radmeridional state is missing: " + ", ".join(sorted(missing))
        )
    return state


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_compatible(item) for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _json_compatible(tolist())
    item = getattr(value, "item", None)
    if callable(item):
        return _json_compatible(item())
    return value


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


