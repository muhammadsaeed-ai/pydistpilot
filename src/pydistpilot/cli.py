"""Command-line interface for PyDistPilot."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydistpilot import __version__
from pydistpilot.archive import audit_artifact
from pydistpilot.comparison import MAX_REPORT_BYTES, compare_reports
from pydistpilot.models import ArtifactResult, Finding, VerificationReport
from pydistpilot.reporting import to_sarif
from pydistpilot.verify import verify_project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pydistpilot",
        description="Build and verify the Python distributions users actually install.",
        epilog=(
            "Safety: 'verify' executes the project's build backend and installed import/CLI code. "
            "Only use it on source you trust. No network access is used by default."
        ),
    )
    parser.add_argument("--version", action="version", version=f"pydistpilot {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify = subparsers.add_parser("verify", help="build and smoke-test wheel and source distribution")
    verify.add_argument("project", nargs="?", type=Path, default=Path.cwd(), help="project root (default: current directory)")
    verify.add_argument("--import", dest="imports", action="append", default=None, metavar="MODULE",
                        help="additional/override import smoke target; may be repeated")
    verify.add_argument("--timeout", type=float, default=90.0, help="timeout per build, install, import, or CLI check (default: 90 seconds; max: 3600)")
    verify.add_argument("--install-deps", action="store_true",
                        help="allow pip to resolve package dependencies from configured indexes (network/package execution may occur)")
    verify.add_argument("--build-isolation", action="store_true",
                        help="let 'python -m build' create isolated build environments (may download build requirements)")
    verify.add_argument("--keep-artifacts", type=Path, metavar="DIR",
                        help="retain original wheel and sdist in a new/empty directory outside the source project")
    verify.add_argument("--report", type=Path, metavar="JSON",
                        help="write the full JSON report to this path (overwrites that report file atomically)")
    verify.add_argument("--sarif", type=Path, metavar="SARIF",
                        help="write findings in SARIF 2.1.0 format for CI/code-scanning integrations")
    verify.add_argument("--quiet", action="store_true", help="print only the final status and error/warning counts")

    inspect = subparsers.add_parser("inspect", help="statically inspect one or more built artifacts without installing or executing them")
    inspect.add_argument("artifacts", nargs="+", type=Path, help="wheel or source distribution file(s)")
    inspect.add_argument("--json", dest="json_path", type=Path, metavar="JSON",
                         help="write a machine-readable inspection report to this path")
    inspect.add_argument("--sarif", type=Path, metavar="SARIF",
                         help="write findings in SARIF 2.1.0 format for CI/code-scanning integrations")
    inspect.add_argument("--quiet", action="store_true", help="print only the final status and finding counts")

    compare = subparsers.add_parser("compare", help="compare two JSON reports and detect new findings")
    compare.add_argument("baseline", type=Path, help="accepted/baseline JSON report from verify or inspect")
    compare.add_argument("candidate", type=Path, help="new JSON report to compare with the baseline")
    compare.add_argument("--json", dest="json_path", type=Path, metavar="JSON",
                         help="write the comparison report to this path")
    compare.add_argument("--sarif", type=Path, metavar="SARIF",
                         help="write newly introduced findings in SARIF 2.1.0 format")
    compare.add_argument("--fail-on-current-failure", action="store_true",
                         help="fail when the candidate report is failed, even if its findings already exist in the baseline")
    compare.add_argument("--quiet", action="store_true", help="print only the final regression summary")
    return parser


def _finding_line(finding: Finding) -> str:
    head = f"[{finding.severity.upper():7}] {finding.code}: {finding.message}"
    if finding.path:
        head += f" ({finding.path})"
    lines = [head, f"          Action: {finding.recommendation}"]
    if finding.evidence:
        evidence = finding.evidence.strip().replace("\n", " | ")
        if evidence:
            lines.append(f"          Evidence: {evidence[:500]}")
    return "\n".join(lines)


def _print_report(report: VerificationReport, quiet: bool = False) -> None:
    data = report.to_dict()
    summary = data["summary"]
    if quiet:
        print(f"PyDistPilot: {report.status.upper()} — {summary['errors']} error(s), {summary['warnings']} warning(s)")
        return
    print(f"\nPyDistPilot {report.tool_version} · {report.project}")
    print("=" * 72)
    print(f"Status: {report.status.upper()} | {summary['artifacts']} artifact(s) | "
          f"{summary['smoke_checks']} smoke check(s) | {summary['errors']} error(s) | "
          f"{summary['warnings']} warning(s)")
    if report.artifacts:
        print("\nArtifacts")
        for artifact in report.artifacts:
            state = "FAIL" if artifact.has_errors else "OK"
            print(f"  [{state:4}] {artifact.kind}: {artifact.path} ({artifact.size_bytes:,} bytes)")
            if artifact.distribution or artifact.version:
                print(f"         {artifact.distribution or '?'} {artifact.version or '?'}")
            for finding in artifact.findings:
                print("    " + _finding_line(finding).replace("\n", "\n    "))
    if report.smoke_checks:
        print("\nInstalled-artifact smoke checks")
        for check in report.smoke_checks:
            print(f"  [{check.status.upper():6}] {check.check}: {check.target} "
                  f"({check.duration_seconds:.2f}s) — {check.message}")
    if report.findings:
        print("\nFindings")
        for finding in report.findings:
            print(_finding_line(finding))
    print(f"\nFinished in {report.duration_seconds:.2f}s")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically using a unique temporary file beside the target."""
    requested = path.expanduser()
    if requested.is_symlink():
        raise OSError(f"report path must not be a symbolic link: {requested}")
    parent = requested.parent.resolve()
    target = parent / requested.name
    if target.exists() and target.is_dir():
        raise OSError(f"report path is a directory: {target}")
    parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _inspect(artifacts: list[Path]) -> tuple[list[ArtifactResult], list[Finding]]:
    results: list[ArtifactResult] = []
    top_level: list[Finding] = []
    for artifact in artifacts:
        result = audit_artifact(artifact)
        results.append(result)
        if not artifact.is_file():
            top_level.append(Finding("PD003", "error", "Artifact path does not point to a file.",
                                     "Pass an existing .whl or supported source-distribution file.", str(artifact)))
    return results, top_level


def _validate_distinct_outputs(*paths: Path | None) -> None:
    resolved = [path.expanduser().resolve() for path in paths if path is not None]
    if len(resolved) != len(set(resolved)):
        raise OSError("JSON and SARIF outputs must use different file paths")


def _validate_outputs_do_not_replace_inputs(
    outputs: tuple[Path | None, ...], inputs: tuple[Path, ...]
) -> None:
    resolved_outputs = {path.expanduser().resolve() for path in outputs if path is not None}
    resolved_inputs = {path.expanduser().resolve() for path in inputs}
    collisions = sorted(str(path) for path in resolved_outputs & resolved_inputs)
    if collisions:
        raise OSError("report output must not overwrite an input file: " + ", ".join(collisions))


def _write_sarif(path: Path, report: dict[str, Any], *, project_root: Path | None = None) -> None:
    _write_json(path, to_sarif(report, project_root=project_root))


def _is_owned_report(path: Path, *, output_kind: str, project_root: Path) -> bool:
    """Allow an existing in-project report to be refreshed, but protect source files."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_REPORT_BYTES:
            return False
        with path.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return False
    if not isinstance(existing, dict):
        return False
    if output_kind == "json":
        return (
            existing.get("schema_version") == 1
            and existing.get("tool") == "pydistpilot"
            and existing.get("project") == str(project_root)
            and existing.get("status") in {"passed", "failed"}
            and isinstance(existing.get("summary"), dict)
            and isinstance(existing.get("artifacts"), list)
            and isinstance(existing.get("findings"), list)
        )
    runs = existing.get("runs")
    return (
        existing.get("version") == "2.1.0"
        and isinstance(runs, list)
        and bool(runs)
        and isinstance(runs[0], dict)
        and isinstance(runs[0].get("tool"), dict)
        and isinstance(runs[0]["tool"].get("driver"), dict)
        and runs[0]["tool"]["driver"].get("name") == "PyDistPilot"
    )


def _validate_verify_outputs(
    project: Path, json_output: Path | None, sarif_output: Path | None
) -> None:
    """Reject output paths that would clobber project inputs during verification."""
    _validate_distinct_outputs(json_output, sarif_output)
    root = project.expanduser().resolve()
    for output, output_kind in ((json_output, "json"), (sarif_output, "sarif")):
        if output is None:
            continue
        target = output.expanduser().resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if target == root:
            raise OSError(f"report output must not replace the project directory: {target}")
        if target.exists() and not _is_owned_report(
            target, output_kind=output_kind, project_root=root
        ):
            raise OSError(
                f"report output would overwrite an existing project file: {target}; "
                "choose a new report path or an existing PyDistPilot report"
            )


def _inspect_command(args: argparse.Namespace) -> int:
    try:
        _validate_distinct_outputs(args.json_path, args.sarif)
        _validate_outputs_do_not_replace_inputs((args.json_path, args.sarif), tuple(args.artifacts))
    except OSError as exc:
        print(f"error: invalid inspection output path: {exc}", file=sys.stderr)
        return 2
    results, top_findings = _inspect(args.artifacts)
    has_errors = bool(top_findings) or any(item.has_errors for item in results)
    warnings = sum(f.severity == "warning" for item in results for f in item.findings)
    errors = sum(f.severity == "error" for item in results for f in item.findings) + sum(
        f.severity == "error" for f in top_findings
    )
    report = {
        "schema_version": 1,
        "tool": "pydistpilot",
        "tool_version": __version__,
        "status": "failed" if has_errors else "passed",
        "summary": {"artifacts": len(results), "errors": errors, "warnings": warnings},
        "artifacts": [item.to_dict() for item in results],
        "findings": [f.to_dict() for f in top_findings],
    }
    try:
        if args.json_path:
            _write_json(args.json_path, report)
        if args.sarif:
            _write_sarif(args.sarif, report, project_root=Path.cwd())
    except OSError as exc:
        print(f"error: could not write inspection report: {exc}", file=sys.stderr)
        return 2
    if args.quiet:
        print(f"PyDistPilot inspect: {str(report['status']).upper()} — {errors} error(s), {warnings} warning(s)")
    else:
        print(f"\nPyDistPilot static artifact inspection · {report['status'].upper()}")
        for item in results:
            state = "FAIL" if item.has_errors else "OK"
            print(f"  [{state:4}] {item.kind}: {item.path} ({item.size_bytes:,} bytes)")
            if item.distribution or item.version:
                print(f"         {item.distribution or '?'} {item.version or '?'}")
            for finding in item.findings:
                print(_finding_line(finding).replace("\n", "\n    "))
        for finding in top_findings:
            print(_finding_line(finding))
        if args.json_path:
            print(f"\nJSON report: {args.json_path.resolve()}")
        if args.sarif:
            print(f"SARIF report: {args.sarif.expanduser().resolve()}")
    return 1 if has_errors else 0


def _load_json_report(path: Path) -> dict[str, Any]:
    """Load a local report under a strict size cap before parsing JSON."""
    requested = path.expanduser()
    if not requested.is_file():
        raise ValueError(f"report path must point to a regular file: {requested}")
    try:
        size = requested.stat().st_size
        if size > MAX_REPORT_BYTES:
            raise ValueError(
                f"report exceeds the {MAX_REPORT_BYTES // (1024 * 1024)} MiB input limit: {requested}"
            )
        with requested.open("rb") as handle:
            raw = handle.read(MAX_REPORT_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"could not read report {requested}: {exc}") from exc
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError(
            f"report exceeds the {MAX_REPORT_BYTES // (1024 * 1024)} MiB input limit: {requested}"
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"could not read valid UTF-8 JSON from {requested}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"report must contain a JSON object: {requested}")
    return data


def _compare_command(args: argparse.Namespace) -> int:
    try:
        _validate_distinct_outputs(args.json_path, args.sarif)
        _validate_outputs_do_not_replace_inputs((args.json_path, args.sarif), (args.baseline, args.candidate))
        baseline = _load_json_report(args.baseline)
        candidate = _load_json_report(args.candidate)
        result = compare_reports(baseline, candidate, fail_on_current_failure=args.fail_on_current_failure)
        if args.json_path:
            _write_json(args.json_path, result)
        if args.sarif:
            _write_sarif(args.sarif, result, project_root=Path.cwd())
    except (OSError, ValueError) as exc:
        print(f"error: comparison failed: {exc}", file=sys.stderr)
        return 2

    summary = result["summary"]
    if args.quiet:
        print(f"PyDistPilot compare: {result['status'].upper()} — {summary['new_issues']} new, "
              f"{summary['resolved_issues']} resolved")
    else:
        print("\nPyDistPilot report comparison")
        print("=" * 72)
        print(f"Status: {result['status'].upper()} | {summary['new_issues']} new issue(s) | "
              f"{summary['resolved_issues']} resolved issue(s)")
        print(f"Baseline: {result['baseline_status']} | Candidate: {result['candidate_status']}")
        if result["new_issues"]:
            print("\nNew findings")
            for item in result["new_issues"]:
                print(f"  [{item['severity'].upper():7}] {item['code']}: {item['message']} (x{item['count']})")
        if result["resolved_issues"]:
            print("\nResolved findings")
            for item in result["resolved_issues"]:
                print(f"  [{item['severity'].upper():7}] {item['code']}: {item['message']} (x{item['count']})")
        if args.json_path:
            print(f"\nJSON report: {args.json_path.expanduser().resolve()}")
        if args.sarif:
            print(f"SARIF report: {args.sarif.expanduser().resolve()}")
    return 1 if result["status"] == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "inspect":
        return _inspect_command(args)
    if args.command == "compare":
        return _compare_command(args)
    if args.command == "verify":
        try:
            _validate_verify_outputs(args.project, args.report, args.sarif)
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        report = verify_project(
            args.project,
            import_names=args.imports,
            timeout=args.timeout,
            install_deps=args.install_deps,
            build_isolation=args.build_isolation,
            keep_artifacts=args.keep_artifacts,
        )
        report_data = report.to_dict()
        _print_report(report, args.quiet)
        try:
            if args.report:
                _write_json(args.report, report_data)
                if not args.quiet:
                    print(f"JSON report: {args.report.expanduser().resolve()}")
            if args.sarif:
                _write_sarif(args.sarif, report_data, project_root=args.project.resolve())
                if not args.quiet:
                    print(f"SARIF report: {args.sarif.expanduser().resolve()}")
        except OSError as exc:
            print(f"error: could not write verification report: {exc}", file=sys.stderr)
            return 2
        return 0 if report.status == "passed" else 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
