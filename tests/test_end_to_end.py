from __future__ import annotations

import site
import sysconfig
import shutil
from pathlib import Path

import pytest

from pydistpilot.verify import verify_project


def _has_build_frontend() -> bool:
    roots = {Path(sysconfig.get_paths()["purelib"]), *(Path(item) for item in site.getsitepackages())}
    return any((root / "build" / "__main__.py").is_file() for root in roots) or shutil.which("uv") is not None


@pytest.mark.skipif(not _has_build_frontend(), reason="neither PyPA build nor uv is installed")
def test_verify_builds_and_smoke_tests_both_distribution_paths(tmp_path: Path) -> None:
    project = tmp_path / "sample-project"
    (project / "src" / "sampleapp").mkdir(parents=True)
    (project / "src" / "sampleapp" / "__init__.py").write_text("__version__ = '0.4.2'\n", encoding="utf-8")
    (project / "src" / "sampleapp" / "cli.py").write_text(
        "def main():\n    print('sampleapp CLI help')\n    return 0\n", encoding="utf-8"
    )
    (project / "README.md").write_text("# sampleapp\n", encoding="utf-8")
    (project / "pyproject.toml").write_text(
        """[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "sampleapp"
version = "0.4.2"
readme = "README.md"
requires-python = ">=3.10"

[project.scripts]
sampleapp = "sampleapp.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pydistpilot]
imports = ["sampleapp"]
""",
        encoding="utf-8",
    )
    report = verify_project(project, timeout=60, keep_artifacts=tmp_path / "release-artifacts")
    assert report.status == "passed", report.to_dict()
    assert sum(artifact.kind == "wheel" for artifact in report.artifacts) >= 2
    assert sum(artifact.kind == "sdist" for artifact in report.artifacts) == 1
    assert any(check.check == "import" and check.status == "passed" for check in report.smoke_checks)
    assert any(check.check == "console-script" and check.status == "passed" for check in report.smoke_checks)
