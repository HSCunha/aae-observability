# Publishing aae-observability

## One-time prerequisites

1. Confirm that `aae-observability` is available on PyPI and TestPyPI.
2. Complete legal and open-source approval for the MIT license and public release.
3. Replace generic author metadata and add verified public repository, documentation,
   issue tracker, and changelog URLs in `pyproject.toml`.
4. Create PyPI and TestPyPI accounts, enable two-factor authentication, and establish
   at least two project owners where organizational policy permits.
5. Create GitHub environments named `testpypi` and `pypi`. Require reviewer approval
   for the `pypi` environment.
6. Configure PyPI and TestPyPI Trusted Publishers for the repository, workflow file
   `.github/workflows/publish.yml`, and the corresponding environment name.
7. Protect release tags and the default branch. Restrict changes to the publishing workflow.

## Release candidate flow

1. Run CI on Python 3.10, 3.11, and 3.12.
2. Run the `Publish Python distribution` workflow manually with target `testpypi`.
3. Install from TestPyPI in a new environment. Dependencies may be resolved from PyPI:

```bash
python -m venv .venv-testpypi
. .venv-testpypi/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  aae-observability==0.6.3
python -c "import aae_observability; print(aae_observability.__version__)"
aae-observability version
```

4. Verify the TestPyPI project page, README rendering, metadata, license, files, hashes,
   provenance attestations, imports, CLI, and a minimal instrumented call.
5. Record approval in the release ticket.

## Production publication

```bash
git tag -s v0.6.3 -m "aae-observability 0.6.3"
git push origin v0.6.3
```

The tag triggers the production job. The `pypi` environment must require manual approval.
Do not rebuild artifacts during publication. The publish job downloads the wheel and sdist
created by the build job and uses PyPI Trusted Publishing.

## Post-publication verification

```bash
python -m venv .venv-pypi
. .venv-pypi/bin/activate
python -m pip install --upgrade pip
python -m pip install aae-observability==0.6.3
python -c "import aae_observability; print(aae_observability.__version__)"
aae-observability version
```

Then create the GitHub release from tag `v0.6.3`, attach the changelog, compare artifact
hashes with CI, verify PyPI provenance, and monitor installation and vulnerability reports.
A defective immutable release must be yanked and replaced by a new patch version.
