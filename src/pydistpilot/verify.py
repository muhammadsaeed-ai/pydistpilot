"""End-to-end build, static audit, and installed-artifact smoke verification."""

from __future__ import annotations

import site
import sysconfig
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tarfile
import zipfile
import venv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydistpilot import __version__
from pydistpilot.archive import ArchiveAuditError, audit_sdist, audit_wheel, extract_sdist_safely
from pydistpilot.config import ConfigError, load_config
from pydistpilot.models import ArtifactResult, Finding, SmokeResult, VerificationReport
from pydistpilot.process import run_process

_IMPORT_PROBE = r"""
import importlib, json, pathlib, sys
name = sys.argv[1]
root = pathlib.Path(sys.argv[2]).resolve()
module = importlib.import_module(name)
spec = getattr(module, "__spec__", None)
paths = []
origin = getattr(spec, "origin", None) if spec else None
if origin and origin not in {"built-in", "frozen", "namespace"}:
    paths.append(pathlib.Path(origin).resolve())
locations = getattr(spec, "submodule_search_locations", None) if spec else None
if locations:
    paths.extend(pathlib.Path(item).resolve() for item in locations)
inside = bool(paths) and all(item == root or root in item.parents for item in paths)
print(json.dumps({"module": name, "origin": str(paths[0]) if paths else None,
                  "locations": [str(p) for p in paths], "inside_environment": inside}))
if not inside:
    raise SystemExit(41)
"""


def _finding(code: str, message: str, recommendation: str, evidence: str | None = None) -> Finding:
    return Finding(code, "error", message, recommendation, evidence=evidence)


def _report_path(report: VerificationReport, temporary_root: Path, keep_artifacts: bool) -> None:
    if keep_artifacts:
        return
    prefix = str(temporary_root)
    for artifact in report.artifacts:
        artifact.path = Path(artifact.path).name
        for finding in artifact.findings:
            if finding.path and finding.path.startswith(prefix):
                finding.path = "<temporary artifact>" + finding.path[len(prefix):]
    for finding in report.findings:
        if finding.path and finding.path.startswith(prefix):
            finding.path = "<temporary artifact>" + finding.path[len(prefix):]


def _run_checked(
    report: VerificationReport,
    argv: list[str | os.PathLike[str]],
    *,
    cwd: Path,
    timeout: float,
    code: str,
    step_name: str,
) -> bool:
    try:
        result = run_process(argv, cwd=cwd, timeout=timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        report.findings.append(_finding(code, f"Could not start {step_name}.",
                                        "Confirm the Python executable and working directory are available.", str(exc)[:500]))
        return False
    if result.timed_out:
        report.findings.append(_finding(code, f"{step_name} exceeded the {timeout:g}-second timeout.",
                                        "Inspect the build backend or CLI entry point; increase --timeout only when the longer run is expected.",
                                        result.output[-2000:] or "No output captured."))
        return False
    if result.returncode != 0:
        report.findings.append(_finding(code, f"{step_name} exited with status {result.returncode}.",
                                        "Review the redacted output and fix the underlying build, install, or smoke-test failure.",
                                        result.output[-2000:] or "No output captured."))
        return False
    return True


def _wheel_files(result: ArtifactResult) -> list[str]:
    return result.imports


def _test_installed_wheel(
    report: VerificationReport,
    wheel: Path,
    artifact: ArtifactResult,
    import_names: list[str],
    *,
    timeout: float,
    install_deps: bool,
    stage: str,
    temporary_root: Path,
) -> None:
    start = time.monotonic()
    env_dir = temporary_root / f"venv-{stage}"
    smoke_dir = temporary_root / f"cwd-{stage}"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    try:
        builder = venv.EnvBuilder(with_pip=True, clear=False, symlinks=(os.name != "nt"))
        builder.create(env_dir)
    except (OSError, subprocess.SubprocessError) as exc:
        report.findings.append(_finding("PD110", "Could not create an isolated virtual environment.",
                                        "Use a Python installation that includes venv/ensurepip support.", str(exc)[:500]))
        report.smoke_checks.append(SmokeResult(wheel.name, "venv-create", stage, "failed",
                                                time.monotonic() - start, str(exc)[:300]))
        return
    python_exe = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    pip_args = [str(python_exe), "-m", "pip", "install"]
    if not install_deps:
        pip_args.extend(["--no-index", "--no-deps"])
    pip_args.append(str(wheel.resolve()))
    install_started = time.monotonic()
    try:
        install = run_process(pip_args, cwd=smoke_dir, timeout=timeout)
    except (OSError, ValueError, RuntimeError) as exc:
        report.findings.append(_finding("PD111", f"Could not install {wheel.name} into a fresh environment.",
                                        "Check venv creation and local artifact readability.", str(exc)[:500]))
        report.smoke_checks.append(SmokeResult(wheel.name, "wheel-install", stage, "failed",
                                                time.monotonic() - install_started, str(exc)[:300]))
        return
    if install.timed_out or install.returncode != 0:
        advice = "Run with --install-deps only if the package's declared dependencies are intended to be resolved from the configured package index." if not install_deps else "Review the installation output, dependency constraints, and configured package index."
        report.findings.append(_finding("PD112", f"Installation of {wheel.name} in a fresh virtual environment failed.",
                                        advice, install.output[-2000:] or "No output captured."))
        report.smoke_checks.append(SmokeResult(wheel.name, "wheel-install", stage, "failed",
                                                time.monotonic() - install_started,
                                                "timed out" if install.timed_out else f"exit={install.returncode}"))
        return
    report.smoke_checks.append(SmokeResult(wheel.name, "wheel-install", stage, "passed",
                                            time.monotonic() - install_started,
                                            "Installed into a fresh virtual environment."))

    if not import_names:
        report.findings.append(Finding("PD113", "warning", "No import smoke targets could be inferred from the wheel.",
                                       "Set [tool.pydistpilot].imports in pyproject.toml or pass --import package_name.",
                                       wheel.name))
    for module_name in import_names:
        check_started = time.monotonic()
        try:
            probe = run_process([str(python_exe), "-I", "-c", _IMPORT_PROBE, module_name, str(env_dir.resolve())],
                                cwd=smoke_dir, timeout=timeout)
        except (OSError, ValueError, RuntimeError) as exc:
            report.findings.append(_finding("PD114", f"Could not run import smoke check for {module_name}.",
                                            "Confirm the temporary interpreter and import target are available.", str(exc)[:500]))
            report.smoke_checks.append(SmokeResult(wheel.name, "import", module_name, "failed",
                                                    time.monotonic() - check_started, str(exc)[:300]))
            continue
        ok = not probe.timed_out and probe.returncode == 0
        report.smoke_checks.append(SmokeResult(wheel.name, "import", module_name,
                                                "passed" if ok else "failed",
                                                time.monotonic() - check_started,
                                                "Imported from the installed environment." if ok else "Import failed or resolved outside the temporary environment; inspect the output below."))
        if not ok:
            reason = "timed out" if probe.timed_out else f"exit={probe.returncode}"
            report.findings.append(_finding("PD115", f"Import smoke test failed for {module_name} ({reason}).",
                                            "Ensure the module is included in the built artifact, its dependencies are declared, and import names are configured correctly.",
                                            probe.output[-2000:] or "No output captured."))

    if artifact.console_scripts:
        bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
        for command in artifact.console_scripts:
            check_started = time.monotonic()
            candidates = [bin_dir / command]
            if os.name == "nt":
                candidates.extend([bin_dir / f"{command}.exe", bin_dir / f"{command}.cmd", bin_dir / f"{command}.bat"])
            executable = next((item for item in candidates if item.is_file()), None)
            if executable is None:
                report.findings.append(_finding("PD116", f"Declared console script {command!r} was not installed.",
                                                "Check [project.scripts] or the build backend's entry-point configuration.", wheel.name))
                report.smoke_checks.append(SmokeResult(wheel.name, "console-script", command, "failed",
                                                        time.monotonic() - check_started, "executable not found"))
                continue
            try:
                result = run_process([str(executable), "--help"], cwd=smoke_dir, timeout=timeout)
            except (OSError, ValueError, RuntimeError) as exc:
                report.findings.append(_finding("PD117", f"Could not run {command} --help.",
                                                "Inspect the installed console-script launcher and its target.", str(exc)[:500]))
                report.smoke_checks.append(SmokeResult(wheel.name, "console-script", command, "failed",
                                                        time.monotonic() - check_started, str(exc)[:300]))
                continue
            ok = not result.timed_out and result.returncode == 0
            report.smoke_checks.append(SmokeResult(wheel.name, "console-script", command,
                                                    "passed" if ok else "failed",
                                                    time.monotonic() - check_started,
                                                    "--help returned exit status 0." if ok else "--help did not complete successfully."))
            if not ok:
                report.findings.append(_finding("PD118", f"Console script {command!r} failed its --help smoke test.",
                                                "Check its target function, imports, and documented CLI options.", result.output[-2000:] or "No output captured."))


def _select_build_frontend() -> str | None:
    """Prefer the installed PyPA build package, not a project-local ``build/`` folder."""
    roots: set[Path] = set()
    try:
        roots.add(Path(sysconfig.get_paths()["purelib"]))
    except (KeyError, OSError):
        pass
    try:
        roots.update(Path(item) for item in site.getsitepackages())
    except (AttributeError, OSError):
        pass
    if any((root / "build" / "__main__.py").is_file() for root in roots):
        return "build"
    if shutil.which("uv") is not None:
        return "uv"
    return None


def _build_argv(
    frontend: str,
    source: Path,
    out_dir: Path,
    *,
    build_isolation: bool,
    wheel_only: bool = False,
) -> list[str | os.PathLike[str]]:
    if frontend == "build":
        # Isolated mode prevents a project-local module/directory named ``build`` from
        # shadowing the installed PyPA frontend in the child process.
        argv: list[str | os.PathLike[str]] = [sys.executable, "-I", "-m", "build"]
        if not build_isolation:
            argv.append("--no-isolation")
        if wheel_only:
            argv.append("--wheel")
        argv.extend(["--outdir", str(out_dir), str(source)])
        return argv
    uv_path = shutil.which("uv")
    if frontend == "uv" and uv_path:
        argv = [uv_path, "build"]
        if not build_isolation:
            argv.append("--no-build-isolation")
        if wheel_only:
            argv.append("--wheel")
        argv.extend(["--out-dir", str(out_dir), str(source)])
        return argv
    raise ValueError(f"requested build frontend is unavailable: {frontend}")


def verify_project(
    project: Path,
    *,
    import_names: list[str] | None = None,
    timeout: float = 90.0,
    install_deps: bool = False,
    build_isolation: bool = False,
    keep_artifacts: Path | None = None,
) -> VerificationReport:
    """Build and verify source artifacts; executes trusted build and package code."""
    started_wall = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started = time.monotonic()
    project = project.resolve()
    report = VerificationReport(project=str(project), started_at=started_wall)
    if timeout <= 0 or timeout > 3600:
        report.findings.append(_finding("PD101", "Timeout must be greater than 0 and at most 3600 seconds.",
                                        "Use --timeout with a value in the range (0, 3600]."))
        report.duration_seconds = time.monotonic() - started
        return report
    if not project.is_dir():
        report.findings.append(_finding("PD102", "Project path is not a directory.",
                                        "Pass a project directory that contains a pyproject.toml build configuration.", str(project)))
        report.duration_seconds = time.monotonic() - started
        return report
    try:
        config = load_config(project)
    except ConfigError as exc:
        report.findings.append(_finding("PD103", "Project configuration could not be read.",
                                        "Fix the TOML syntax and confirm tool.pydistpilot.imports is an array of import names.", str(exc)))
        report.duration_seconds = time.monotonic() - started
        return report
    configured_imports = list(import_names if import_names is not None else config.get("imports", []))
    for module_name in configured_imports:
        if any(not part.isidentifier() for part in module_name.split(".")):
            report.findings.append(_finding("PD104", f"Invalid import smoke target {module_name!r}.",
                                            "Pass dotted Python module names such as package_name or package_name.submodule."))
    if any(f.severity == "error" for f in report.findings):
        report.duration_seconds = time.monotonic() - started
        return report
    if keep_artifacts is not None:
        keep_artifacts = keep_artifacts.expanduser().resolve()
        if keep_artifacts == project or project in keep_artifacts.parents:
            report.findings.append(_finding("PD105", "Artifact output directory cannot be the project or a directory inside it.",
                                            "Choose an output directory outside the source checkout so generated artifacts cannot contaminate the build.",
                                            str(keep_artifacts)))
            report.duration_seconds = time.monotonic() - started
            return report
        if keep_artifacts.exists() and (not keep_artifacts.is_dir() or any(keep_artifacts.iterdir())):
            report.findings.append(_finding("PD106", "Artifact output directory already exists and is not empty.",
                                            "Choose a new or empty output directory; PyDistPilot will not overwrite existing files.",
                                            str(keep_artifacts)))
            report.duration_seconds = time.monotonic() - started
            return report
    if not (project / "pyproject.toml").is_file():
        report.findings.append(Finding("PD107", "warning", "No pyproject.toml was found in the project root.",
                                       "Modern PEP 517 builds normally define [build-system] in pyproject.toml.", str(project)))
    frontend = _select_build_frontend()
    if frontend is None:
        report.findings.append(_finding("PD100", "No supported build frontend was found.",
                                        "Install the optional dependency with 'python -m pip install pydistpilot[build]' or install the uv CLI."))
        report.duration_seconds = time.monotonic() - started
        return report
    if frontend == "uv":
        report.findings.append(Finding("PD099", "info", "Using the installed uv CLI as the PEP 517 build frontend.",
                                       "Install pydistpilot[build] to use the preferred 'python -m build' frontend; both paths invoke the declared build backend.", str(project)))

    owns_temp = keep_artifacts is None
    artifact_dir: Path
    temp_context: tempfile.TemporaryDirectory[str] | None = None
    if keep_artifacts is None:
        temp_context = tempfile.TemporaryDirectory(prefix="pydistpilot-")
        temporary_root = Path(temp_context.name)
        artifact_dir = temporary_root / "artifacts"
        artifact_dir.mkdir()
    else:
        keep_artifacts.mkdir(parents=True, exist_ok=True)
        temporary_root = Path(tempfile.mkdtemp(prefix="pydistpilot-smoke-"))
        artifact_dir = keep_artifacts
    try:
        build_args = _build_argv(frontend, project, artifact_dir, build_isolation=build_isolation)
        _run_checked(report, build_args, cwd=project, timeout=timeout,
                     code="PD100", step_name="source project build")
        built_files = sorted(artifact_dir.iterdir())
        wheels = [item for item in built_files if item.is_file() and item.name.endswith(".whl")]
        sdists = [item for item in built_files if item.is_file() and item.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".zip"))]
        if not wheels or not sdists:
            report.findings.append(_finding("PD108", "Build did not produce both a wheel and a source distribution.",
                                            "Ensure the project's build backend supports both formats and inspect the build output.",
                                            f"wheels={len(wheels)}, sdists={len(sdists)}"))
        if len(wheels) > 1 or len(sdists) > 1:
            report.findings.append(Finding("PD119", "warning", "Build produced more than one wheel or source distribution; all matching artifacts will be inspected.",
                                           "Review multiple artifacts to confirm each target is intentional.", str(artifact_dir),
                                           f"wheels={len(wheels)}, sdists={len(sdists)}"))
        wheel_results = [audit_wheel(item) for item in wheels]
        sdist_results = [audit_sdist(item) for item in sdists]
        report.artifacts.extend(wheel_results)
        report.artifacts.extend(sdist_results)
        for wheel_result in wheel_results:
            for sdist_result in sdist_results:
                if wheel_result.distribution and sdist_result.distribution and wheel_result.distribution.lower().replace("_", "-") != sdist_result.distribution.lower().replace("_", "-"):
                    report.findings.append(_finding("PD120", "Wheel and source distribution names disagree.",
                                                    "Build both artifacts from the same project metadata.",
                                                    f"wheel={wheel_result.distribution}; sdist={sdist_result.distribution}"))
                if wheel_result.version and sdist_result.version and wheel_result.version != sdist_result.version:
                    report.findings.append(_finding("PD121", "Wheel and source distribution versions disagree.",
                                                    "Build both artifacts from the same versioned source tree.",
                                                    f"wheel={wheel_result.version}; sdist={sdist_result.version}"))

        smoke_root = temporary_root / "smoke"
        smoke_root.mkdir(parents=True, exist_ok=True)
        for idx, wheel_path in enumerate(wheels):
            audit = wheel_results[idx]
            target_imports = configured_imports or _wheel_files(audit)
            _test_installed_wheel(report, wheel_path, audit, target_imports, timeout=timeout,
                                  install_deps=install_deps, stage=f"wheel-{idx}", temporary_root=smoke_root)

        for idx, sdist_path in enumerate(sdists):
            from_sdist_dir = temporary_root / f"rebuilt-from-sdist-{idx}"
            from_sdist_dir.mkdir()
            sdist_project_dir = temporary_root / f"sdist-source-{idx}"
            # Do not add a second generic failure when the static audit already explains
            # why an artifact is unsafe or malformed.
            if sdist_results[idx].has_errors:
                continue
            try:
                unpacked_project = extract_sdist_safely(sdist_path, sdist_project_dir, sdist_results[idx])
            except (ArchiveAuditError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
                report.findings.append(_finding("PD125", "Source distribution could not be safely extracted for rebuild.",
                                                "Resolve archive audit findings and ensure the sdist contains one valid project root.",
                                                str(exc)[:500]))
                continue
            sdist_build_args = _build_argv(frontend, unpacked_project, from_sdist_dir,
                                           build_isolation=build_isolation, wheel_only=True)
            ok = _run_checked(report, sdist_build_args, cwd=unpacked_project, timeout=timeout,
                              code="PD109", step_name=f"wheel rebuild from {sdist_path.name}")
            rebuilt_wheels = sorted(p for p in from_sdist_dir.iterdir() if p.is_file() and p.name.endswith(".whl"))
            if ok and len(rebuilt_wheels) == 1:
                rebuilt = audit_wheel(rebuilt_wheels[0])
                report.artifacts.append(rebuilt)
                origin_sdist = sdist_results[idx]
                if origin_sdist.distribution and rebuilt.distribution and origin_sdist.distribution.lower().replace("_", "-") != rebuilt.distribution.lower().replace("_", "-"):
                    report.findings.append(_finding("PD122", "Wheel rebuilt from the source distribution has a different distribution name.",
                                                    "Investigate whether the sdist metadata and wheel build backend are consistent.",
                                                    f"sdist={origin_sdist.distribution}; wheel={rebuilt.distribution}"))
                if origin_sdist.version and rebuilt.version and origin_sdist.version != rebuilt.version:
                    report.findings.append(_finding("PD123", "Wheel rebuilt from the source distribution has a different version.",
                                                    "Build the sdist and its wheel from a consistent versioned source tree.",
                                                    f"sdist={origin_sdist.version}; wheel={rebuilt.version}"))
                _test_installed_wheel(report, rebuilt_wheels[0], rebuilt, configured_imports or rebuilt.imports,
                                      timeout=timeout, install_deps=install_deps,
                                      stage=f"sdist-{idx}", temporary_root=smoke_root)
            elif ok:
                report.findings.append(_finding("PD124", "Rebuilding the source distribution did not produce exactly one wheel.",
                                                "Inspect the source distribution and build backend output.",
                                                f"wheels={len(rebuilt_wheels)}"))
        # Replace ephemeral absolute paths with stable names before the temp directory is removed.
        if owns_temp:
            _report_path(report, temporary_root, False)
        else:
            # The main artifacts are retained, but intermediate rebuilds and venvs are temporary.
            for finding in report.findings:
                if finding.path and str(temporary_root) in finding.path:
                    finding.path = finding.path.replace(str(temporary_root), "<temporary verification workspace>")
            for artifact in report.artifacts:
                if str(temporary_root) in artifact.path:
                    artifact.path = artifact.path.replace(str(temporary_root), "<temporary verification workspace>")
                for finding in artifact.findings:
                    if finding.path and str(temporary_root) in finding.path:
                        finding.path = finding.path.replace(str(temporary_root), "<temporary verification workspace>")
        report.status = "passed" if report.error_count == 0 else "failed"
        return report
    finally:
        if temp_context is not None:
            temp_context.cleanup()
        elif owns_temp is False:
            shutil.rmtree(temporary_root, ignore_errors=True)
            # Replace retained output path with the retained artifact directory path for the primary artifacts.
            for artifact in report.artifacts:
                if artifact.path.startswith("<temporary verification workspace>"):
                    continue
                candidate = keep_artifacts / Path(artifact.path).name if keep_artifacts else None
                if candidate and candidate.exists():
                    artifact.path = str(candidate)
        report.duration_seconds = time.monotonic() - started
        report.status = "passed" if report.error_count == 0 else "failed"
