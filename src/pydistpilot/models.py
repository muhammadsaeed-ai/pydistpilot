"""Small, serializable result models shared by auditing and verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    message: str
    recommendation: str
    path: str | None = None
    evidence: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArtifactResult:
    path: str
    kind: str
    sha256: str
    size_bytes: int
    distribution: str | None = None
    version: str | None = None
    imports: list[str] = field(default_factory=list)
    console_scripts: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(f.severity == "error" for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["findings"] = [f.to_dict() for f in self.findings]
        result["has_errors"] = self.has_errors
        return result


@dataclass(slots=True)
class SmokeResult:
    artifact: str
    check: str
    target: str
    status: Literal["passed", "failed", "skipped"]
    duration_seconds: float
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationReport:
    schema_version: int = 1
    tool: str = "pydistpilot"
    tool_version: str = "0.2.0"
    project: str = ""
    started_at: str = ""
    duration_seconds: float = 0.0
    status: Literal["passed", "failed"] = "failed"
    artifacts: list[ArtifactResult] = field(default_factory=list)
    smoke_checks: list[SmokeResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(f.severity == "error" for f in self.findings) + sum(
            f.severity == "error" for a in self.artifacts for f in a.findings
        ) + sum(s.status == "failed" for s in self.smoke_checks)

    @property
    def warning_count(self) -> int:
        return sum(f.severity == "warning" for f in self.findings) + sum(
            f.severity == "warning" for a in self.artifacts for f in a.findings
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "tool_version": self.tool_version,
            "project": self.project,
            "started_at": self.started_at,
            "duration_seconds": round(self.duration_seconds, 3),
            "status": self.status,
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "artifacts": len(self.artifacts),
                "smoke_checks": len(self.smoke_checks),
                "smoke_failures": sum(s.status == "failed" for s in self.smoke_checks),
            },
            "artifacts": [a.to_dict() for a in self.artifacts],
            "smoke_checks": [s.to_dict() for s in self.smoke_checks],
            "findings": [f.to_dict() for f in self.findings],
        }
