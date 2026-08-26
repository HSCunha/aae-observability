# Contributing

## Development setup

1. Create and activate a Python 3.10 to 3.12 virtual environment.
2. Run `python -m pip install -e ".[dev]"`.
3. Install hooks with `pre-commit install`.
4. Create a focused branch and add tests with every behavioral change.

## Required local checks

```bash
ruff check .
ruff format --check .
mypy
pytest
validate-pyproject pyproject.toml
python -m build
python -m twine check dist/*
```

## Design expectations

- Preserve the public contracts and semantic-versioning guarantees.
- Keep the core package framework-neutral and put integrations behind adapters.
- Do not block the instrumented call path for telemetry delivery.
- Treat governance errors as fail-closed when enforcement is enabled.
- Never log secrets or captured sensitive content.
- Update `RELEASE.md` for user-visible changes.

## Pull requests

Keep changes small, explain design decisions, list validation performed, and
call out compatibility or security implications.
