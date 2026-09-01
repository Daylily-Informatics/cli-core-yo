# CLI syntax validation 2.2.0 control ledger

## Control Ledger

Controlling plan: GitHub issue `#10`, "Add config-driven CLI syntax validator for downstream drift detection," plus the user direction in this task.

Ledger path: `docs/plans/20260901T104909Z_cli_syntax_validation_ledger.md`

Gate 0 baseline:

- Repo state: `cli-core-yo` was clean on new branch `codex/cli-core-yo-syntax-validation`, based on `origin/main`/`origin/jemdev10` `a99e761097dd9a0e3e8ed3c39fc4d1470c259bce` (release `2.1.1`).
- Sweep commands: `git grep -n -i -E 'syntax.?validation|validate_cli|ValidationReport|SyntaxValidation' origin/main -- 'cli_core_yo/**' 'tests/**' 'README.md'` -> no current implementation; inspected `cli_core_yo/conformance.py`, `cli_core_yo/app.py`, `cli_core_yo/registry.py`, `cli_core_yo/spec.py`, and their tests.
- Baseline checks: `.venv/bin/python -m pytest -q` -> exit `0`.
- Assumptions and live limits: the validator is an opt-in library/CI API. It must not run during `create_app()` or `run()` without an explicit caller request; the requested `2.2.0` release includes normal GitHub PR/merge/tag/build/package publication steps.

| ID | Area/Repo | Requirement/Surface | Status | Category | Approval Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| VAL-001 | `cli_core_yo.validation` | Implement an opt-in, config-driven normalized CLI-surface validator with structured findings, strict/advisory modes, policy checks, and allowlisting. | SUCCESS | feature_implementation | Gate 1 | `/root` | `cli_core_yo/validation.py`; `.venv/bin/python -m pytest -q` -> `0`; Ruff and mypy pass after the recorded style repair. |  | Explicit calls to `validate_cli(app, config)` return structured reports and never change app construction or command invocation. |
| VAL-002 | `CommandRegistry` | Expose the minimum immutable registration surface needed to normalize commands/groups without changing existing registration behavior. | SUCCESS | feature_implementation | Gate 1 | `/root` | `cli_core_yo/registry.py`, `tests/test_registry.py::TestCommandRegistry::test_surface_snapshots_are_deterministic`. |  | Deterministic command and group snapshots are additive registry APIs. |
| VAL-003 | Tests | Cover required/forbidden paths, root flags, policy mismatch, allowlisted drift, warning/fail behavior, and invalid surface syntax. | SUCCESS | contract_test | Gate 5 | `/root` | `tests/test_validation.py`; focused tests and `.venv/bin/python -m pytest -q` -> `0`. |  | Contract coverage includes each declared drift class and machine-readable report fields. |
| VAL-004 | Compatibility | Prove an existing `CliSpec` without syntax-validation configuration produces the same command surface and invocation behavior. | SUCCESS | contract_test | Gate 5 | `/root` | `tests/test_validation.py::TestNormalizeCli::test_existing_cli_spec_is_unchanged_when_validation_is_not_requested` and `...test_validation_is_observational_and_does_not_change_invocation_behavior`. |  | Existing apps keep their root flags, command tree, and JSON `version` behavior; validation is non-mutating and explicit. |
| VAL-005 | Documentation | Document the explicit downstream pytest/CI integration and non-automatic behavior. | SUCCESS | feature_implementation | Gate 5 | `/root` | `README.md`; README example executed by `.venv/bin/python -m pytest tests/test_readme_examples.py -q` -> `0`. |  | Documents config, fail/warn modes, report serialization, and opt-in behavior. |
| REL-001 | Release | Publish backward-compatible minor release `2.2.0`: PR, checks, merge, annotated tag, build, and package upload. | IN_PROGRESS | feature_implementation | Gate 5 | `/root` | Latest tag/release is `2.1.1`; repository uses unprefixed annotated numeric tags. |  |  |
