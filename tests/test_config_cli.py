from __future__ import annotations

import json
from pathlib import Path

import pytest

from pydistpilot.cli import main
from pydistpilot.config import ConfigError, load_config
from pydistpilot.models import VerificationReport


def test_loads_configured_imports(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.pydistpilot]\nimports = ["acme", "acme.cli"]\n', encoding="utf-8")
    assert load_config(tmp_path)["imports"] == ["acme", "acme.cli"]


def test_rejects_invalid_config_import(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.pydistpilot]\nimports = ["not-a-module"]\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_config_missing_is_allowed(tmp_path: Path) -> None:
    assert load_config(tmp_path) == {}


def test_rejects_non_table_tool_section(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('tool = "not-a-table"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match=r"\[tool\] must be a TOML table"):
        load_config(tmp_path)


def test_verify_invalid_project_path_returns_failure(tmp_path: Path) -> None:
    report = VerificationReport(project=str(tmp_path / "missing"))
    assert report.status == "failed"
    assert report.to_dict()["schema_version"] == 1


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "pydistpilot" in capsys.readouterr().out


def test_inspect_writes_json_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    artifact = tmp_path / "sample_pkg-1.2.0-py3-none-any.whl"
    artifact.write_bytes(b"no")
    report_path = tmp_path / "report.json"
    code = main(["inspect", str(artifact), "--json", str(report_path)])
    assert code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["artifacts"][0]["kind"] == "wheel"
    assert "FAIL" in capsys.readouterr().out


def test_inspect_missing_path_is_failure(tmp_path: Path) -> None:
    assert main(["inspect", str(tmp_path / "missing.whl"), "--quiet"]) == 1


def test_json_writer_rejects_symlink_target(tmp_path: Path) -> None:
    from pydistpilot.cli import _write_json

    real_file = tmp_path / "real.json"
    real_file.write_text("keep\n", encoding="utf-8")
    link = tmp_path / "report.json"
    try:
        link.symlink_to(real_file)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable in this environment")
    with pytest.raises(OSError, match="symbolic link"):
        _write_json(link, {"status": "failed"})
    assert real_file.read_text(encoding="utf-8") == "keep\n"


def test_verify_refuses_to_overwrite_project_manifest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text('[project]\nname = "keep-me"\n', encoding="utf-8")
    original = manifest.read_text(encoding="utf-8")
    code = main(["verify", str(tmp_path), "--report", str(manifest), "--quiet"])
    assert code == 2
    assert manifest.read_text(encoding="utf-8") == original
    assert "overwrite an existing project file" in capsys.readouterr().err


def test_verify_allows_refreshing_its_own_report(tmp_path: Path) -> None:
    from pydistpilot.cli import _validate_verify_outputs, _write_json

    project = tmp_path / "project"
    project.mkdir()
    report_path = project / "report.json"
    _write_json(report_path, {
        "schema_version": 1,
        "tool": "pydistpilot",
        "project": str(project.resolve()),
        "status": "passed",
        "summary": {},
        "artifacts": [],
        "findings": [],
    })
    _validate_verify_outputs(project, report_path, None)
