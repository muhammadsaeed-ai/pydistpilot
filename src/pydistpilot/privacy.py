"""Conservative redaction for command output stored in reports."""

from __future__ import annotations

import re

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|passwd|secret)\b\s*[:=]\s*)"
            r"(['\"]?)[^\s,'\"]{4,}\2"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"), r"\1[REDACTED]@"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
)


def redact(text: str) -> str:
    """Redact common credential patterns; this is best-effort, not a DLP guarantee."""
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result
