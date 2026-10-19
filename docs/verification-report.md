# PyDistPilot 0.2.0 — local verification report

**Run date:** 19 October 2026  
**Environment:** Linux, CPython 3.13.5, isolated test virtual environment, network unavailable.  
**Scope:** Local build and runtime verification only. No hosted GitHub Actions run or PyPI publication has occurred.

## Summary

The expanded 0.2.0 code and the installed wheel were exercised locally. Unit/integration tests passed, both distributions were built, the wheel installed from a clean virtual environment, static inspection completed, the sample and self-project verification runs passed, SARIF JSON parsed, and the comparison CLI correctly failed on a deliberately synthetic newly introduced warning. The publish workflow is prepared but has not executed against a public repository or a configured PyPI Trusted Publisher.

## Executed checks

| Check | Result | Evidence / scope |
|---|---|---|
| Unit and integration tests | **PASS** | `python -m pytest -q`: 52 passed on CPython 3.13.5. |
| Python bytecode compilation | **PASS** | `python -m compileall -q src tests`. |
| Distribution build | **PASS** | `uv build --offline --no-build-isolation --out-dir dist` created `pydistpilot-0.2.0.tar.gz` and `pydistpilot-0.2.0-py3-none-any.whl`; the build frontend also rebuilt a wheel from the sdist as part of its process. |
| Clean wheel install | **PASS** | Installed the newly built wheel into a new CPython 3.13.5 virtual environment with `pip install --no-deps`; isolated CLI reported `pydistpilot 0.2.0`, and `--help` succeeded. |
| Sample end-to-end verification | **PASS** | Installed CLI ran `verify` against `examples/sample_project`: 3 artifacts, 8 smoke checks, zero errors, zero warnings, zero failed smoke checks. JSON and SARIF outputs parsed. |
| Self-project artifact verification | **PASS** | Installed CLI ran `verify` against the current source project: 3 artifacts, 6 smoke checks, zero errors, zero warnings, zero failed smoke checks. This is still one environment, not the cross-platform matrix. |
| Static inspection of release artifacts | **PASS** | Installed CLI inspected the current wheel and sdist; 2 artifacts, zero errors, zero warnings. It did not install or execute those two artifacts during the inspect command. |
| SARIF format smoke checks | **PASS (structural)** | Verification, inspection, and comparison SARIF JSON parsed, used `version: 2.1.0`, and contained the expected run/driver/result structures. No external SARIF schema validator or hosted code-scanning ingestion was available. |
| Regression-gate end-to-end example | **PASS** | A deliberately synthetic warning was added to a copy of a passing local report. `compare` returned exit code 1, emitted JSON with one new issue, and emitted SARIF with rule ID `PD-DEMO-REGRESSION`. This tests gate mechanics only; the warning is not a real package defect. |
| Invalid/malformed report handling | **PASS** | Tests cover unsupported schemas, unhashable status values, malformed nested findings, invalid JSON, output-path collision, and a report larger than the 16 MiB limit. |
| SVG, repository JSON, and YAML local parsing | **PASS (local parse only)** | Final pass validates SVG/XML, relevant JSON assets, and GitHub workflow YAML syntax; all 40-character action references are full commit SHAs. Parsing does not prove GitHub's expressions, action permissions, or hosted execution. |
| Relative README link check | **PASS (local path check)** | Local Markdown links and visual asset paths point to files in the source tree. A hosted renderer was not tested. |

## Quality and security gates not run

| Gate | Status | Reason |
|---|---|---|
| Ruff lint | **NOT RUN** | Ruff is not in the offline cache and package indexes are unreachable in this environment. |
| mypy strict type-check | **NOT RUN** | mypy could not be installed while offline. |
| `twine check` | **NOT RUN** | Twine could not be installed while offline. Metadata and artifact contents were inspected locally, but that is not a substitute for Twine. |
| `pip-audit` | **NOT RUN** | Tool and advisory data were unavailable; dependencies are not claimed to be vulnerability-audited. |
| Python 3.10–3.14 matrix | **NOT RUN LOCALLY** | Only CPython 3.13.5 ran here. CI is configured to test the declared version matrix, but no hosted results exist. |
| Ubuntu, Windows, macOS matrix | **NOT RUN LOCALLY** | Only one Linux execution environment was available. |
| GitHub Actions CI and publish workflow | **NOT RUN** | The remote repository is not created or pushed by this process. |
| PyPI name reservation / Trusted Publisher setup / publication | **NOT VERIFIED / NOT PUBLISHED** | Maintainer must verify package-name availability, configure PyPI Trusted Publishing, push the source, run hosted CI, and then deliberately tag a release. |

## Interpretation and next release gate

The evidence supports a local alpha candidate on CPython 3.13.5. It does **not** establish cross-platform compatibility, strict typing/lint cleanliness, vulnerability-audit cleanliness, validity of the whole GitHub workflow under hosted execution, popularity, or correctness on arbitrary projects. Tests and package building must not be represented as substitutes for the gates above.

Before public release, push the current source tree to the intended public repository, run all jobs, fix issues without weakening checks, confirm `twine check` and `pip-audit`, review generated reports for source-derived sensitive messages, configure the exact PyPI Trusted Publisher, and verify the workflow only publishes distributions built by the protected build job. See [release checklist](release.md) and [Trusted Publishing setup](publishing.md).
