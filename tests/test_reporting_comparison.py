from __future__ import annotations

import json
from pathlib import Path

import pytest

from pydistpilot.cli import main
from pydistpilot.comparison import ReportFormatError, compare_reports
from pydistpilot.reporting import SARIF_VERSION, to_sarif


def _report(*, status: str = "passed", findings: list[dict] | None = None, smoke: list[dict] | None = None) -> dict:
    return {
        "schema_version": 1,
        "tool": "pydistpilot",
        "tool_version": "0.2.0",
        "project": "/workspace/project",
        "status": status,
        "findings": findings or [],
        "artifacts": [],
        "smoke_checks": smoke or [],
    }


def _finding(code: str, severity: str, message: str, path: str = "src/pkg.py") -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommendation": "Fix the underlying issue.",
        "path": path,
    }


def test_sarif_uses_stable_rules_and_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    report = _report(findings=[_finding("PD201", "error", "Import failed", str(root / "src/pkg.py"))])

    sarif = to_sarif(report, project_root=root)

    assert sarif["version"] == SARIF_VERSION == "2.1.0"
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "PyDistPilot"
    assert run["tool"]["driver"]["rules"][0]["id"] == "PD201"
    assert run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "src/pkg.py"
    assert run["results"][0]["level"] == "error"


def test_sarif_does_not_leak_external_absolute_path(tmp_path: Path) -> None:
    report = _report(findings=[_finding("PD202", "warning", "Metadata warning", "/home/private-user/work/pkg/file.py")])

    sarif = to_sarif(report, project_root=tmp_path)

    uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "file.py"
    assert "private-user" not in json.dumps(sarif)


def test_sarif_preserves_hidden_file_path() -> None:
    report = _report(findings=[_finding("PD203", "info", "Workflow metadata", ".github/workflows/ci.yml")])

    sarif = to_sarif(report)

    uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == ".github/workflows/ci.yml"
    assert sarif["runs"][0]["results"][0]["level"] == "note"


def test_sarif_maps_failed_smoke_checks_to_results() -> None:
    report = _report(smoke=[{"artifact": "pkg.whl", "check": "import", "target": "pkg", "status": "failed", "message": "exit=1"}])

    sarif = to_sarif(report)

    assert sarif["runs"][0]["results"][0]["ruleId"] == "PDSMOKE001"
    assert sarif["runs"][0]["results"][0]["level"] == "error"


def test_compare_detects_new_issue_and_resolved_issue() -> None:
    old = _report(findings=[_finding("PD100", "error", "Build failed")], status="failed")
    new = _report(findings=[_finding("PD201", "warning", "Missing package data")])

    result = compare_reports(old, new)

    assert result["status"] == "failed"
    assert result["summary"]["new_issues"] == 1
    assert result["summary"]["blocking_new_issues"] == 1
    assert result["resolved_issues"][0]["code"] == "PD100"


def test_compare_ignores_artifact_path_and_evidence_changes() -> None:
    old_finding = _finding("PD101", "warning", "Wheel warning", "/tmp/build-1/pkg.whl")
    old_finding["evidence"] = "old temp location"
    new_finding = _finding("PD101", "warning", "Wheel warning", "/tmp/build-2/pkg.whl")
    new_finding["evidence"] = "new temp location"

    result = compare_reports(_report(findings=[old_finding]), _report(findings=[new_finding]))

    assert result["status"] == "passed"
    assert result["summary"]["new_issues"] == 0
    assert result["summary"]["resolved_issues"] == 0


def test_compare_counts_duplicates_as_regressions() -> None:
    warning = _finding("PD109", "warning", "No import roots found")
    old = _report(findings=[warning])
    new = _report(findings=[warning, warning])

    result = compare_reports(old, new)

    assert result["summary"]["new_issues"] == 1
    assert result["new_issues"][0]["count"] == 1


def test_compare_new_info_is_non_blocking_but_reported() -> None:
    result = compare_reports(_report(), _report(findings=[_finding("PDINFO", "info", "FYI")]))

    assert result["status"] == "passed"
    assert result["summary"]["new_issues"] == 1
    assert result["summary"]["blocking_new_issues"] == 0


def test_compare_can_fail_on_existing_candidate_failures() -> None:
    old = _report(status="failed", findings=[_finding("PD100", "error", "Build failed")])
    new = _report(status="failed", findings=[_finding("PD100", "error", "Build failed")])

    assert compare_reports(old, new)["status"] == "passed"
    assert compare_reports(old, new, fail_on_current_failure=True)["status"] == "failed"


@pytest.mark.parametrize("bad", [None, [], {"schema_version": 2, "status": "passed"}, {"schema_version": 1}])
def test_compare_rejects_malformed_reports(bad: object) -> None:
    with pytest.raises(ReportFormatError):
        compare_reports(bad, _report())


def test_inspect_cli_emits_sarif(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad_artifact = tmp_path / "bad.whl"
    bad_artifact.write_bytes(b"not a wheel")
    sarif_path = tmp_path / "inspection.sarif"

    code = main(["inspect", str(bad_artifact), "--sarif", str(sarif_path), "--quiet"])

    assert code == 1
    sarif = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"]
    assert "FAIL" not in capsys.readouterr().err


def test_compare_cli_emits_json_and_sarif(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    result_json = tmp_path / "comparison.json"
    result_sarif = tmp_path / "comparison.sarif"
    baseline.write_text(json.dumps(_report()), encoding="utf-8")
    candidate.write_text(json.dumps(_report(findings=[_finding("PD999", "error", "New issue")])), encoding="utf-8")

    code = main(["compare", str(baseline), str(candidate), "--json", str(result_json), "--sarif", str(result_sarif), "--quiet"])

    assert code == 1
    assert json.loads(result_json.read_text(encoding="utf-8"))["new_issues"][0]["code"] == "PD999"
    assert json.loads(result_sarif.read_text(encoding="utf-8"))["runs"][0]["results"][0]["ruleId"] == "PD999"


def test_cli_rejects_json_and_sarif_same_output_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps(_report()), encoding="utf-8")
    candidate.write_text(json.dumps(_report()), encoding="utf-8")
    same = tmp_path / "same.json"

    code = main(["compare", str(baseline), str(candidate), "--json", str(same), "--sarif", str(same), "--quiet"])

    assert code == 2
    assert "different file paths" in capsys.readouterr().err
    assert not same.exists()


def test_compare_rejects_unhashable_status_and_malformed_nested_findings() -> None:
    malformed_status = _report()
    malformed_status["status"] = ["passed"]
    with pytest.raises(ReportFormatError, match="status"):
        compare_reports(malformed_status, _report())

    malformed_schema = _report()
    malformed_schema["schema_version"] = True
    with pytest.raises(ReportFormatError, match="schema_version"):
        compare_reports(malformed_schema, _report())

    malformed_nested = _report()
    malformed_nested["artifacts"] = [{"findings": ["not-an-object"]}]
    with pytest.raises(ReportFormatError, match=r"artifacts\[0\]\.findings"):
        compare_reports(malformed_nested, _report())


def test_compare_report_loader_rejects_oversized_input(tmp_path: Path) -> None:
    from pydistpilot.comparison import MAX_REPORT_BYTES
    from pydistpilot.cli import _load_json_report

    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_REPORT_BYTES + 1))
    with pytest.raises(ValueError, match="16 MiB input limit"):
        _load_json_report(path)


def test_compare_cli_invalid_json_is_actionable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text("{broken", encoding="utf-8")
    candidate.write_text(json.dumps(_report()), encoding="utf-8")

    code = main(["compare", str(baseline), str(candidate), "--quiet"])

    captured = capsys.readouterr()
    assert code == 2
    assert "could not read valid UTF-8 JSON" in captured.err
    assert "Traceback" not in captured.err


def test_compare_rejects_comparison_results_as_baselines() -> None:
    comparison_result = compare_reports(_report(), _report(findings=[_finding("PD900", "warning", "New issue")]))
    with pytest.raises(ReportFormatError, match="comparison result"):
        compare_reports(comparison_result, _report())


def test_compare_rejects_report_from_another_tool() -> None:
    foreign = _report()
    foreign["tool"] = "some-other-tool"
    with pytest.raises(ReportFormatError, match="PyDistPilot report"):
        compare_reports(foreign, _report())


def test_sarif_reduces_internal_path_traversal_to_basename() -> None:
    report = _report(findings=[_finding("PD204", "warning", "Suspicious path", "src/../../private.txt")])

    sarif = to_sarif(report)

    uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "private.txt"


def test_inspect_refuses_to_overwrite_an_artifact_with_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact = tmp_path / "broken.whl"
    original = b"not a real wheel"
    artifact.write_bytes(original)

    code = main(["inspect", str(artifact), "--json", str(artifact), "--quiet"])

    assert code == 2
    assert artifact.read_bytes() == original
    assert "must not overwrite an input file" in capsys.readouterr().err


def test_compare_refuses_to_overwrite_a_baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline_content = json.dumps(_report())
    baseline.write_text(baseline_content, encoding="utf-8")
    candidate.write_text(json.dumps(_report()), encoding="utf-8")

    code = main(["compare", str(baseline), str(candidate), "--json", str(baseline), "--quiet"])

    assert code == 2
    assert baseline.read_text(encoding="utf-8") == baseline_content
    assert "must not overwrite an input file" in capsys.readouterr().err
