from __future__ import annotations

import pytest
from pathlib import Path

from pydistpilot.archive import ArchiveAuditError, audit_sdist, audit_wheel, extract_sdist_safely
from pydistpilot.models import Finding
from tests.helpers import make_sdist, make_wheel


def codes(findings: list[Finding]) -> set[str]:
    return {finding.code for finding in findings}


def test_valid_wheel_has_metadata_imports_and_cli(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "sample_pkg-1.2.0-py3-none-any.whl")
    result = audit_wheel(wheel)
    assert not result.has_errors
    assert result.distribution == "Sample-Pkg"
    assert result.version == "1.2.0"
    assert "sample_pkg" in result.imports
    assert result.console_scripts == ["sample-cli"]
    assert len(result.sha256) == 64


def test_wheel_record_mismatch_is_reported(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "sample_pkg-1.2.0-py3-none-any.whl", corrupt_payload=True)
    result = audit_wheel(wheel)
    assert result.has_errors
    assert "PD038" in codes(result.findings)


def test_wheel_unsafe_archive_path_is_reported(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "sample_pkg-1.2.0-py3-none-any.whl", add_unsafe_path=True)
    result = audit_wheel(wheel)
    assert "PD010" in codes(result.findings)


def test_wheel_malformed_repeated_separator_is_reported(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "sample_pkg-1.2.0-py3-none-any.whl", add_malformed_path=True)
    result = audit_wheel(wheel)
    assert "PD010" in codes(result.findings)


def test_invalid_zip_is_reported(tmp_path: Path) -> None:
    broken = tmp_path / "broken.whl"
    broken.write_bytes(b"not a zip archive")
    result = audit_wheel(broken)
    assert result.has_errors
    assert "PD002" in codes(result.findings)


def test_nonexistent_wheel_is_reported(tmp_path: Path) -> None:
    result = audit_wheel(tmp_path / "missing.whl")
    assert result.has_errors
    assert "PD001" in codes(result.findings)


def test_valid_sdist_metadata_and_paths(tmp_path: Path) -> None:
    sdist = make_sdist(tmp_path / "sample_pkg-1.2.0.tar.gz")
    result = audit_sdist(sdist)
    assert not result.has_errors
    assert result.distribution == "Sample-Pkg"
    assert result.version == "1.2.0"


def test_sdist_path_traversal_is_reported(tmp_path: Path) -> None:
    sdist = make_sdist(tmp_path / "sample_pkg-1.2.0.tar.gz", add_unsafe_path=True)
    result = audit_sdist(sdist)
    assert "PD010" in codes(result.findings)


def test_sdist_malformed_repeated_separator_is_reported(tmp_path: Path) -> None:
    sdist = make_sdist(tmp_path / "sample_pkg-1.2.0.tar.gz", add_malformed_path=True)
    result = audit_sdist(sdist)
    assert "PD010" in codes(result.findings)


def test_sdist_wrong_extension_is_reported(tmp_path: Path) -> None:
    artifact = tmp_path / "package.7z"
    artifact.write_bytes(b"no")
    result = audit_sdist(artifact)
    assert "PD045" in codes(result.findings)


def test_wheel_crc_corruption_is_reported(tmp_path: Path) -> None:
    wheel = make_wheel(tmp_path / "sample_pkg-1.2.0-py3-none-any.whl")
    raw = bytearray(wheel.read_bytes())
    # Flip a byte in the compressed payload; a corrupt ZIP should be reported cleanly.
    raw[len(raw) // 2] ^= 0xFF
    wheel.write_bytes(raw)
    result = audit_wheel(wheel)
    assert result.has_errors


def test_safe_sdist_extraction_returns_project_root(tmp_path: Path) -> None:
    sdist = make_sdist(tmp_path / "sample_pkg-1.2.0.tar.gz")
    audit = audit_sdist(sdist)
    root = extract_sdist_safely(sdist, tmp_path / "unpacked", audit)
    assert root.name == "sample_pkg-1.2.0"
    assert (root / "pyproject.toml").is_file()
    assert (root / "src" / "sample_pkg" / "__init__.py").is_file()


def test_unsafe_sdist_is_never_extracted(tmp_path: Path) -> None:
    sdist = make_sdist(tmp_path / "sample_pkg-1.2.0.tar.gz", add_unsafe_path=True)
    audit = audit_sdist(sdist)
    assert audit.has_errors
    with pytest.raises(ArchiveAuditError):
        extract_sdist_safely(sdist, tmp_path / "unpacked", audit)
    assert not (tmp_path / "outside.txt").exists()
