# How To Add README Tests

This repo validates executable README examples with `pytest` and `mktestdocs`.

## Current Pattern

- The executable-doc test lives in `tests/test_readme_examples.py`.
- It runs `mktestdocs.check_md_file(Path("README.md"), lang="python", memory=True)`.
- `memory=True` matters because later Python blocks in the README reuse names defined earlier, such as `SPEC`.
- The test pins `sys.argv` to a simple script-like value and redirects XDG directories into `tmp_path` so README examples run predictably under `pytest`.
- The test allows `SystemExit(0)` because the quick-start example uses `raise SystemExit(run(SPEC))`.

## What Counts As Executable

- `python` fences are part of the executable contract.
- `console` fences are documentation-only in this repo.
- Use `console` instead of `bash` for install, bootstrap, build, or other heavy shell commands that should not be executed during tests.
- `toml` fences are documentation-only unless a future test explicitly validates them.

## Adding A New README Example

When adding a new snippet to `README.md`:

1. Use a `python` fence only if the example should stay runnable under automated tests.
2. Keep the snippet self-contained, or place it after any earlier `python` blocks it depends on.
3. Avoid examples that mutate the developer environment or rely on external services.
4. For shell instructions, prefer `console` unless the command is intentionally safe and lightweight enough to become part of the executable test contract.

## Updating The Harness

Touch `tests/test_readme_examples.py` if a new README example needs stable test setup.

Typical reasons:

- the example depends on specific environment variables
- the example needs a temp directory
- the example intentionally exits with `SystemExit(0)`

If you need to extend the harness, keep it narrow and repo-specific. Do not turn it into a generic docs framework in this repo.

## Running The Checks

Run the README example test only:

```console
.venv/bin/python -m pytest tests/test_readme_examples.py -q
```

Run the related app regression and the README example test together:

```console
.venv/bin/python -m pytest tests/test_app.py tests/test_readme_examples.py -q
```

Run the full suite:

```console
.venv/bin/python -m pytest -q
```
