from __future__ import annotations

import base64
import csv
import hashlib
import io
import tarfile
import zipfile
from pathlib import Path


def make_wheel(path: Path, *, corrupt_payload: bool = False, add_unsafe_path: bool = False, add_malformed_path: bool = False) -> Path:
    name = "sample_pkg"
    version = "1.2.0"
    dist_info = f"{name}-{version}.dist-info"
    files: dict[str, bytes] = {
        "sample_pkg/__init__.py": b'"""Fixture package."""\n__version__ = "1.2.0"\n',
        "sample_pkg/cli.py": b"def main():\n    print('usage: sample-cli --help')\n    return 0\n",
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.1\nName: Sample-Pkg\nVersion: 1.2.0\nSummary: fixture\n\n"
        ).encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: test-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n\n",
        f"{dist_info}/entry_points.txt": b"[console_scripts]\nsample-cli = sample_pkg.cli:main\n",
    }
    if add_unsafe_path:
        files["../outside.py"] = b"# unsafe\n"
    if add_malformed_path:
        files["bad//"] = b""
    record_rows: list[list[str]] = []
    for member, payload in files.items():
        content = payload[:-1] + b"x" if corrupt_payload and member == "sample_pkg/cli.py" else payload
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        record_rows.append([member, f"sha256={digest}", str(len(content))])
    record_rows.append([f"{dist_info}/RECORD", "", ""])
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerows(record_rows)
    files[f"{dist_info}/RECORD"] = text.getvalue().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member, payload in files.items():
            archive.writestr(member, payload)
    return path


def make_sdist(path: Path, *, add_unsafe_path: bool = False, add_malformed_path: bool = False) -> Path:
    root = "sample_pkg-1.2.0"
    files: dict[str, bytes] = {
        f"{root}/PKG-INFO": b"Metadata-Version: 2.1\nName: Sample-Pkg\nVersion: 1.2.0\n\n",
        f"{root}/pyproject.toml": b"[build-system]\nrequires = ['setuptools']\nbuild-backend = 'setuptools.build_meta'\n",
        f"{root}/src/sample_pkg/__init__.py": b"__version__ = '1.2.0'\n",
    }
    if add_unsafe_path:
        files["../outside.txt"] = b"unsafe"
    if add_malformed_path:
        files[f"{root}/bad//"] = b"malformed"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    return path
