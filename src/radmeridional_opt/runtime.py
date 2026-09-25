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


def prepare(request_path: Path, state_path: Path) -> None:
    """Generate and decompose one case, ready for the laminar solve."""
    request = _read_json(request_path)
    options = SolverOptions.from_options(
        request.get("case", {}).get("options", {})
    )
    candidate = request["candidate"]
    candidate_id = str(candidate["id"])
    state = _state_label(candidate_id)
    parameters = candidate["parameters"]
    vector = [float(parameters[item.name]) for item in PARAMETERS]
    resources = request["context"]["resources"]
    mpi_ranks = int(resources["mpi_ranks"])
    if mpi_ranks < 1:
        raise ValueError("mpi_ranks must be at least one")

    scratch_dir = Path(request["context"]["scratch_dir"]).resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(scratch_dir)
    work_dir = _stage_case(scratch_dir)


    with _working_directory(work_dir):
        implementation = _load_implementation(work_dir)
        evaluation = implementation.runRadMeridional(vector, state)
        evaluation.pre()
        
        #if not evaluation.MeshOk_:
        #    raise RuntimeError(f"mesh generation failed for {state}")
        history = evaluation.get_history()

    case_dir = work_dir / f"of_{state}"
    _run_case_command(case_dir, ["checkMesh"], "log.checkMesh")
    if mpi_ranks > 1:
        _configure_decomposition(case_dir, mpi_ranks)
        _run_case_command(
            case_dir,
            ["decomposePar", "-fileHandler", "collated"],
            "log.decomposePar",
        )
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


def configure_turbulent(state_path: Path) -> None:
    """Switch a prepared case from laminar to turbulent settings."""
    state = _read_state(state_path)
    options = SolverOptions.from_options(state.get("solver_options", {}))
    _configure_turbulent(Path(state["case_dir"]), options.end_time)


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
    if mpi_ranks > 1:
        _run_case_command(case_dir, ["reconstructPar"], "log.reconstructPar")
        for processor_dir in case_dir.glob("processor*"):
            if processor_dir.is_dir():
                shutil.rmtree(processor_dir)

    with _working_directory(work_dir):

        implementation = _load_implementation(work_dir)
        evaluation = implementation.runRadMeridional(vector, state)
        evaluation.history_.update(state_data.get("history", {}))
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

    print("TEST: current working directory")
    print(Path.cwd())
    print("TEST: sys.path")
    
    print(
        "radmeridional_files exists:",
        (work_dir / "radmeridional_files").exists(),
    )

    print(
        "radMeridional.py exists:",
        (work_dir / "radmeridional_files" / "radMeridional.py").exists(),
    )
    for path in sys.path:
        print(path)

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


#"""Runtime bridge to the radmeridional CFD implementation.
#
#The external dtOO, foamlib, and OpenFOAM runtime is deliberately imported only
#when a worker is actually evaluating a candidate.  This keeps the plugin
#installable and unit-testable on a development laptop.
#"""
#
#from __future__ import annotations
#
#import importlib.util
#import os
#import sys
#from importlib.resources import files
#from pathlib import Path
#from typing import Any
#
#
#def evaluate(request: dict[str, Any]) -> tuple[float, dict[str, Any]]:
#    """Evaluate one candidate with the established radmeridional physics code.
#
#    The legacy implementation is loaded only here while its geometry and CFD
#    implementation is being split further.  It contains no Pyro dependency;
#    the process boundary and all scheduling now belong to hydroflow-opt .
#    """
#    scratch_dir = Path(request["context"]["scratch_dir"])
#    scratch_dir.mkdir(parents=True, exist_ok=True)
#    resources = request["context"]["resources"]
#    mpi_ranks = int(resources["mpi_ranks"])
#    if mpi_ranks < 1:
#        raise ValueError("mpi_ranks must be at least one")
#    os.environ["TMPDIR"] = str(scratch_dir)
#    os.environ["FLOW_OPT_MPI_RANKS"] = str(mpi_ranks)
#    module = _load_implementation()
#    parameters = request["candidate"]["parameters"]
#    candidate_id = request["candidate"]["id"]
#    fitness, extra, state, history = module.runRadMeridional(
#        [
#            float(parameters["alpha_1_0"]),
#            float(parameters["alpha_1_1"]),
#            float(parameters["alpha_1_2"]),
#            float(parameters["alpha_2_0"]),
#            float(parameters["alpha_2_1"]),
#            float(parameters["alpha_2_2"]),
#            float(parameters["alpha_2_3"]),
#            float(parameters["ratioX_0"]),
#            float(parameters["ratioX_1"]),
#            float(parameters["ratioX_2"]),
#            float(parameters["ratioX_3"]),
#            float(parameters["deltaY_0"]),
#            float(parameters["deltaY_1"]),
#            float(parameters["deltaY_2"]),
#            float(parameters["deltaY_3"]),
#        ],
#        candidate_id,
#        solver_launcher=_solver_launcher(request, mpi_ranks),
#    )
#    return float(fitness), {
#        "state": state,
#        "fitness_components": extra,
#        "history": history,
#    }
#
#
#def _solver_launcher(request: dict[str, Any], mpi_ranks: int) -> list[str]:
#    """Return the backend-provided command prefix for ``simpleFoam``."""
#
#    execution = request["context"].get("execution")
#    if execution is None:
#        return ["mpiexec", "-n", str(mpi_ranks)] if mpi_ranks > 1 else []
#    launcher = execution.get("mpi_launcher")
#    if not isinstance(launcher, list) or not all(
#        isinstance(item, str) and item for item in launcher
#    ):
#        raise TypeError("context.execution.mpi_launcher must be a string list")
#    return list(launcher)
#
#
#def _load_implementation() -> Any:
#    source = _implementation_path()
#    if not source.exists():
#        raise RuntimeError(
#            "radmeridional implementation is unavailable; install from the "
#            "radmeridional-opt source checkout with its CFD runtime"
#        )
#    sys.path.insert(0, str(source.parent))
#    spec = importlib.util.spec_from_file_location(
#        "radmeridional_implementation", source
#    )
#    if spec is None or spec.loader is None:
#        raise RuntimeError(
#            f"cannot load radmeridional implementation from {source}"
#        )
#    module = importlib.util.module_from_spec(spec)
#    spec.loader.exec_module(module)
#    return module
#
#
#def _implementation_path() -> Path:
#    bundled = files("radmeridional_opt").joinpath("_legacy", "runRadMeridional.py")
#    if bundled.is_file():
#        return Path(bundled)
#    return Path(__file__).resolve().parents[2] / "runRadMeridional.py"
