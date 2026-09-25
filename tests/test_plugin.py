import json

import pytest

import radmeridional_opt.runtime as runtime
import radmeridional_opt.runtime_check as runtime_check
from radmeridional_opt.case import RadMeridionalCase
from radmeridional_opt.cli import main as cli_main
from radmeridional_opt.runtime_check import CheckResult
from radmeridional_opt.worker import main


def test_case_exposes_the_radmeridional_parameter_space():
    case = RadMeridionalCase()
    space = case.parameter_space({})
    assert space.names == ("alpha_1", "alpha_2", "t_mid")
    assert space.lower_bounds == (150.0, 155.0, 0.01)
    assert case.worker_placement() == "controller"


def test_runtime_passes_backend_solver_launcher_to_legacy(
    monkeypatch, tmp_path
):
    calls = []

    class FakeImplementation:
        @staticmethod
        def runRadMeridional(vector, state, *, solver_launcher):
            calls.append((vector, state, solver_launcher))
            return 1.25, {"dHMean": 1.0}, state, {"started": True}

    monkeypatch.setattr(
        runtime, "_load_implementation", lambda: FakeImplementation()
    )
    request = {
        "candidate": {
            "id": "candidate-1",
            "parameters": {
                "alpha_1": 160.0,
                "alpha_2": 165.0,
                "t_mid": 0.05,
            },
        },
        "context": {
            "scratch_dir": str(tmp_path / "scratch"),
            "resources": {"mpi_ranks": 2},
            "execution": {
                "backend": "slurm",
                "mpi_launcher": [
                    "srun",
                    "--exclusive",
                    "--ntasks=2",
                ],
            },
        },
    }

    objective, metadata = runtime.evaluate(request)

    assert objective == 1.25
    assert metadata["state"] == "candidate-1"
    assert calls == [
        (
            [160.0, 165.0, 0.05],
            "candidate-1",
            ["srun", "--exclusive", "--ntasks=2"],
        )
    ]


def test_runtime_defaults_old_requests_to_local_mpiexec(tmp_path):
    request = {
        "context": {
            "scratch_dir": str(tmp_path),
            "resources": {"mpi_ranks": 2},
        }
    }

    assert runtime._solver_launcher(request, 2) == ["mpiexec", "-n", "2"]


def test_runtime_propagates_legacy_evaluation_failure(monkeypatch, tmp_path):
    class FailedImplementation:
        @staticmethod
        def runRadMeridional(vector, state, *, solver_launcher):
            del vector, state, solver_launcher
            raise RuntimeError("simpleFoam failed")

    monkeypatch.setattr(
        runtime, "_load_implementation", lambda: FailedImplementation()
    )
    request = {
        "candidate": {
            "id": "candidate-1",
            "parameters": {
                "alpha_1": 160.0,
                "alpha_2": 165.0,
                "t_mid": 0.05,
            },
        },
        "context": {
            "scratch_dir": str(tmp_path / "scratch"),
            "resources": {"mpi_ranks": 1},
        },
    }

    with pytest.raises(RuntimeError, match="simpleFoam failed"):
        runtime.evaluate(request)


def test_worker_returns_a_structured_failure_without_cfd_runtime(tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(
        json.dumps(
            {
                "candidate": {
                    "id": "test-1",
                    "parameters": {
                        "alpha_1": 160.0,
                        "alpha_2": 165.0,
                        "t_mid": 0.05,
                    },
                },
                "context": {
                    "scratch_dir": str(tmp_path / "scratch"),
                    "resources": {"mpi_ranks": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    assert main([str(request_path), str(result_path)]) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["candidate_id"] == "test-1"
    assert result["status"] == "failed"


def test_runtime_check_reports_missing_runtime(monkeypatch, tmp_path):
    implementation = tmp_path / "runRadMeridional.py"
    implementation.write_text("# test implementation\n", encoding="utf-8")

    def fake_import_module(name):
        if name == "dtOOPythonSWIG":
            raise ImportError("missing dtOO")
        return object()

    monkeypatch.setattr(runtime_check, "import_module", fake_import_module)
    monkeypatch.setattr(runtime_check, "which", lambda name: None)
    monkeypatch.setattr(
        runtime_check, "_implementation_path", lambda: implementation
    )

    results = runtime_check.run_checks()
    report = runtime_check.format_report(results, environ={})

    assert runtime_check.failed_required_count(results) == 3
    assert "FAIL import dtOOPythonSWIG" in report
    assert "FAIL executable simpleFoam" in report
    assert "Runtime check failed: 3 required check(s) failed." in report


def test_runtime_check_passes_when_requirements_are_available(
    monkeypatch, tmp_path
):
    implementation = tmp_path / "runRadMeridional.py"
    implementation.write_text("# test implementation\n", encoding="utf-8")

    monkeypatch.setattr(
        runtime_check, "import_module", lambda module_name: object()
    )
    monkeypatch.setattr(
        runtime_check, "which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(
        runtime_check, "_implementation_path", lambda: implementation
    )

    results = runtime_check.run_checks()
    report = runtime_check.format_report(
        results,
        environ={"FLOW_OPT_MPI_RANKS": "2"},
    )

    assert runtime_check.failed_required_count(results) == 0
    assert "OK   import dtOOPythonSWIG" in report
    assert "FLOW_OPT_MPI_RANKS=2" in report
    assert "Runtime check passed." in report


def test_runtime_cli_returns_nonzero_for_failed_checks(monkeypatch):
    monkeypatch.setattr(
        "radmeridional_opt.cli.run_checks",
        lambda: [CheckResult("import dtOOPythonSWIG", False)],
    )

    assert cli_main(["check-runtime"]) == 1


def test_runtime_cli_returns_zero_for_successful_checks(monkeypatch):
    monkeypatch.setattr(
        "radmeridional_opt.cli.run_checks",
        lambda: [CheckResult("import dtOOPythonSWIG", True)],
    )

    assert cli_main(["check-runtime"]) == 0
