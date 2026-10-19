# PyDistPilot

![PyDistPilot banner](assets/pydistpilot-banner.svg)

**Test the distribution, not just the checkout.**

PyDistPilot is a local-first Python package release-verification CLI. It builds a wheel and source distribution, statically inspects package metadata and archive paths, rebuilds a wheel from the source distribution, installs built wheels into fresh virtual environments, and runs configurable import and console-script smoke checks. Version 0.2 adds baseline regression comparison and SARIF 2.1.0 export.

> **Status:** early-stage alpha release candidate. This is a verification aid, not a release guarantee. Hosted CI, full cross-platform testing, and several external quality gates still need to run before a stable release.

[![CI](https://github.com/muhammadsaeed-ai/pydistpilot/actions/workflows/ci.yml/badge.svg)](https://github.com/muhammadsaeed-ai/pydistpilot/actions/workflows/ci.yml) [![Python](https://img.shields.io/badge/python-3.10%E2%80%933.14-blue.svg)](https://www.python.org/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why PyDistPilot?

A green test run from a source checkout does not prove the wheel or source distribution consumers install is usable. PyDistPilot verifies the built artifacts: it inspects archives, checks wheel `RECORD` hashes, rebuilds a wheel from the sdist, and smoke-tests installed packages in isolated virtual environments.

It complements `pytest`, `build`, `twine`, `check-wheel-contents`, `tox`/`nox`, and provenance tools. It does not replace them.

## Visual tour

### End-to-end verification pipeline

![Verification workflow](docs/diagrams/workflow.svg)

### Architecture

![System architecture](docs/diagrams/architecture.svg)

### Repository hierarchy

![Repository hierarchy](docs/diagrams/hierarchy.svg)

### Security boundaries

![Security boundaries](docs/diagrams/security-boundaries.svg)

All diagrams are stored in this repository, with editable Mermaid sources and a diagram catalog in `docs/diagrams/`.

## Quick start

Use Python 3.10–3.14. From the repository root, create an isolated environment and install the CLI and build extras:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[build]"
python -m pydistpilot verify examples/sample_project
```

To verify another trusted project:

```bash
pydistpilot verify path/to/python-project
```

Inspect existing artifacts without executing their package code:

```bash
pydistpilot inspect dist/*.whl dist/*.tar.gz
pydistpilot inspect dist/*.whl --json inspection.json
```

Create a report and preserve build artifacts:

```bash
pydistpilot verify . --keep-artifacts ../release-candidate --report ./pydistpilot-report.json
```

## Version 0.2 features

- Build wheel and sdist from a project.
- Static archive and metadata inspection with wheel `RECORD` validation.
- Rebuild a wheel from the source distribution.
- Fresh-environment installed-wheel import and console-script smoke tests.
- Stable finding codes, actionable recommendations, and JSON reports.
- Baseline comparison for new and resolved findings.
- SARIF 2.1.0 export for compatible CI and code-scanning workflows.
- Bounded subprocess output, configurable timeouts, and explicit network/dependency opt-ins.
- GitHub Actions CI and a separately gated publishing workflow.

## Security model

`pydistpilot inspect` parses artifact contents without installing or executing the package. `pydistpilot verify` executes a trusted project's build backend and imports package code and entry points from the built artifacts. `--build-isolation` may download build requirements; `--install-deps` may access package indexes and install dependency code. Neither is enabled by default.

Review JSON reports before sharing them; secret redaction is best-effort, not a guarantee.

## Development

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check src tests
mypy src/pydistpilot
python -m build --no-isolation
python -m twine check dist/*
```

The automated tests and local smoke checks passed in the authoring environment. Ruff, mypy, Twine metadata checks, pip-audit, hosted CI, and the full multi-OS / multi-Python matrix still require independent verification. See [the verification report](docs/verification-report.md).

## Documentation

- [Research report](docs/research-report.md)
- [Product specification](docs/specification.md)
- [Architecture and data flow](docs/architecture.md)
- [Security model](docs/security.md)
- [Reporting, baselines, and SARIF](docs/reporting-and-baselines.md)
- [Release checklist](docs/release.md)
- [Publishing setup](docs/publishing.md)
- [Verification report](docs/verification-report.md)
- [Contribution guide](CONTRIBUTING.md)
- [Security reporting](SECURITY.md)
- [Support](SUPPORT.md)
- [Changelog](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
