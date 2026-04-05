"""README example validation."""

from __future__ import annotations

import sys
from pathlib import Path

import mktestdocs.__main__ as mktestdocs_main
from mktestdocs import check_md_file


def test_readme_python_examples(monkeypatch, tmp_path):
    def exec_python_allowing_successful_exit(source: str) -> None:
        try:
            exec(source, {"__name__": "__main__"})
        except SystemExit as exc:
            if exc.code not in (None, 0):
                print(source)
                raise
        except Exception:
            print(source)
            raise

    monkeypatch.setattr(sys, "argv", ["README.py"])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setitem(
        mktestdocs_main._executors,
        "python",
        exec_python_allowing_successful_exit,
    )

    check_md_file(fpath=Path("README.md"), lang="python", memory=True)
