"""Static auditing of wheel and source-distribution archives without extraction."""

from __future__ import annotations

import base64
import configparser
import csv
import hashlib
import io
import re
import tarfile
import zipfile
from collections import Counter
from email.parser import BytesParser
from email.policy import compat32
from pathlib import Path
from typing import BinaryIO, Iterable

from pydistpilot.models import ArtifactResult, Finding

MAX_ARCHIVE_MEMBERS = 100_000
MAX_ARCHIVE_FILE_SIZE = 1024 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 512 * 1024 * 1024
MAX_MEMBER_SIZE = 256 * 1024 * 1024
MAX_METADATA_SIZE = 2 * 1024 * 1024
MAX_RECORD_SIZE = 16 * 1024 * 1024
MAX_ENTRY_POINTS_SIZE = 2 * 1024 * 1024


class ArchiveAuditError(ValueError):
    """Raised when an archive is malformed or exceeds safe inspection limits."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalized_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _safe_member_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        return False
    # Inspect raw components: PurePosixPath normalizes away explicit '.' segments.
    # A single trailing slash marks a directory. Strip at most one so malformed
    # names such as ``folder//`` still fail the empty-component check.
    trimmed = name[:-1] if name.endswith("/") else name
    return bool(trimmed) and all(part not in {"", ".", ".."} for part in trimmed.split("/"))


def _parse_metadata(raw: bytes, artifact_path: Path, findings: list[Finding]) -> tuple[str | None, str | None]:
    if len(raw) > MAX_METADATA_SIZE:
        findings.append(
            Finding(
                "PD021",
                "error",
                "Distribution metadata exceeds the safe inspection size limit.",
                "Rebuild the distribution with reasonably sized metadata.",
                str(artifact_path),
            )
        )
        return None, None
    metadata = BytesParser(policy=compat32).parsebytes(raw)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not name or not version:
        findings.append(
            Finding(
                "PD022",
                "error",
                "Distribution metadata is missing Name or Version.",
                "Ensure the build backend emits valid Core Metadata for the distribution.",
                str(artifact_path),
            )
        )
    return str(name) if name else None, str(version) if version else None


def _archive_size_guard(infos: Iterable[tuple[str, int]], artifact: Path, findings: list[Finding]) -> bool:
    total = 0
    count = 0
    valid = True
    for name, size in infos:
        count += 1
        if not _safe_member_name(name):
            findings.append(
                Finding(
                    "PD010",
                    "error",
                    "Archive contains an unsafe member path.",
                    "Rebuild the artifact so every member uses a relative POSIX path without '..' or backslashes.",
                    str(artifact),
                    name[:300],
                )
            )
            valid = False
        if size < 0 or size > MAX_MEMBER_SIZE:
            findings.append(
                Finding(
                    "PD011",
                    "error",
                    "Archive member exceeds the safe uncompressed-size limit.",
                    "Inspect the distribution contents and remove unexpectedly large entries.",
                    str(artifact),
                    name[:300],
                )
            )
            valid = False
        total += max(0, size)
        if count > MAX_ARCHIVE_MEMBERS:
            findings.append(
                Finding(
                    "PD012",
                    "error",
                    "Archive contains too many members to inspect safely.",
                    "Review generated files and rebuild a reasonably sized distribution.",
                    str(artifact),
                )
            )
            return False
    if total > MAX_TOTAL_UNCOMPRESSED:
        findings.append(
            Finding(
                "PD013",
                "error",
                "Archive's declared uncompressed size exceeds the safe inspection limit.",
                "Review the package contents before verifying this artifact.",
                str(artifact),
            )
        )
        valid = False
    return valid


def _infer_imports(names: Iterable[str]) -> list[str]:
    all_names = list(names)
    roots: set[str] = set()
    package_roots = {
        name.split("/", 1)[0]
        for name in all_names
        if name.endswith("/__init__.py") and ".dist-info/" not in name and ".data/" not in name
    }
    module_roots: set[str] = set()
    for name in all_names:
        if ".dist-info/" in name or ".data/" in name or name.startswith("__pycache__/"):
            continue
        if "/" not in name and name.endswith(".py") and name != "__init__.py":
            module_roots.add(name[:-3])
    package_roots = {root for root in package_roots if root.isidentifier() and not root.startswith("_")}
    module_roots = {root for root in module_roots if root.isidentifier() and not root.startswith("_")}
    # Namespace packages cannot be reliably distinguished from bundled assets without
    # project-specific knowledge, so users can select those explicitly in pyproject.toml.
    return sorted(package_roots | module_roots)


def _read_member_limited(archive: zipfile.ZipFile, member: str, limit: int) -> bytes:
    """Read at most limit + 1 bytes from an archive member."""
    with archive.open(member, "r") as handle:
        return handle.read(limit + 1)


def _entry_points(raw: bytes, artifact: Path, findings: list[Finding]) -> list[str]:
    if len(raw) > MAX_ENTRY_POINTS_SIZE:
        findings.append(Finding("PD039", "error", "Console entry-point metadata exceeds the safe size limit.",
                                "Regenerate entry_points.txt with a reasonable number of console scripts.", str(artifact)))
        return []
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(raw.decode("utf-8"))
    except (UnicodeDecodeError, configparser.Error) as exc:
        findings.append(
            Finding(
                "PD030",
                "error",
                "Console entry-point metadata is malformed.",
                "Regenerate entry_points.txt through the build backend.",
                str(artifact),
                str(exc)[:300],
            )
        )
        return []
    if not parser.has_section("console_scripts"):
        return []
    names: list[str] = []
    for name, target in parser.items("console_scripts"):
        if not name or any(c in name for c in "/\\\0"):
            findings.append(
                Finding(
                    "PD031",
                    "error",
                    "A console script has an invalid executable name.",
                    "Use a simple command name without path separators or control characters.",
                    str(artifact),
                    name[:150],
                )
            )
            continue
        if not target.strip():
            findings.append(
                Finding(
                    "PD032",
                    "error",
                    "A console script entry has an empty target.",
                    "Set each console script to a valid module:function target in project metadata.",
                    str(artifact),
                    name[:150],
                )
            )
            continue
        names.append(name)
    return sorted(set(names))


def audit_wheel(path: Path) -> ArtifactResult:
    """Inspect a wheel's metadata, paths, RECORD hashes, imports, and scripts."""
    path = path.resolve()
    size_bytes = path.stat().st_size if path.is_file() else 0
    result = ArtifactResult(path=str(path), kind="wheel", sha256="", size_bytes=size_bytes)
    if not path.is_file() or path.suffix != ".whl":
        result.findings.append(
            Finding("PD001", "error", "Expected an existing .whl file.", "Pass a valid wheel path.", str(path))
        )
        return result
    if size_bytes > MAX_ARCHIVE_FILE_SIZE:
        result.findings.append(Finding("PD048", "error", "Wheel file exceeds the compressed archive size limit.",
                                       "Review the artifact size; this release uses a 1 GiB safety limit for static inspection.", str(path),
                                       f"size_bytes={size_bytes}"))
        return result
    result.sha256 = sha256_file(path)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            within_limits = _archive_size_guard(((i.filename, i.file_size) for i in infos), path, result.findings)
            seen: set[str] = set()
            for info in infos:
                if info.filename in seen:
                    result.findings.append(
                        Finding(
                            "PD014", "error", "Archive contains duplicate member names.",
                            "Rebuild the wheel; every path must occur only once.", str(path), info.filename[:300]
                        )
                    )
                seen.add(info.filename)
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                if (unix_mode & 0o170000) == 0o120000:
                    result.findings.append(
                        Finding(
                            "PD015", "error", "Wheel contains a symbolic link.",
                            "Ship regular files in wheels; do not rely on symlink extraction semantics.",
                            str(path), info.filename[:300]
                        )
                    )
            bad_file = archive.testzip() if within_limits else None
            if bad_file is not None:
                result.findings.append(
                    Finding(
                        "PD016", "error", "Wheel CRC validation failed for a member.",
                        "Rebuild the wheel from a clean tree and verify the produced artifact.",
                        str(path), bad_file[:300]
                    )
                )
            names = [i.filename for i in infos]
            metadata_members = [n for n in names if n.endswith(".dist-info/METADATA")]
            wheel_members = [n for n in names if n.endswith(".dist-info/WHEEL")]
            record_members = [n for n in names if n.endswith(".dist-info/RECORD")]
            if len(metadata_members) != 1 or len(wheel_members) != 1 or len(record_members) != 1:
                result.findings.append(
                    Finding(
                        "PD017", "error", "Wheel must contain exactly one METADATA, WHEEL, and RECORD file.",
                        "Rebuild the distribution with a compliant PEP 427 wheel backend.", str(path),
                        f"METADATA={len(metadata_members)}, WHEEL={len(wheel_members)}, RECORD={len(record_members)}"
                    )
                )
                return result
            metadata_name = metadata_members[0]
            record_name = record_members[0]
            wheel_info_name = wheel_members[0]
            metadata_dist_info = metadata_name.rsplit("/", 1)[0]
            if not (record_name.startswith(metadata_dist_info + "/") and wheel_info_name.startswith(metadata_dist_info + "/")):
                result.findings.append(
                    Finding("PD018", "error", "Wheel metadata files belong to different .dist-info directories.",
                            "Rebuild the wheel with a standards-compliant backend.", str(path))
                )
            metadata_info = archive.getinfo(metadata_name)
            if metadata_info.file_size > MAX_METADATA_SIZE:
                result.findings.append(Finding("PD021", "error", "Distribution metadata exceeds the safe inspection size limit.",
                                               "Rebuild the distribution with reasonably sized metadata.", str(path)))
                metadata_raw = b""
            else:
                metadata_raw = _read_member_limited(archive, metadata_name, MAX_METADATA_SIZE)
            name, version = _parse_metadata(metadata_raw, path, result.findings)
            result.distribution = name
            result.version = version
            filename_parts = path.name[:-4].split("-")
            if len(filename_parts) not in (5, 6):
                result.findings.append(
                    Finding("PD019", "error", "Wheel filename does not have the expected five or six fields.",
                            "Use the standard distribution-version-python-abi-platform wheel filename.", str(path), path.name)
                )
            elif name and _normalized_name(filename_parts[0]) != _normalized_name(name):
                result.findings.append(
                    Finding("PD023", "error", "Wheel filename distribution name disagrees with METADATA.",
                            "Rebuild the wheel so its filename and internal metadata agree.", str(path),
                            f"filename={filename_parts[0]!r}; metadata={name!r}")
                )
            elif version and filename_parts[1] != version:
                result.findings.append(
                    Finding("PD024", "error", "Wheel filename version disagrees with METADATA.",
                            "Rebuild the wheel so its filename and internal metadata agree.", str(path),
                            f"filename={filename_parts[1]!r}; metadata={version!r}")
                )
            try:
                record_info = archive.getinfo(record_name)
                if record_info.file_size > MAX_RECORD_SIZE:
                    result.findings.append(Finding("PD026", "error", "Wheel RECORD exceeds the safe size limit.",
                                                   "Rebuild the wheel or reduce the number of shipped files.", str(path)))
                else:
                    with archive.open(record_name, "r") as record_handle:
                        result.findings.extend(_verify_record(record_handle, archive, path, record_name))
            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                result.findings.append(
                    Finding("PD025", "error", "Wheel RECORD could not be read or verified.",
                            "Rebuild the wheel; its RECORD file must be readable and consistent.", str(path), str(exc)[:300])
                )
            result.imports = _infer_imports(names)
            ep_member = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
            if ep_member:
                ep_info = archive.getinfo(ep_member)
                if ep_info.file_size > MAX_ENTRY_POINTS_SIZE:
                    result.findings.append(Finding("PD039", "error", "Console entry-point metadata exceeds the safe size limit.",
                                                   "Regenerate entry_points.txt with a reasonable number of console scripts.", str(path)))
                else:
                    result.console_scripts = _entry_points(_read_member_limited(archive, ep_member, MAX_ENTRY_POINTS_SIZE), path, result.findings)
    except (OSError, zipfile.BadZipFile, RuntimeError, ArchiveAuditError) as exc:
        result.findings.append(
            Finding("PD002", "error", "Wheel archive could not be inspected.",
                    "Confirm the file is a complete wheel and rebuild if necessary.", str(path), str(exc)[:300])
        )
    return result


def _verify_record(
    record_handle: BinaryIO,
    archive: zipfile.ZipFile,
    artifact: Path,
    record_name: str,
) -> list[Finding]:
    findings: list[Finding] = []
    try:
        raw = record_handle.read(MAX_RECORD_SIZE + 1)
        if len(raw) > MAX_RECORD_SIZE:
            return [Finding("PD026", "error", "Wheel RECORD exceeds the safe size limit.",
                            "Rebuild the wheel or reduce the number of shipped files.", str(artifact))]
        text = raw.decode("utf-8")
        rows = list(csv.reader(io.StringIO(text, newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        return [Finding("PD026", "error", "Wheel RECORD is not valid UTF-8 CSV.",
                        "Rebuild the wheel using a compliant backend.", str(artifact), str(exc)[:300])]
    recorded: dict[str, tuple[str, str]] = {}
    for row in rows:
        if len(row) != 3:
            findings.append(Finding("PD027", "error", "Wheel RECORD contains a row with the wrong number of columns.",
                                    "Rebuild the wheel; every RECORD row must have path, hash, and size columns.",
                                    str(artifact)))
            continue
        name, digest, size = row
        if not _safe_member_name(name) or name in recorded:
            findings.append(Finding("PD028", "error", "Wheel RECORD contains an unsafe or duplicate path.",
                                    "Rebuild the wheel with unique relative paths in RECORD.", str(artifact), name[:300]))
            continue
        recorded[name] = (digest, size)
    archive_names = {info.filename for info in archive.infolist()}
    payload_names = {info.filename for info in archive.infolist() if not info.is_dir()}
    expected = payload_names - {record_name, record_name + ".jws", record_name + ".p7s"}
    missing = sorted(expected - set(recorded))
    extra = sorted(set(recorded) - archive_names)
    if missing:
        findings.append(Finding("PD029", "error", "Wheel RECORD omits archive members.",
                                "Rebuild the wheel so RECORD covers every shipped file (except permitted signature files and RECORD itself).",
                                str(artifact), ", ".join(missing[:10])))
    if extra:
        findings.append(Finding("PD033", "error", "Wheel RECORD refers to members not present in the archive.",
                                "Rebuild the wheel so RECORD exactly describes its contents.", str(artifact), ", ".join(extra[:10])))
    for member, (declared_hash, declared_size) in recorded.items():
        if member == record_name:
            if declared_hash or declared_size:
                findings.append(Finding("PD034", "error", "Wheel RECORD must leave its own hash and size empty.",
                                        "Regenerate the wheel using a compliant build backend.", str(artifact), member))
            continue
        if member not in archive_names or member.endswith((".jws", ".p7s")):
            continue
        if not declared_hash or not declared_size:
            findings.append(Finding("PD035", "error", "Wheel RECORD has an empty hash or size for a payload member.",
                                    "Rebuild the wheel and verify the generated RECORD file.", str(artifact), member[:300]))
            continue
        algorithm, sep, expected_digest = declared_hash.partition("=")
        normalized_algorithm = algorithm.lower()
        if not sep or normalized_algorithm not in {"sha256", "sha384", "sha512"}:
            findings.append(Finding("PD036", "error", "Wheel RECORD uses a missing or unsupported payload hash.",
                                    "Rebuild with SHA-256, SHA-384, or SHA-512 hashes in RECORD.", str(artifact), f"{member}: {declared_hash[:80]}"))
            continue
        digest = hashlib.new(normalized_algorithm)
        size = 0
        try:
            with archive.open(member, "r") as stream:
                for block in iter(lambda: stream.read(64 * 1024), b""):
                    size += len(block)
                    digest.update(block)
        except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
            findings.append(Finding("PD037", "error", "A wheel member could not be read for RECORD verification.",
                                    "Rebuild the wheel and inspect the failing file.", str(artifact), f"{member}: {exc}"[:300]))
            continue
        observed = base64.urlsafe_b64encode(digest.digest()).decode("ascii").rstrip("=")
        if observed != expected_digest or str(size) != declared_size:
            findings.append(Finding("PD038", "error", "Wheel RECORD hash or size does not match a payload member.",
                                    "Rebuild the wheel from the intended source tree; do not edit a wheel in place.",
                                    str(artifact), member[:300]))
    return findings


def audit_sdist(path: Path) -> ArtifactResult:
    """Inspect source-distribution paths and PKG-INFO without extracting the archive."""
    path = path.resolve()
    size_bytes = path.stat().st_size if path.is_file() else 0
    result = ArtifactResult(path=str(path), kind="sdist", sha256="", size_bytes=size_bytes)
    if not path.is_file():
        result.findings.append(Finding("PD040", "error", "Expected an existing source distribution file.",
                                       "Pass a .tar.gz, .tar.bz2, .tar.xz, or .zip source distribution.", str(path)))
        return result
    if size_bytes > MAX_ARCHIVE_FILE_SIZE:
        result.findings.append(Finding("PD048", "error", "Source archive exceeds the compressed archive size limit.",
                                       "Review the artifact size; this release uses a 1 GiB safety limit for static inspection.", str(path),
                                       f"size_bytes={size_bytes}"))
        return result
    result.sha256 = sha256_file(path)
    try:
        if path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz")):
            with tarfile.open(path, mode="r:*") as archive:
                members = archive.getmembers()
                _archive_size_guard(((m.name, m.size if m.isfile() else 0) for m in members), path, result.findings)
                member_names = [m.name for m in members]
                duplicates = sorted(name for name, count in Counter(member_names).items() if count > 1)
                for duplicate in duplicates[:10]:
                    result.findings.append(Finding("PD047", "error", "Source archive contains duplicate member names.",
                                                   "Rebuild the source archive with unique member paths.", str(path), duplicate[:300]))
                for member in members:
                    if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                        result.findings.append(Finding("PD041", "error", "Source archive contains a link or special filesystem entry.",
                                                       "Ship regular files only; avoid symlinks and device entries in an sdist.",
                                                       str(path), member.name[:300]))
                pkg_infos = [
                    m for m in members
                    if m.isfile()
                    and len(m.name.rstrip("/").split("/")) == 2
                    and m.name.rstrip("/").split("/")[-1] == "PKG-INFO"
                ]
                if len(pkg_infos) != 1:
                    result.findings.append(Finding("PD042", "error", "Source distribution must contain exactly one root PKG-INFO file.",
                                                   "Rebuild the sdist with valid package metadata.", str(path), f"count={len(pkg_infos)}"))
                else:
                    file_obj = archive.extractfile(pkg_infos[0])
                    if file_obj is None:
                        raw = b""
                    else:
                        with file_obj:
                            raw = file_obj.read(MAX_METADATA_SIZE + 1)
                    name, version = _parse_metadata(raw, path, result.findings)
                    result.distribution, result.version = name, version
                roots = {m.name.rstrip("/").split("/", 1)[0] for m in members if m.name.rstrip("/")}
                if len(roots) != 1:
                    result.findings.append(Finding("PD043", "error", "Source distribution does not have exactly one top-level directory.",
                                                   "Rebuild the sdist with the project as one root directory.", str(path), ", ".join(sorted(roots)[:10])))
        elif path.suffix == ".zip":
            with zipfile.ZipFile(path, "r") as archive:
                infos = archive.infolist()
                within_limits = _archive_size_guard(((i.filename, i.file_size) for i in infos), path, result.findings)
                info_names = [item.filename for item in infos]
                duplicates = sorted(name for name, count in Counter(info_names).items() if count > 1)
                for duplicate in duplicates[:10]:
                    result.findings.append(Finding("PD047", "error", "Source archive contains duplicate member names.",
                                                   "Rebuild the source archive with unique member paths.", str(path), duplicate[:300]))
                if within_limits and archive.testzip() is not None:
                    result.findings.append(Finding("PD044", "error", "Source zip CRC validation failed.",
                                                   "Rebuild the source distribution.", str(path)))
                pkg_infos = [
                    i for i in infos
                    if len(i.filename.rstrip("/").split("/")) == 2
                    and i.filename.rstrip("/").split("/")[-1] == "PKG-INFO"
                ]
                if len(pkg_infos) != 1:
                    result.findings.append(Finding("PD042", "error", "Source distribution must contain exactly one root PKG-INFO file.",
                                                   "Rebuild the sdist with valid package metadata.", str(path), f"count={len(pkg_infos)}"))
                else:
                    name, version = _parse_metadata(_read_member_limited(archive, pkg_infos[0].filename, MAX_METADATA_SIZE), path, result.findings)
                    result.distribution, result.version = name, version
                roots = {i.filename.rstrip("/").split("/", 1)[0] for i in infos if i.filename.rstrip("/")}
                if len(roots) != 1:
                    result.findings.append(Finding("PD043", "error", "Source distribution does not have exactly one top-level directory.",
                                                   "Rebuild the sdist with the project as one root directory.", str(path), ", ".join(sorted(roots)[:10])))
        else:
            result.findings.append(Finding("PD045", "error", "Unsupported source distribution format.",
                                           "Pass a .tar.gz, .tar.bz2, .tar.xz, .tgz, or .zip source distribution.", str(path)))
    except (OSError, tarfile.TarError, zipfile.BadZipFile, RuntimeError) as exc:
        result.findings.append(Finding("PD046", "error", "Source distribution could not be inspected.",
                                       "Confirm the archive is complete and uses a supported source distribution format.",
                                       str(path), str(exc)[:300]))
    return result


def extract_sdist_safely(path: Path, destination: Path, audit: ArtifactResult) -> Path:
    """Extract an already-audited sdist without archive-controlled paths or links.

    This is deliberately separate from static inspection and called only when the
    audit has no errors. It re-checks critical constraints during extraction.
    """
    if audit.kind != "sdist" or audit.has_errors:
        raise ArchiveAuditError("source distribution has audit errors and will not be extracted")
    path = path.resolve()
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ArchiveAuditError("extraction destination must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    count = 0

    def target_for(raw_name: str, is_dir: bool) -> Path:
        if not _safe_member_name(raw_name):
            raise ArchiveAuditError(f"unsafe archive member path: {raw_name[:200]}")
        normalized = raw_name[:-1] if is_dir and raw_name.endswith("/") else raw_name
        target = destination.joinpath(*normalized.split("/"))
        resolved = target.resolve()
        if resolved != destination and destination not in resolved.parents:
            raise ArchiveAuditError(f"archive member escapes extraction destination: {raw_name[:200]}")
        return target

    def write_member(raw_name: str, size: int, is_dir: bool, stream: BinaryIO | None) -> None:
        nonlocal total_bytes, count
        count += 1
        if count > MAX_ARCHIVE_MEMBERS:
            raise ArchiveAuditError("archive member count exceeds the safe extraction limit")
        target = target_for(raw_name, is_dir)
        if is_dir:
            target.mkdir(parents=True, exist_ok=True)
            return
        if stream is None or size < 0 or size > MAX_MEMBER_SIZE:
            raise ArchiveAuditError(f"unsupported or oversized source member: {raw_name[:200]}")
        total_bytes += size
        if total_bytes > MAX_TOTAL_UNCOMPRESSED:
            raise ArchiveAuditError("source archive exceeds the safe total extraction size")
        target.parent.mkdir(parents=True, exist_ok=True)
        observed = 0
        try:
            with target.open("xb") as output:
                while True:
                    block = stream.read(64 * 1024)
                    if not block:
                        break
                    observed += len(block)
                    if observed > size or observed > MAX_MEMBER_SIZE:
                        raise ArchiveAuditError(f"archive member expanded beyond its declared size: {raw_name[:200]}")
                    output.write(block)
        except Exception:
            try:
                target.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        if observed != size:
            target.unlink(missing_ok=True)
            raise ArchiveAuditError(f"archive member size did not match its header: {raw_name[:200]}")

    if path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz")):
        with tarfile.open(path, mode="r:*") as archive:
            members = archive.getmembers()
            # Validate duplicates and every entry type before writing any member.
            names = [member.name for member in members]
            if len(names) != len(set(names)):
                raise ArchiveAuditError("source archive contains duplicate member paths")
            for member in members:
                if not (member.isdir() or member.isfile()):
                    raise ArchiveAuditError(f"source archive contains a link or special entry: {member.name[:200]}")
                if not _safe_member_name(member.name):
                    raise ArchiveAuditError(f"unsafe archive member path: {member.name[:200]}")
            for member in members:
                if member.isdir():
                    write_member(member.name, 0, True, None)
                elif member.isfile():
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise ArchiveAuditError(f"could not read source member: {member.name[:200]}")
                    with stream:
                        write_member(member.name, member.size, False, stream)
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise ArchiveAuditError("source archive contains duplicate member paths")
            for info in infos:
                if not _safe_member_name(info.filename):
                    raise ArchiveAuditError(f"unsafe archive member path: {info.filename[:200]}")
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = mode & 0o170000
                if file_type not in {0, 0o040000, 0o100000}:
                    raise ArchiveAuditError(f"source archive contains a link or special entry: {info.filename[:200]}")
            for info in infos:
                is_dir = info.is_dir()
                if is_dir:
                    write_member(info.filename, 0, True, None)
                else:
                    with archive.open(info, "r") as stream:
                        write_member(info.filename, info.file_size, False, stream)
    else:
        raise ArchiveAuditError("unsupported source distribution format")

    # Infer the root from the extracted filesystem, not an unchecked archive path.
    roots = {child.name for child in destination.iterdir()}
    if len(roots) != 1:
        raise ArchiveAuditError("source distribution must unpack to exactly one top-level project directory")
    root = destination / next(iter(roots))
    if not root.is_dir() or not (root / "pyproject.toml").is_file():
        raise ArchiveAuditError("source distribution root must contain pyproject.toml")
    return root


def audit_artifact(path: Path) -> ArtifactResult:
    """Dispatch an artifact to the correct static audit."""
    if path.name.endswith(".whl"):
        return audit_wheel(path)
    return audit_sdist(path)
