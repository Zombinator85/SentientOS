# Publishing Guide

This document describes how to publish a new release of SentientOS.

## Cut a release candidate

1. Bump `__version__` in `sentientos/__init__.py`.
2. Tag the commit using a version with `-rc`, e.g. `v0.4.2-rc1`.
3. Push the tag and wait for CI.
4. CI will upload the wheel to TestPyPI using `TEST_PYPI_API_TOKEN`.

## Final release

1. Ensure the tag has no `-rc` suffix, e.g. `v0.4.2`.
2. CI uploads to real PyPI using `PYPI_API_TOKEN` and pushes the Docker image to GHCR.
3. Confirm the GPG-signed tag appears on GitHub.

To dry run a release candidate locally:

```bash
python -m build
TWINE_USERNAME=__token__ TWINE_PASSWORD=$TEST_PYPI_API_TOKEN twine upload --repository testpypi --skip-existing dist/*
```
