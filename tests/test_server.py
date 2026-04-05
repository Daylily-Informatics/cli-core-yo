"""Tests for cli_core_yo.server."""

from __future__ import annotations

import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import call, patch

import pytest

from cli_core_yo import server


class TestReadPid:
    def test_missing_pid_file_returns_none(self, tmp_path: Path):
        assert server.read_pid(tmp_path / "server.pid") is None

    def test_returns_pid_when_process_is_alive(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with patch("cli_core_yo.server.os.kill") as mock_kill:
            assert server.read_pid(pid_file) == 123

        mock_kill.assert_called_once_with(123, 0)

    def test_invalid_pid_file_is_removed(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("not-an-int", encoding="utf-8")

        assert server.read_pid(pid_file) is None
        assert not pid_file.exists()

    def test_dead_process_pid_file_is_removed(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with patch("cli_core_yo.server.os.kill", side_effect=ProcessLookupError):
            assert server.read_pid(pid_file) is None

        assert not pid_file.exists()

    def test_permission_error_removes_pid_file(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with patch("cli_core_yo.server.os.kill", side_effect=PermissionError):
            assert server.read_pid(pid_file) is None

        assert not pid_file.exists()


class TestWritePid:
    def test_creates_parent_dirs_and_writes_pid(self, tmp_path: Path):
        pid_file = tmp_path / "run" / "server.pid"

        server.write_pid(pid_file, 456)

        assert pid_file.read_text(encoding="utf-8") == "456"


class TestLogHelpers:
    def test_new_log_path_uses_timestamp_and_prefix(self, tmp_path: Path):
        fixed_now = datetime(2026, 4, 5, 12, 34, 56, tzinfo=timezone.utc)

        class FakeDateTime:
            @staticmethod
            def now(tz=None):
                assert tz == timezone.utc
                return fixed_now

        with patch("cli_core_yo.server.datetime", FakeDateTime):
            path = server.new_log_path(tmp_path / "logs", prefix="api")

        assert path == tmp_path / "logs" / "api_20260405_123456.log"
        assert path.parent.is_dir()

    def test_latest_log_returns_none_when_dir_missing(self, tmp_path: Path):
        assert server.latest_log(tmp_path / "logs") is None

    def test_latest_log_returns_newest_matching_file(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        older = log_dir / "server_20260405_010101.log"
        newer = log_dir / "server_20260405_020202.log"
        ignored = log_dir / "other_20260405_030303.log"
        older.write_text("old", encoding="utf-8")
        newer.write_text("new", encoding="utf-8")
        ignored.write_text("ignore", encoding="utf-8")

        assert server.latest_log(log_dir) == newer

    def test_list_logs_returns_newest_first_with_limit(self, tmp_path: Path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        created = []
        for ts in ("20260405_010101", "20260405_020202", "20260405_030303"):
            path = log_dir / f"server_{ts}.log"
            path.write_text(ts, encoding="utf-8")
            created.append(path)

        logs = server.list_logs(log_dir, limit=2)

        assert logs == [created[2], created[1]]

    def test_list_logs_returns_empty_for_missing_dir(self, tmp_path: Path):
        assert server.list_logs(tmp_path / "logs") == []


class TestStopPid:
    def test_returns_no_server_running_when_no_pid(self, tmp_path: Path):
        with patch("cli_core_yo.server.read_pid", return_value=None):
            stopped, message = server.stop_pid(tmp_path / "server.pid")

        assert stopped is False
        assert message == "No server running"

    def test_stops_process_gracefully(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        def fake_kill(pid: int, sig: int) -> None:
            if sig == signal.SIGTERM:
                return
            if sig == 0:
                raise ProcessLookupError

        with (
            patch("cli_core_yo.server.read_pid", return_value=123),
            patch("cli_core_yo.server.os.kill", side_effect=fake_kill) as mock_kill,
            patch("cli_core_yo.server.time.monotonic", side_effect=[0.0, 0.1]),
            patch("cli_core_yo.server.time.sleep"),
        ):
            stopped, message = server.stop_pid(pid_file)

        assert stopped is True
        assert message == "Server stopped (was PID 123)"
        assert not pid_file.exists()
        assert mock_kill.call_args_list == [call(123, signal.SIGTERM), call(123, 0)]

    def test_escalates_to_sigkill_after_timeout(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with (
            patch("cli_core_yo.server.read_pid", return_value=123),
            patch("cli_core_yo.server.os.kill") as mock_kill,
            patch("cli_core_yo.server.time.monotonic", side_effect=[0.0, 0.0, 0.2]),
            patch("cli_core_yo.server.time.sleep"),
        ):
            stopped, message = server.stop_pid(pid_file, grace_seconds=0.1)

        assert stopped is True
        assert message == "Server stopped (was PID 123)"
        assert mock_kill.call_args_list == [
            call(123, signal.SIGTERM),
            call(123, 0),
            call(123, signal.SIGKILL),
        ]

    def test_reports_server_not_running_when_process_missing(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with (
            patch("cli_core_yo.server.read_pid", return_value=123),
            patch("cli_core_yo.server.os.kill", side_effect=ProcessLookupError),
        ):
            stopped, message = server.stop_pid(pid_file)

        assert stopped is False
        assert message == "Server was not running"
        assert not pid_file.exists()

    def test_reports_permission_denied(self, tmp_path: Path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("123", encoding="utf-8")

        with (
            patch("cli_core_yo.server.read_pid", return_value=123),
            patch("cli_core_yo.server.os.kill", side_effect=PermissionError),
        ):
            stopped, message = server.stop_pid(pid_file)

        assert stopped is False
        assert message == "Permission denied stopping PID 123"


class TestTailFollow:
    def test_tail_follow_invokes_tail_command(self, tmp_path: Path):
        log_file = tmp_path / "server.log"

        with patch("cli_core_yo.server.subprocess.run") as mock_run:
            server.tail_follow(log_file, lines=25)

        mock_run.assert_called_once_with(["tail", "-f", "-n", "25", str(log_file)])


class TestSourceEnvFile:
    def test_missing_env_file_returns_false(self, tmp_path: Path):
        assert server.source_env_file(tmp_path / ".env") is False

    def test_parses_simple_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join(
                [
                    "# comment",
                    "PLAIN=value",
                    "DOUBLE=\"quoted value\"",
                    "SINGLE='another value'",
                    "INVALID_LINE",
                    "SPACED = spaced",
                ]
            ),
            encoding="utf-8",
        )

        for key in ("PLAIN", "DOUBLE", "SINGLE", "SPACED"):
            monkeypatch.delenv(key, raising=False)

        assert server.source_env_file(env_file) is True
        assert os.environ["PLAIN"] == "value"
        assert os.environ["DOUBLE"] == "quoted value"
        assert os.environ["SINGLE"] == "another value"
        assert os.environ["SPACED"] == "spaced"


class TestDisplayHost:
    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "127.0.0.1"])
    def test_maps_bind_all_hosts_to_localhost(self, host: str):
        assert server.display_host(host) == "localhost"

    def test_preserves_non_local_host(self):
        assert server.display_host("example.com") == "example.com"
