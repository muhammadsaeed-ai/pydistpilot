"""Interoperable report exports for CI and code-scanning workflows."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def _finding_items(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect report-level and artifact-level findings without mutating the input."""
    findings: list[dict[str, Any]] = []
    raw_findings = report.get("findings", [])
    if isinstance(raw_findings, list):
        findings.extend(item for item in raw_findings if isinstance(item, dict))
    artifacts = report.get("artifacts", [])
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            nested = artifact.get("findings", [])
            if isinstance(nested, list):
                findings.extend(item for item in nested if isinstance(item, dict))
    # Failed smoke checks are represented independently as results too, so a report
    # remains useful even if a future version emits a failed check without a finding.
    smoke_checks = report.get("smoke_checks", [])
    if isinstance(smoke_checks, list):
        for check in smoke_checks:
            if isinstance(check, dict) and check.get("status") == "failed":
                findings.append(
                    {
                        "code": "PDSMOKE001",
                        "severity": "error",
                        "message": f"Smoke check failed: {check.get('check', 'unknown')} — {check.get('target', 'unknown')}",
                        "recommendation": check.get("message") or "Review the smoke-check output and repair the installed-artifact behavior.",
                        "path": check.get("artifact"),
                    }
                )
    # A compact comparator report exposes the newly introduced items as `new_issues`.
    issues = report.get("new_issues", [])
    if isinstance(issues, list):
        findings.extend(item for item in issues if isinstance(item, dict))
    return findings


def _safe_uri(raw_path: object, project_root: Path | None) -> str | None:
    """Return a repository-relative URI when possible; never expose outside paths."""
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    raw = raw_path.strip()
    # Temporary-workspace placeholders are not valid paths; retain only their basename.
    if raw.startswith("<"):
        raw = raw.rsplit("/", 1)[-1].rstrip(">")
    candidate = Path(raw)
    uri: str
    windows_absolute = bool(re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\\\"))
    if windows_absolute and os_name_is_posix():
        # Reports can be moved across operating systems; don't leak a Windows
        # user directory when inspected on POSIX.
        uri = PureWindowsPath(raw).name
    elif candidate.is_absolute():
        if project_root is not None:
            try:
                resolved_root = project_root.resolve()
                resolved_path = candidate.resolve()
                relative = resolved_path.relative_to(resolved_root)
                uri = relative.as_posix()
            except (OSError, ValueError, RuntimeError):
                uri = candidate.name
        else:
            uri = candidate.name
    else:
        uri = candidate.as_posix()
    uri = uri.replace("\\", "/")
    while uri.startswith("./"):
        uri = uri[2:]
    uri_parts = PurePosixPath(uri).parts
    if (
        not uri
        or uri == "."
        or uri == ".."
        or any(part == ".." for part in uri_parts)
        or "://" in uri
    ):
        uri = PurePosixPath(uri).name
    if not uri:
        return None
    return quote(uri, safe="/.-_~")


def os_name_is_posix() -> bool:
    """Whether the current pathlib implementation is parsing POSIX paths."""
    return Path("/").anchor == "/"


def to_sarif(report: dict[str, Any], *, project_root: Path | None = None) -> dict[str, Any]:
    """Convert a PyDistPilot report to SARIF 2.1.0 with stable rule IDs.

    SARIF includes diagnostic messages and recommendations, while paths are made
    relative when contained by `project_root` and otherwise reduced to basenames
    to avoid leaking local usernames or unrelated filesystem structure.
    """
    findings = _finding_items(report)
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    valid_levels = {"error": "error", "warning": "warning", "note": "note", "info": "note"}

    for finding in findings:
        code_value = finding.get("code", "PDUNKNOWN")
        rule_id = str(code_value) if isinstance(code_value, (str, int)) else "PDUNKNOWN"
        severity = str(finding.get("severity", "warning")).lower()
        level = valid_levels.get(severity, "warning")
        message = str(finding.get("message") or "PyDistPilot reported a finding.")
        recommendation = str(finding.get("recommendation") or "Review the report and correct the underlying issue.")
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "shortDescription": {"text": message[:180]},
                "fullDescription": {"text": recommendation[:1000]},
                "defaultConfiguration": {"level": level},
                "properties": {"tags": ["python-packaging", "release-verification"]},
            }
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": level,
            "message": {"text": message},
            "properties": {"recommendation": recommendation},
            "partialFingerprints": {
                "pydistpilot/v1": hashlib.sha256(f"{rule_id}\0{severity}\0{message}".encode("utf-8")).hexdigest()
            },
        }
        uri = _safe_uri(finding.get("path"), project_root)
        if uri:
            result["locations"] = [{"physicalLocation": {"artifactLocation": {"uri": uri}}}]
        results.append(result)

    result_status = report.get("status", "unknown")
    sarif_run: dict[str, Any] = {
        "tool": {"driver": {"name": "PyDistPilot", "semanticVersion": str(report.get("tool_version", "0.2.0")), "rules": list(rules.values())}},
        "results": results,
        "properties": {"pydistpilotStatus": result_status},
    }
    # Deliberately omit local file:// base URIs: they can expose usernames and
    # workspace paths. Each location above is already safe and relative when possible.
    return {"$schema": SARIF_SCHEMA, "version": SARIF_VERSION, "runs": [sarif_run]}


def sarif_result_count(sarif: dict[str, Any]) -> int:
    """Return the total number of SARIF results (handy for CLI summaries/tests)."""
    runs = sarif.get("runs", [])
    if not isinstance(runs, list):
        return 0
    return sum(len(run.get("results", [])) for run in runs if isinstance(run, dict) and isinstance(run.get("results", []), list))
