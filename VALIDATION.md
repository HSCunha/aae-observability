# Release 0.6.3 Validation

Validated on 2026-08-26.

- Python compilation: passed.
- Ruff lint: passed.
- Ruff formatting check: passed.
- Automated tests: 134 passed, 1 skipped.
- Skipped test: explicitly opt-in live Azure Event Hub integration test.
- Coverage: 90.49%, above the configured 85% threshold.
- `validate-pyproject`: passed.
- Wheel and source distribution build: passed.
- Twine 7 strict metadata and README validation: passed.
- Release artifact content validation: passed.
- Generated wheel: `aae_observability-0.6.3-py3-none-any.whl`.
- Generated sdist: `aae_observability-0.6.3.tar.gz`.

The GitHub CI matrix performs strict MyPy validation and package installation checks on the
supported Python versions. The live Azure Event Hub test remains intentionally opt-in.

## Publication gates still requiring project-owner action

- Confirm the package name in authenticated PyPI and TestPyPI workflows.
- Complete legal and open-source approval for public distribution.
- Add verified public project URLs and non-generic owner/maintainer metadata.
- Configure protected `pypi` and `testpypi` GitHub environments.
- Register matching Trusted Publishers on PyPI and TestPyPI.
- Qualify this exact version on TestPyPI before creating tag `v0.6.3`.
