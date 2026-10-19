from __future__ import annotations

import sys

from pydistpilot.privacy import redact
from pydistpilot.process import MAX_CAPTURE_BYTES, run_process


def test_redacts_common_secrets() -> None:
    output = redact("API_KEY=supersecret123 Authorization: Bearer abcdef123456")
    assert "supersecret123" not in output
    assert "abcdef123456" not in output
    assert "[REDACTED]" in output


def test_subprocess_captures_output_with_bound(tmp_path) -> None:
    result = run_process([sys.executable, "-c", "print('x' * 200000)"], cwd=tmp_path, timeout=5)
    assert result.returncode == 0
    assert result.output_truncated
    assert len(result.output.encode()) <= MAX_CAPTURE_BYTES + 100
    assert "output truncated" in result.output


def test_subprocess_timeout_is_enforced(tmp_path) -> None:
    result = run_process([sys.executable, "-c", "import time; time.sleep(3)"], cwd=tmp_path, timeout=0.15)
    assert result.timed_out
    assert result.returncode is not None
