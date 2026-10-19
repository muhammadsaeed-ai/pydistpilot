"""Bounded subprocess runner; never invokes a command through a shell."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from pydistpilot.privacy import redact

MAX_CAPTURE_BYTES = 64 * 1024


@dataclass(slots=True)
class ProcessResult:
    argv: list[str]
    returncode: int | None
    duration_seconds: float
    output: str
    timed_out: bool
    output_truncated: bool


def run_process(
    argv: Sequence[str | os.PathLike[str]],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Run a non-shell command with bounded in-memory output and a hard timeout."""
    cmd = [os.fspath(arg) for arg in argv]
    started = time.monotonic()
    captured = bytearray()
    total_seen = 0
    read_error: list[BaseException] = []
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
        close_fds=True,
        start_new_session=(os.name == "posix"),
        creationflags=(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0),
    )
    assert proc.stdout is not None

    def drain() -> None:
        nonlocal total_seen
        try:
            while True:
                chunk = proc.stdout.read(16 * 1024)
                if not chunk:
                    break
                total_seen += len(chunk)
                remaining = MAX_CAPTURE_BYTES - len(captured)
                if remaining > 0:
                    captured.extend(chunk[:remaining])
        except Exception as exc:  # propagate reader failures to the caller
            read_error.append(exc)

    reader = threading.Thread(target=drain, name="pydistpilot-output-drain", daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "posix":
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            # On Windows, terminate descendants as well when taskkill is available;
            # a timed-out build backend may have launched compiler/helper processes.
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                    shell=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass
            if proc.poll() is None:
                proc.kill()
        proc.wait()
    finally:
        reader.join(timeout=max(1.0, min(timeout, 10.0)))
        if reader.is_alive():
            proc.stdout.close()
            reader.join(timeout=1.0)
        proc.stdout.close()

    if read_error:
        raise RuntimeError(f"could not capture child-process output: {read_error[0]}")
    output = redact(captured.decode("utf-8", errors="replace"))
    if total_seen > len(captured):
        output += "\n[output truncated by PyDistPilot]"
    return ProcessResult(
        argv=cmd,
        returncode=proc.returncode,
        duration_seconds=time.monotonic() - started,
        output=output,
        timed_out=timed_out,
        output_truncated=total_seen > len(captured),
    )
