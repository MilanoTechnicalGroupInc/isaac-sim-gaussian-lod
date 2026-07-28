# Contributing

Thank you for contributing to Isaac Sim Gaussian LOD. The project maintainer
and code owner is [@eaturkgeldi-mtg](https://github.com/eaturkgeldi-mtg).

## Development setup

Use Python 3.10, 3.11, or 3.12:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest
python -m build
```

Runtime or extension changes should also be validated in Isaac Sim 6.0.1.
Avoid committing generated PLY, USDC, USDZ, benchmark, or package output.

## Pull requests

Keep each pull request focused, explain the motivation and user impact, and
include tests for changed behavior. All required checks must pass. Report
security vulnerabilities through the private process in `SECURITY.md`.

Configuration files can select output directories and external converter
commands. Treat configuration as trusted executable input and review changes
to these fields carefully.

By submitting a contribution, you represent that you have the right to submit
it and agree that it is licensed under the Apache License 2.0.
