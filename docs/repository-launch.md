# Repository launch and discoverability plan

## Repository metadata

**Repository name:** `pydistpilot`

**Suggested owner:** `muhammadsaeed-ai` (confirm the publishing account before creation)

**Visibility:** Public

**Description:**

> Python package release verification CLI: build and inspect wheels and sdists, rebuild from source distributions, and smoke-test installed artifacts locally and in CI.

GitHub recommends a clear README and lets repository maintainers classify a repository with relevant topics. The metadata file uses the current 20-topic limit documented by GitHub. Topics are for classification and discovery, not a guarantee of traffic or ranking.

## Topics (20)

`python`, `python-packaging`, `pypi`, `python-package`, `packaging`, `wheel`, `sdist`, `release-engineering`, `continuous-integration`, `ci-cd`, `devtools`, `developer-tools`, `open-source`, `testing`, `software-quality`, `software-supply-chain`, `package-validation`, `github-actions`, `command-line-tool`, `python-cli`

## Keyword strategy

Lead with the exact workflow this tool implements: Python package verification, wheel and sdist validation, installed-package smoke testing, source-distribution rebuild, release artifact inspection, and CI/CD packaging checks. Mention Python build, pytest, GitHub Actions, wheel metadata, and PyPI only where the documentation accurately explains integration or limits.

Do not claim that PyDistPilot guarantees releases, provides malware/provenance scanning, replaces Twine or existing packaging Actions, or has been published on PyPI. Do not add irrelevant trending tags, keyword repetitions, fabricated badges, benchmark claims, or adoption claims.

## Before public release

- [ ] Confirm the correct GitHub owner and create `pydistpilot` as a public repository.
- [ ] Push the complete source tree and ensure `README.md` renders local SVG diagrams.
- [ ] Add the 20 topics from `repository-metadata.json` and the description above.
- [ ] Verify GitHub Actions on supported Python versions and operating systems.
- [ ] Run lint, type checking, package metadata checks, and dependency auditing in an online environment.
- [ ] Review GitHub's security alerts and enable Dependabot alerts where available.
- [ ] Resolve failures and update `docs/verification-report.md` with actual logs/results.
- [ ] Publish to PyPI only after checking package-name ownership, credentials, provenance/publishing configuration, and release checklist.
- [ ] Tag `v0.2.0` only when release gates are met; otherwise label the upload as an alpha preview.

## Public release announcement draft

**PyDistPilot 0.2.0 — test the distribution, not just the checkout.**

PyDistPilot is a local-first Python CLI for checking what users actually install. It builds a wheel and source distribution, inspects archive paths and metadata, rebuilds a wheel from the sdist, then installs candidate wheels into fresh virtual environments to smoke-test imports and console-script help. It produces actionable terminal findings and JSON reports, runs without a paid API, and keeps dependency installation opt-in.

It is an early-stage tool and complements the Python packaging ecosystem rather than replacing it. Contributions, real-project test cases, and maintainers' feedback are welcome.
