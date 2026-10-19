"""Regression comparison for previously emitted PyDistPilot JSON reports."""

from __future__ import annotations

from collections import Counter
from typing import Any

REPORT_SCHEMA_VERSION = 1
MAX_REPORT_BYTES = 16 * 1024 * 1024


class ReportFormatError(ValueError):
    """Raised when a report is not compatible with this comparator."""


def _validate_report(report: object, label: str) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ReportFormatError(f"{label} must be a JSON object")
    schema_version = report.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != REPORT_SCHEMA_VERSION:
        raise ReportFormatError(f"{label} has unsupported schema_version {schema_version!r}; expected {REPORT_SCHEMA_VERSION}")
    if report.get("tool") != "pydistpilot":
        raise ReportFormatError(f"{label} must be a PyDistPilot report")
    if report.get("command") == "compare":
        raise ReportFormatError(f"{label} is a comparison result, not a verification or inspection report")
    status = report.get("status")
    if not isinstance(status, str) or status not in {"passed", "failed"}:
        raise ReportFormatError(f"{label} must have status 'passed' or 'failed'")
    for required in ("findings", "artifacts"):
        if required not in report:
            raise ReportFormatError(f"{label} is missing required field {required!r}")
    for field in ("findings", "artifacts", "smoke_checks"):
        value = report.get(field, [])
        if not isinstance(value, list):
            raise ReportFormatError(f"{label} field {field!r} must be an array")
        if field in {"findings", "smoke_checks"} and any(not isinstance(item, dict) for item in value):
            raise ReportFormatError(f"{label} field {field!r} must contain JSON objects")
        if field == "artifacts":
            for index, artifact in enumerate(value):
                if not isinstance(artifact, dict):
                    raise ReportFormatError(f"{label} artifacts[{index}] must be a JSON object")
                nested = artifact.get("findings", [])
                if not isinstance(nested, list) or any(not isinstance(item, dict) for item in nested):
                    raise ReportFormatError(f"{label} artifacts[{index}].findings must be an array of JSON objects")
    return report


def _issues(report: dict[str, Any]) -> Counter[tuple[str, str, str]]:
    issues: Counter[tuple[str, str, str]] = Counter()

    def consume(finding: object) -> None:
        if not isinstance(finding, dict):
            return
        code, severity, message = finding.get("code"), finding.get("severity"), finding.get("message")
        if not isinstance(code, (str, int)) or isinstance(code, bool):
            return
        if not isinstance(severity, str) or severity not in {"error", "warning", "info", "note"}:
            return
        if not isinstance(message, str):
            return
        issues[(str(code), severity, message)] += 1

    for finding in report.get("findings", []):
        consume(finding)
    for artifact in report.get("artifacts", []):
        if isinstance(artifact, dict):
            for finding in artifact.get("findings", []):
                consume(finding)
    for check in report.get("smoke_checks", []):
        if isinstance(check, dict) and check.get("status") == "failed":
            check_name, target = str(check.get("check", "unknown")), str(check.get("target", "unknown"))
            issues[("PDSMOKE001", "error", f"Smoke check failed: {check_name} — {target}")] += 1
    has_blocking_issue = any(severity in {"error", "warning"} for _, severity, _ in issues)
    if report.get("status") == "failed" and not has_blocking_issue:
        issues[("PDREPORT001", "error", "Report status is failed but has no structured blocking finding.")] += 1
    return issues


def _expanded(counter: Counter[tuple[str, str, str]]) -> list[dict[str, Any]]:
    return [{"code": k[0], "severity": k[1], "message": k[2], "count": counter[k]} for k in sorted(counter)]


def compare_reports(baseline: object, candidate: object, *, fail_on_current_failure: bool = False) -> dict[str, Any]:
    """Compare schema-v1 reports; optionally require the candidate to be failure-free."""
    old, new = _validate_report(baseline, "baseline report"), _validate_report(candidate, "candidate report")
    old_issues, new_issues = _issues(old), _issues(new)
    added, removed = new_issues - old_issues, old_issues - new_issues
    new_issue_count = sum(added.values())
    blocking_new_issues = sum(count for key, count in added.items() if key[1] in {"error", "warning"})
    status = "failed" if blocking_new_issues or (fail_on_current_failure and new.get("status") == "failed") else "passed"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "tool": "pydistpilot",
        "command": "compare",
        "status": status,
        "baseline_status": old.get("status"),
        "candidate_status": new.get("status"),
        "summary": {
            "new_issues": new_issue_count,
            "blocking_new_issues": blocking_new_issues,
            "resolved_issues": sum(removed.values()),
            "baseline_issues": sum(old_issues.values()),
            "candidate_issues": sum(new_issues.values()),
            "fail_on_current_failure": fail_on_current_failure,
        },
        "new_issues": _expanded(added),
        "resolved_issues": _expanded(removed),
    }
