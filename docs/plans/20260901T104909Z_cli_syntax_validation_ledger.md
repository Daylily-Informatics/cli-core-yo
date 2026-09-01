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
| REL-001 | Release | Publish backward-compatible minor release `2.2.0`: PR, checks, merge, annotated tag, build, GitHub release, and package upload. | SUCCESS | feature_implementation | Gate 5 | `/root` | PR [#11](https://github.com/Daylily-Informatics/cli-core-yo/pull/11) merged cleanly at `4c994ef28c469a193f0071252d90293c88fdb601`; annotated tag `2.2.0` points to that exact commit; build, Twine check, fresh-wheel validation, `twup`, the PyPI JSON API, and the [GitHub release](https://github.com/Daylily-Informatics/cli-core-yo/releases/tag/2.2.0) all succeeded. |  | Published [cli-core-yo 2.2.0](https://pypi.org/project/cli-core-yo/2.2.0/); the GitHub release was created from the existing immutable tag, and issue #10 closed with the release receipt. |
| AMD-001 | Release control | Record the explicit direction to add a GitHub release record after publication, without moving the already-published tag or rebuilding artifacts. | SUCCESS | plan_amendment | Gate 5 | `/root` | [GitHub release 2.2.0](https://github.com/Daylily-Informatics/cli-core-yo/releases/tag/2.2.0), published `2026-09-01T11:07:16Z`; `git cat-file -t 2.2.0` -> `tag`; `2.2.0^{}` -> `4c994ef28c469a193f0071252d90293c88fdb601`. |  | The release object references the existing annotated tag; package artifacts already present in `dist/` remain the verified 2.2.0 artifacts. |

## Final Report

All rows terminal: **yes**

Objective complete: **yes**

Status counts:

- SUCCESS: 7
- DUPLICATE: 0
- NO_LONGER_NEEDED: 0
- FAIL: 0
- BLOCKED: 0

Changed files:

- `cli-core-yo`: `cli_core_yo/validation.py`, `cli_core_yo/app.py`, `cli_core_yo/registry.py`, `tests/test_validation.py`, `tests/test_registry.py`, `README.md`, and this ledger.

Validation:

- `.venv/bin/python -m pytest -q` -> exit `0`.
- `.venv/bin/python -m ruff check cli_core_yo tests --exclude cli_core_yo/_version.py` -> pass.
- `.venv/bin/python -m ruff format --check cli_core_yo/validation.py cli_core_yo/registry.py tests/test_validation.py tests/test_registry.py` -> pass.
- `.venv/bin/python -m mypy cli_core_yo --ignore-missing-imports` -> `Success: no issues found in 16 source files`.
- `python -m build` -> `cli_core_yo-2.2.0.tar.gz` and `cli_core_yo-2.2.0-py3-none-any.whl` built.
- `.venv/bin/python -m twine check ...` -> both artifacts passed.
- Fresh temporary virtual environment installed the wheel and passed an explicit `validate_cli()` smoke check.
- `twup` uploaded both artifacts; the PyPI JSON API returned version `2.2.0` with matching SHA-256 checksums.
- The GitHub release record was created from the existing annotated `2.2.0` tag; its release target reports the repository default branch (`jemdev10`), while the immutable tag itself resolves to the merged release commit `4c994ef28c469a193f0071252d90293c88fdb601`.

Non-success terminal rows:

- None.

Residual risks:

- The repository-wide `ruff format --check cli_core_yo tests` still reports five untouched, pre-existing formatting differences, and the ignored generated `cli_core_yo/_version.py` lacks a trailing newline. The changed Python files pass their scoped formatting check; no unrelated formatting churn was added to this release.
