# `cli-core-yo` Activation Validation and Conformance Contract

## Summary
- Keep repo `activate` scripts repo-owned. `cli-core-yo` does not generate, inject, or own the first activation step.
- Add framework-owned activation validation inside the existing runtime validation pipeline, not inside `EnvSpec`.
- Use a marker-based contract: each repo `activate` script exports one repo-specific marker env var, and `cli-core-yo` validates marker + env state before command execution.
- Default behavior remains strict for commands that keep `runtime_guard="required"`. Commands that should warn and proceed must be explicitly marked `runtime_guard="advisory"` downstream.
- Add a new root flag `--ignore-strict-checks` that still runs runtime checks but downgrades strict runtime failures to warnings. Keep `--skip-runtime-check` as the full bypass that skips evaluation entirely.

## Public API and Behavior Changes
- Add `ActivationValidationSpec` under `RuntimeSpec`, with one required field in v1:
  - `marker_env_var: str`
- Keep using existing `EnvSpec.active_env_var` and `EnvSpec.project_root_env_var`; activation validation requires `CliSpec.env` to be present.
- Add root flag `--ignore-strict-checks` whenever `spec.runtime` is configured.
  - `--ignore-strict-checks`: run runtime validation, emit warnings/report output, but do not block on failures that would otherwise be enforced.
  - `--skip-runtime-check`: skip all runtime validation entirely.
  - If both are passed, `--skip-runtime-check` wins because no checks are executed.
- Activation validation contributes prereq-like result entries into the existing runtime report payload so `runtime status`, `runtime check`, `runtime explain`, and pre-execution failure/warning output all show the same activation findings.
- No change to `EnvSpec` semantics: `env activate` and `env deactivate` remain guidance-only commands.

## Validation Contract
- Add a framework activation validator that runs during pre-execution runtime validation and emits stable result keys for:
  - active-env-var present
  - project-root-env-var present
  - marker env var present
  - marker value equals the project-root env var value
  - selected backend is actually active
  - interpreter binding is consistent with the active backend when the backend is `conda` or `venv`
- Marker contract:
  - each repo `activate` script exports the configured `marker_env_var`
  - marker value must be the same absolute path string exported in `project_root_env_var`
  - this is an accidental-bypass detector, not a security boundary
- Guard behavior:
  - keep `RuntimeSpec.guard_mode="enforced"` as the framework default
  - downstream repos mark low-risk/read-only commands `runtime_guard="advisory"` when activation failure should warn and proceed
  - risky commands keep `runtime_guard="required"` and therefore fail on activation-validation failure unless `--ignore-strict-checks` is present
- No framework auto-upgrade based on `mutates_state`. Risk remains an explicit command-policy decision.

## Testing and Downstream Contract
- `cli-core-yo` unit-tests the validator itself for:
  - valid activated env
  - missing marker
  - missing active env var
  - missing project root env var
  - marker/project-root mismatch
  - backend inactive
  - interpreter/backend mismatch
  - `required` vs `advisory`
  - `--ignore-strict-checks` vs `--skip-runtime-check`
- Extend `cli_core_yo.conformance` with downstream helpers that run shell-level activate contract tests without taking over activate implementation. Provide:
  - a shell harness that sources a repo `activate` script and captures env delta, stdout/stderr, and exit status
  - assertion helpers that verify the framework activation contract from that captured shell state
- Downstream repo migration:
  - each repo `activate` script exports the new marker env var alongside its existing active/project-root env vars
  - each repo adds bash and zsh contract tests using the framework conformance helpers
  - each repo updates command policies so low-risk commands are `advisory` and risky commands remain `required`

## Assumptions and Defaults
- The new marker env var name is repo-specific and configured in `ActivationValidationSpec`; the framework does not hardcode one global marker name.
- Marker value is the project-root path, not just `1`, so the framework can validate coherence instead of mere presence.
- Activation validation is local and deterministic only; it is intended to catch accidental bypass and stale shells, not to prevent deliberate local circumvention.
- No framework-owned activate script generation, templating, or shell injection is included in this change.
