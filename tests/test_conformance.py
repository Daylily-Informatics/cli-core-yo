"""Tests for cli_core_yo.conformance."""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import click
import pytest
import typer
from typer.testing import CliRunner

from cli_core_yo import conformance


def _json_app() -> typer.Typer:
    app = typer.Typer()

    @app.callback(invoke_without_command=True)
    def hello(name: str = typer.Option("world", "--name")) -> None:
        click.echo(json.dumps({"hello": name}))

    return app


class TestBuildRunner:
    def test_falls_back_when_mix_stderr_is_not_supported(self) -> None:
        runner = conformance.build_runner()
        assert isinstance(runner, CliRunner)

    def test_uses_mix_stderr_when_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class FakeRunner:
            def __init__(self, *, mix_stderr: bool = False) -> None:
                self.mix_stderr = mix_stderr

        def fake_signature(_obj: object) -> inspect.Signature:
            return inspect.Signature(
                [
                    inspect.Parameter(
                        "mix_stderr",
                        inspect.Parameter.KEYWORD_ONLY,
                        default=False,
                    )
                ]
            )

        monkeypatch.setattr(conformance, "CliRunner", FakeRunner)
        monkeypatch.setattr(conformance.inspect, "signature", fake_signature)

        runner = conformance.build_runner(mix_stderr=True)

        assert isinstance(runner, FakeRunner)
        assert runner.mix_stderr is True


class TestInvokeAndReaders:
    def test_invoke_passes_through_arguments(self) -> None:
        result = conformance.invoke(
            _json_app(),
            ["--name", "codex"],
            env={"DEMO_ENV": "1"},
            prog_name="demo",
        )

        assert result.exit_code == 0
        assert conformance.json_output(result) == {"hello": "codex"}

    def test_stdout_text_uses_stdout_when_available(self) -> None:
        result = SimpleNamespace(stdout='{"hello": "world"}\n')
        assert conformance.stdout_text(result).strip() == '{"hello": "world"}'

    def test_stdout_text_falls_back_to_output(self) -> None:
        result = SimpleNamespace(output="fallback\n")
        assert conformance.stdout_text(result) == "fallback\n"

    def test_stderr_text_reads_separate_stream(self) -> None:
        result = SimpleNamespace(stderr="problem\n")
        assert conformance.stderr_text(result) == "problem\n"

    def test_combined_output_prefers_output_attribute(self) -> None:
        result = SimpleNamespace(output="combined\n", stdout="ignored\n", stderr="ignored\n")
        assert conformance.combined_output(result) == "combined\n"

    def test_combined_output_falls_back_to_stdout_and_stderr(self) -> None:
        result = SimpleNamespace(stdout="left\n", stderr="right\n")
        assert conformance.combined_output(result) == "left\nright\n"


class TestAssertions:
    def test_assert_exit_code_returns_result(self) -> None:
        result = SimpleNamespace(exit_code=0, output="")
        assert conformance.assert_exit_code(result, 0) is result

    def test_assert_exit_code_raises_with_output(self) -> None:
        result = SimpleNamespace(exit_code=2, output="boom\n")

        with pytest.raises(AssertionError, match="expected exit code 0, got 2"):
            conformance.assert_exit_code(result, 0)

    def test_assert_json_output_returns_decoded_payload(self) -> None:
        result = conformance.invoke(_json_app(), [])
        assert conformance.assert_json_output(result) == {"hello": "world"}

    def test_assert_json_output_compares_expected_payload(self) -> None:
        result = conformance.invoke(_json_app(), [])
        assert conformance.assert_json_output(result, {"hello": "world"}) == {"hello": "world"}

    def test_assert_json_output_raises_on_mismatch(self) -> None:
        result = conformance.invoke(_json_app(), [])

        with pytest.raises(AssertionError, match="expected JSON"):
            conformance.assert_json_output(result, {"hello": "codex"})

    def test_assert_no_ansi_allows_plain_text(self) -> None:
        conformance.assert_no_ansi("plain text")

    def test_assert_no_ansi_rejects_escape_sequences(self) -> None:
        with pytest.raises(AssertionError, match="ANSI escape codes found"):
            conformance.assert_no_ansi("\x1b[31mred\x1b[0m")

    def test_assert_stdout_only_allows_empty_stderr(self) -> None:
        conformance.assert_stdout_only(SimpleNamespace(stderr=""))

    def test_assert_stdout_only_rejects_stderr_output(self) -> None:
        with pytest.raises(AssertionError, match="unexpected stderr output"):
            conformance.assert_stdout_only(SimpleNamespace(stderr="warn\n"))
