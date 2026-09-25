"""Runtime environment checks for the radmeridional case plugin."""

from dataclasses import dataclass
from importlib import import_module
from shutil import which

from radmeridional_opt.runtime import _implementation_path


@dataclass(frozen=True)
class CheckResult:
    """Result of one runtime readiness check."""

    name: str
    passed: bool
    detail: str = ""
    required: bool = True


def run_checks() -> list[CheckResult]:
    """Run all radmeridional runtime checks.

    Returns
    -------
    list[CheckResult]
        Individual check results. Required failed checks should make the CLI
        return a non-zero exit status.
    """

    return [
        _check_import("dtOOPythonSWIG"),
        _check_import("pyDtOO"),
        _check_import("dtOOPythonApp.builder"),
        _check_import("hydroflow_opt"),
        _check_import("radmeridional_opt"),
        _check_executable("simpleFoam"),
        _check_executable("mpiexec"),
        _check_implementation(),
    ]


def failed_required_count(results: list[CheckResult]) -> int:
    """Count required checks that failed."""

    return sum(
        1 for result in results if result.required and not result.passed
    )


def format_report(
    results: list[CheckResult],
    *,
    environ: dict[str, str],
) -> str:
    """Format runtime check results for human-readable terminal output.

    Parameters
    ----------
    results
        Runtime check results to render.
    environ
        Environment mapping used to report relevant variables.

    Returns
    -------
    str
        Multi-line report suitable for printing to stdout.
    """

    lines = ["radmeridional-opt runtime check", ""]
    for result in results:
        status = "OK  " if result.passed else "FAIL"
        detail = f": {result.detail}" if result.detail else ""
        lines.append(f"{status} {result.name}{detail}")

    lines.extend(
        [
            "",
            "Environment",
            _format_env("TMPDIR", environ, default="<not set>"),
            _format_env("PYTHONPATH", environ, default="<not set>"),
            _format_env("LD_LIBRARY_PATH", environ, default="<not set>"),
            _format_env(
                "FLOW_OPT_MPI_RANKS",
                environ,
                default="<not set; hydroflow-opt supplies this>",
            ),
            "",
        ]
    )
    failed = failed_required_count(results)
    if failed:
        lines.append(
            f"Runtime check failed: {failed} required check(s) failed."
        )
    else:
        lines.append("Runtime check passed.")
    return "\n".join(lines)


def _check_import(module_name: str) -> CheckResult:
    try:
        import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary.
        return CheckResult(
            name=f"import {module_name}",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    return CheckResult(name=f"import {module_name}", passed=True)


def _check_executable(name: str) -> CheckResult:
    path = which(name)
    if path is None:
        return CheckResult(
            name=f"executable {name}",
            passed=False,
            detail="not found on PATH",
        )
    return CheckResult(name=f"executable {name}", passed=True, detail=path)


def _check_implementation() -> CheckResult:
    try:
        path = _implementation_path()
    except Exception as exc:  # noqa: BLE001 - diagnostic boundary.
        return CheckResult(
            name="runRadMeridional.py",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        )
    if not path.exists():
        return CheckResult(
            name="runRadMeridional.py",
            passed=False,
            detail=f"not found at {path}",
        )
    return CheckResult(name="runRadMeridional.py", passed=True, detail=str(path))


def _format_env(
    name: str,
    environ: dict[str, str],
    *,
    default: str,
) -> str:
    return f"  {name}={environ.get(name, default)}"
