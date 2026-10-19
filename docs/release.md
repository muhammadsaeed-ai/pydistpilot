# 0.2.0 release preparation

## Release state

**Candidate version:** `0.2.0` alpha. The repository bundle can be built and tested locally; this document does not claim that hosted CI passed or that PyPI publication occurred.

**Remote state:** a maintainer must create the public repository and push this source. Confirm repository ownership and URLs before using the publish workflow.

## Before tagging

- [ ] Confirm the intended GitHub owner/repository and check PyPI project-name availability, trademarks, and any existing distribution with the same name.
- [ ] Confirm the `Homepage`, `Repository`, and `Issues` URLs in `pyproject.toml` match the actual remote.
- [ ] Run the complete GitHub Actions matrix on Python 3.10–3.14 and Ubuntu, Windows, and macOS. Do not claim a platform passes without a green job.
- [ ] Verify `ruff check src tests`, `mypy src/pydistpilot`, `python -m build`, `python -m twine check dist/*`, and `pip-audit`.
- [ ] From a fresh virtual environment, install the wheel and run `pydistpilot --version`, `pydistpilot inspect`, `pydistpilot verify` on the sample, and `pydistpilot compare` with both clean and regression cases.
- [ ] Confirm the SARIF output parses as SARIF 2.1.0 and that it contains no absolute host paths or secrets.
- [ ] Review baseline report semantics and test both default regression gating and `--fail-on-current-failure` in the target CI system.
- [ ] Review all generated reports; redaction is best-effort and reports can still contain local paths or project-derived messages.
- [ ] Configure a PyPI Trusted Publisher for the exact GitHub owner, repository, workflow filename `.github/workflows/publish.yml`, and GitHub environment `pypi` before pushing a release tag. No long-lived PyPI token is embedded in this workflow.
- [ ] Only after all release gates pass, create a signed/tagged release `v0.2.0` and watch the build and publish jobs to completion.

## Draft release announcement

**PyDistPilot 0.2.0 — Test the distribution, not just the checkout**

PyDistPilot builds and inspects Python wheel/source-distribution artifacts, rebuilds from an sdist, and smoke-tests installed wheels in fresh virtual environments. Version 0.2.0 adds SARIF 2.1.0 export and report-baseline comparison, allowing teams to review findings in compatible code-scanning systems and make CI fail on newly introduced packaging regressions.

The trust boundary remains explicit: static `inspect` does not install or execute the archive. `verify` invokes the project's build backend and imports package code, so run it only on source you trust. Network-enabled dependency installation and isolated build resolution are explicit opt-ins.

This remains an alpha and complements the packaging toolchain rather than replacing application tests, provenance, signatures, vulnerability scanning, or a full compatibility matrix. Real-project validation and cross-platform CI evidence are the most valuable early contributions.

## Release demo (90–120 seconds)

1. Show a package whose unit tests pass in the checkout.
2. Run `pydistpilot verify . --report baseline.json --sarif baseline.sarif` and explain the generated wheel, sdist, sdist-rebuilt wheel, fresh venv, and imports/entrypoint smoke checks.
3. Modify a packaging rule in a temporary branch or fixture to introduce a real finding, generate a candidate report, and run `pydistpilot compare baseline.json candidate.json --json regressions.json --sarif regressions.sarif`.
4. Show the new finding and nonzero exit code. Then repair the fixture and show the resolved issue.
5. Explain the difference between static `inspect`, executable `verify`, and baseline-aware CI policy. Do not present a smoke test as a full correctness or security proof.

## Initial post-release backlog

1. Add project-configurable baseline severity policy and documented exceptions, while retaining explicit user review of accepted baselines.
2. Add more real-package fixtures for namespace packages, typed packages, data files, extensions, and unusual console scripts.
3. Support an optional local wheelhouse for reproducible offline dependency probes.
4. Improve namespace-package import target discovery only when evidence is unambiguous.
5. Consider cross-interpreter verification when multiple interpreters are installed, reporting actual selected interpreter versions.
6. Explore integration with PyPI attestations and provenance policy without overstating what functional checks prove.

