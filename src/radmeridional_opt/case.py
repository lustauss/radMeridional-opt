"""Case declaration for hydroflow-opt without importing CFD dependencies."""

import sys
import zlib
from dataclasses import dataclass
from typing import Any

from hydroflow_opt.models import (
    Candidate,
    EvaluationPaths,
    EvaluationPlan,
    EvaluationStage,
    ParameterSpace,
    ResourceRequest,
    StageResources,
)

from radmeridional_opt.options import SolverOptions

@dataclass(frozen=True)
class ParameterDefinition:
    """One named optimizer parameter and its legacy dtOO label."""

    name: str
    lower_bound: float
    upper_bound: float


PARAMETERS = (
    ParameterDefinition("alpha_1_0", 85.0, 95.0),
    ParameterDefinition("alpha_1_1", 70.0, 80.0),
    ParameterDefinition("alpha_1_2", 47.0, 57.0),

    ParameterDefinition("alpha_2_0", 40.0, 50.0),
    ParameterDefinition("alpha_2_1", 22.0, 32.0),
    ParameterDefinition("alpha_2_2", 20.0, 30.0),
    ParameterDefinition("alpha_2_3", 8.00, 12.0),

    ParameterDefinition("ratioX_0", 0.60, 0.70),
    ParameterDefinition("ratioX_1", 0.60, 0.70),
    ParameterDefinition("ratioX_2", 0.10, 0.20),
    ParameterDefinition("ratioX_3", 0.19, 0.29),

    ParameterDefinition("deltaY_0", 0.75, 0.85),
    ParameterDefinition("deltaY_1", 0.70, 0.80),
    ParameterDefinition("deltaY_2", 0.70, 0.80),
    ParameterDefinition("deltaY_3", 0.48, 0.58),
)

class RadMeridionalCase:
    """Expose the radmeridional's parameters and isolated worker command."""

    def parameter_space(self, options: dict[str, Any]) -> ParameterSpace:
        """Return the physical optimization bounds for TiStoS."""
        SolverOptions.from_options(options)
        return ParameterSpace(
            names=tuple(parameter.name for parameter in PARAMETERS),
            lower_bounds=tuple(
                parameter.lower_bound for parameter in PARAMETERS
            ),
            upper_bounds=tuple(
                parameter.upper_bound for parameter in PARAMETERS
            ),
        )
    
    def evaluation_plan(
        self,
        candidate: Candidate,
        paths: EvaluationPaths,
        resources: ResourceRequest,
    ) -> EvaluationPlan:
        
        """Return the serial preparation and parallel solver stages."""
        state = _state_label(candidate.id)
        work_dir = paths.scratch_dir / "radmeridional"
        case_dir = work_dir / f"of_{state}"
        state_path = paths.evaluation_dir / "radmeridional-state.json"
        python_stage = (sys.executable, "-m", "radmeridional_opt.stages")
        solver_resources = StageResources(
            processes=resources.mpi_ranks,
            threads_per_process=resources.threads_per_rank,
        )
        solver_command: tuple[str, ...] = ("simpleFoam",)
        if resources.mpi_ranks > 1:
            solver_command += ("-parallel", "-fileHandler", "collated")

        return EvaluationPlan(
            stages=(
                EvaluationStage(
                    name="prepare",
                    command=(
                        *python_stage,
                        "prepare",
                        str(paths.request_path),
                        str(state_path),
                    ),
                    working_directory=paths.scratch_dir,
                ),
                EvaluationStage(
                    name="solve-laminar",
                    command=solver_command,
                    working_directory=case_dir,
                    resources=solver_resources,
                ),
                EvaluationStage(
                    name="configure-turbulent",
                    command=(
                        *python_stage,
                        "configure-turbulent",
                        str(state_path),
                    ),
                    working_directory=case_dir,
                ),
                EvaluationStage(
                    name="solve-turbulent",
                    command=solver_command,
                    working_directory=case_dir,
                    resources=solver_resources,
                ),
                EvaluationStage(
                    name="finalize",
                    command=(
                        *python_stage,
                        "finalize",
                        str(paths.request_path),
                        str(state_path),
                        str(paths.result_path),
                    ),
                    working_directory=work_dir,
                ),
            )
        )


def _state_label(candidate_id: str) -> str:
    """Create the numeric-suffix state label required by legacy rad."""
    number = zlib.crc32(candidate_id.encode("utf-8"))
    return f"rad_{number}"
