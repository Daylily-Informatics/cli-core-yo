"""Shared server lifecycle utilities for CLI services.

Provides reusable helpers for PID management, log file handling,
process start/stop, and .env file sourcing.  Service CLIs import
these instead of copy-pasting the same boilerplate.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


# -- PID helpers ----------------------------------------------------------------


def read_pid(pid_file: Path) -> int | None:
    """Return the PID stored in *pid_file* if the process is alive, else None.

    Stale PID files are cleaned up automatically.
    """
    if not pid_file.exists():
        return None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # signal 0 = existence check
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        pid_file.unlink(missing_ok=True)
        return None


def write_pid(pid_file: Path, pid: int) -> None:
    """Persist *pid* to *pid_file*, creating parent dirs as needed."""
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))


# -- Log helpers ----------------------------------------------------------------


def new_log_path(log_dir: Path, prefix: str = "server") -> Path:
    """Return a timestamped log file path under *log_dir*."""
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return log_dir / f"{prefix}_{ts}.log"


def latest_log(log_dir: Path, prefix: str = "server") -> Path | None:
    """Return the most recent ``{prefix}_*.log`` file, or None."""
    if not log_dir.exists():
        return None
    logs = sorted(log_dir.glob(f"{prefix}_*.log"), reverse=True)
    return logs[0] if logs else None


def list_logs(log_dir: Path, prefix: str = "server", limit: int = 20) -> list[Path]:
    """Return up to *limit* log files sorted newest-first."""
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob(f"{prefix}_*.log"), reverse=True)[:limit]


# -- Process lifecycle ----------------------------------------------------------


def stop_pid(pid_file: Path, *, grace_seconds: float = 5.0) -> tuple[bool, str]:
    """Stop the process whose PID is stored in *pid_file*.

    Returns ``(stopped, message)`` where *stopped* is True on success.
    Uses SIGTERM first, then SIGKILL after *grace_seconds*.
    """
    pid = read_pid(pid_file)
    if pid is None:
        return False, "No server running"

    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            os.kill(pid, signal.SIGKILL)

        pid_file.unlink(missing_ok=True)
        return True, f"Server stopped (was PID {pid})"
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False, "Server was not running"
    except PermissionError:
        return False, f"Permission denied stopping PID {pid}"


def tail_follow(log_file: Path, lines: int = 50) -> None:
    """``tail -f -n`` wrapper -- blocks until Ctrl-C."""
    subprocess.run(["tail", "-f", "-n", str(lines), str(log_file)])


# -- Env file sourcing ----------------------------------------------------------


def source_env_file(env_file: Path) -> bool:
    """Parse a simple KEY=VALUE ``.env`` file into ``os.environ``.

    Ignores comments (``#``) and blank lines.  Strips surrounding quotes.
    Returns True if the file existed and was processed.
    """
    if not env_file.exists():
        return False
    with open(env_file) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip().strip('"').strip("'")
            os.environ[key.strip()] = value
    return True


# -- Display helpers -------------------------------------------------------------


def display_host(host: str) -> str:
    """Map bind-all addresses to ``localhost`` for user-facing URLs."""
    if host in ("0.0.0.0", "::", "127.0.0.1"):
        return "localhost"
    return host
