# Ecosystem research and product-selection record

**Research date:** 19 October 2026  
**Status:** Historical opportunity-selection record from the 0.1.0 candidate. The 0.2.0 reporting features are engineering additions, not evidence of market validation.

## Executive decision

Build **PyDistPilot**, a local-first, artifact-first Python release verifier. Its narrow promise is to reduce the gap between testing code in a checkout and testing the wheel or sdist users will install. It combines a built wheel audit, a built source-distribution audit, a second wheel build from the sdist, isolated installs, import-origin probes, and console-script help smoke checks in one repeatable CLI run.

This selection is intentionally modest about novelty. Individual parts already exist. The product hypothesis is that an integrated local command, with sensible offline defaults and automatic smoke probes, lowers friction enough to be useful beside established packaging and CI tooling. That hypothesis needs maintainers' feedback and real-world trial usage before it can be called validated.

## Research method and confidence

The review used current official documentation, GitHub repository pages, PyPI project descriptions, and ecosystem guidance. Links below are primary sources whenever possible. The sources establish documented capabilities and the existence of common workflows; they do **not** establish exact market size, downloads, willingness to pay, or adoption forecasts. Repository star counts were not used as the selection criterion.

Labels used here:

- **Verified fact:** directly described in a linked primary source.
- **Inference:** a reasoned product conclusion from those facts.
- **Hypothesis:** needs field validation with Python maintainers.

## Problem evidence

### The installed artifact is a separate thing from the source checkout

- The Python Packaging User Guide explains the lifecycle from source project to built wheel/sdist and user installation. Wheels contain files needed by the installed environment, which is different from importing source files from the repository: [Packaging Flow](https://packaging.python.org/en/latest/flow/). **Verified fact.**
- Hynek Schlawack's [build-and-inspect-python-package](https://github.com/hynek/build-and-inspect-python-package) builds wheel and sdist distributions, checks wheel contents, emits packaging metadata, and uploads artifacts in GitHub Actions. Its documentation explicitly recommends testing against the built wheel rather than the source tree for higher fidelity. **Verified fact.**
- [OpenAstronomy/build-python-dist](https://github.com/OpenAstronomy/build-python-dist) can build source distributions and run a configured test command against the installed package from a temporary directory. **Verified fact.**
- [check-wheel-contents](https://github.com/jwodder/check-wheel-contents) checks archive file paths and common wheel-content mistakes; its documentation notes that path checks do not examine file contents. [Pyroma](https://github.com/regebro/pyroma) checks package-friendliness/metadata. [Twine](https://twine.readthedocs.io/en/stable/) validates package metadata/readme rendering and uploads distributions. **Verified fact.**
- Supply-chain guidance highlights that a published artifact can differ from the repository source, and recommends inspecting the actual sdist/wheel and using provenance evidence where available: [PyPI Security Best Practices](https://github.com/lirantal/pypi-security-best-practices). **Verified guidance.**

**Inference:** the space is served by several mature building blocks and CI recipes. A new linter that repeats metadata or file-content checks would be weak. The product should orchestrate *artifact behavior checks* locally, while remaining complementary to these tools.

### Adjacent opportunities and why they were not selected

- **Flaky-test replay/triage:** [pytest's flaky-test guide](https://pytest.org/en/latest/explanation/flaky.html) documents isolation, state, and rerun challenges; [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), [pytest-replay](https://github.com/ESSS/pytest-replay), and [pytest-rerunfailures](https://github.com/pytest-dev/pytest-rerunfailures) already cover seeds, replay ordering, and retries. The newer [pyrept](https://pypi.org/project/pyrept/) compares test reports across runs and tracks flaky tests. **Decision:** not another test-result comparator or rerunner.
- **Command/environment capture and diff:** [Capsula](https://github.com/ut-issl/capsula) captures execution metadata and output; `pyrept` already compares test history. **Decision:** the original EnvProof/environment-capsule idea was rejected after competitor review; `EnvProof` is also already a PyPI project ([PyPI page](https://pypi.org/project/envproof/)).
- **Free-threaded CPython readiness:** [CPython free-threading documentation](https://docs.python.org/3/howto/free-threading-python.html) describes extension compatibility and GIL behavior. Current tools include [ftready](https://pypi.org/project/ftready/), [ft-readiness](https://pypi.org/project/ft-readiness/), and [Threadcheck](https://pypi.org/project/threadcheck/). **Decision:** important and emerging, but existing tooling covers a large portion of the obvious readiness/race-analysis gap, and robust race analysis is significantly harder to validate.
- **Autonomous AI debugging:** the [Stack Overflow 2025 AI survey](https://survey.stackoverflow.co/2025/ai) reports mixed agent adoption and frustration with inaccurate AI outputs. **Decision:** not selected because core correctness would be difficult to prove, and an online/LLM dependency would weaken the local-first value.
- **Generic Python security/package auditor:** the ecosystem already has static analysis, dependency audit, artifact/signature/provenance, and package-content tools. **Decision:** do not build a broad duplicate of Bandit/Ruff/pip-audit/Sigstore.

## Final shortlisted concepts and scores

Scoring is a structured judgment, not a survey. Ten dimensions are scored 1–5, with 5 always favorable. For “Security and maintenance risk,” 5 means the risk is relatively manageable. The weighted score is `sum(score × weight) / 5`, reported out of 100.

| Dimension | Weight |
|---|---:|
| Problem severity and frequency | 15% |
| Potential audience | 10% |
| Evidence of demand | 15% |
| Differentiation relative to incumbents | 15% |
| Technical feasibility | 10% |
| Python ecosystem fit | 5% |
| Innovation/usefulness | 10% |
| Adoption ease | 5% |
| Security and maintenance risk (higher is more manageable) | 5% |
| Community-growth potential | 10% |

| Concept | Severity | Audience | Demand evidence | Differentiation | Feasibility | Python fit | Usefulness | Adoption | Risk manageability | Community | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **PyDistPilot: artifact-first release verification** | 4 | 4 | 4 | 3 | 5 | 5 | 4 | 4 | 4 | 4 | **80/100** |
| Cross-run environment drift diagnostics | 4 | 4 | 4 | 2 | 4 | 5 | 3 | 3 | 4 | 3 | 70/100 |
| Free-threading readiness/race assurance | 4 | 3 | 4 | 2 | 3 | 5 | 4 | 3 | 3 | 3 | 67/100 |
| Autonomous AI debugging agent | 4 | 5 | 4 | 2 | 3 | 4 | 4 | 3 | 2 | 4 | 71/100 |
| Generic local package/security auditor | 4 | 4 | 5 | 1 | 4 | 5 | 3 | 5 | 3 | 3 | 71/100 |

The score does not mean PyDistPilot has the largest possible audience or strongest absolute novelty. It wins this shortlist because its initial version is feasible, measurable, useful without a service, and easy to verify through artifacts that deliberately fail if packaging is broken.

## Competitor comparison

| Tool or approach | Existing strength | Remaining PyDistPilot role |
|---|---|---|
| `build` / PEP 517 build backend | Builds distributions using the project's backend | Orchestrates the complete local verification run and captures the outcomes |
| `check-wheel-contents` | Detects known mistakes in wheel file layout/content | Adds runtime import and entry-point smoke checks after installation |
| `pyroma` | Reviews metadata/package friendliness | Tests the built artifact's behavior rather than rating metadata alone |
| `twine check` | Validates package metadata and README rendering | Complements metadata checks with installation probes |
| `build-and-inspect-python-package` GitHub Action | Strong CI integration, builds/inspects artifacts and suggests testing installed wheels | Local CLI, automatic import/console-script smoke tests, sdist-to-wheel rebuild, JSON report; users may still prefer the Action |
| `OpenAstronomy/build-python-dist` | Builds sdist and can run a user-configured test command in a temporary directory | Adds standard automatic probes, wheel/sdist static audit, and a portable report without requiring an Actions workflow |
| `tox` / `nox` | Flexible automation and environment matrices | Smaller targeted artifact smoke workflow; not a replacement for a full test matrix |
| Sigstore/provenance verification | Verifies signatures/attestations and source/workflow identity under its trust model | Does not claim provenance; should be used alongside provenance checks when required |

**Closest competitor:** `build-and-inspect-python-package` plus tests run against built artifacts. That is real overlap and a credible substitute. PyDistPilot's proposed advantage is a developer-invoked command with a focused end-to-end default flow, automatic import/CLI probes, and offline-first behavior—not a claim that existing CI approaches cannot do the job.

## Proposed user and use cases

Primary users are Python library maintainers publishing packages to PyPI, internal package registries, or release artifact stores. Secondary users are CI maintainers who need machine-readable release gates.

1. Before tagging a release, build both wheel and sdist, verify their metadata, then run smoke checks against a fresh wheel install.
2. Confirm the sdist can independently build a wheel and that this wheel also installs/imports.
3. Diagnose missing packages, bad console entry points, broken wheel RECORD hashes, archive path anomalies, and local-source shadowing.
4. Run static inspection on an existing artifact without executing it.

## Value proposition and boundaries

**Value proposition:** “A one-command, local release check that tests the package you are about to ship, not only the source directory you developed in.”

The first release does not promise malware detection, API compatibility, proof of reproducibility, complete functional correctness, cross-platform support, signed provenance, or automatic dependency vulnerability detection.

## Validation still needed

These are hypotheses, not facts:

- Maintainers value one local command enough to add it to their release workflow.
- Automatic import and `--help` checks detect a useful share of avoidable packaging regressions.
- Offline-first defaults are desirable in CI and restricted networks.
- JSON findings are sufficient for CI integration without building a dedicated service.

Before targeting a 1.0 release, test on several real packages (pure Python and packages with extensions), collect consented maintainer feedback, compare the detection overlap with current Actions workflows, and review false positives from import discovery and `--help` checks.

## Source index

1. [Python Packaging User Guide — The Packaging Flow](https://packaging.python.org/en/latest/flow/)
2. [Hynek Schlawack — build-and-inspect-python-package](https://github.com/hynek/build-and-inspect-python-package)
3. [OpenAstronomy — build-python-dist](https://github.com/OpenAstronomy/build-python-dist)
4. [check-wheel-contents](https://github.com/jwodder/check-wheel-contents)
5. [Pyroma](https://github.com/regebro/pyroma)
6. [Twine documentation](https://twine.readthedocs.io/en/stable/)
7. [PyPI security best practices](https://github.com/lirantal/pypi-security-best-practices)
8. [pytest flaky tests documentation](https://pytest.org/en/latest/explanation/flaky.html)
9. [pytest-randomly](https://github.com/pytest-dev/pytest-randomly), [pytest-replay](https://github.com/ESSS/pytest-replay), [pytest-rerunfailures](https://github.com/pytest-dev/pytest-rerunfailures)
10. [pyrept on PyPI](https://pypi.org/project/pyrept/), [Capsula on GitHub](https://github.com/ut-issl/capsula), [EnvProof on PyPI](https://pypi.org/project/envproof/)
11. [CPython free-threading guide](https://docs.python.org/3/howto/free-threading-python.html), [ftready](https://pypi.org/project/ftready/), [ft-readiness](https://pypi.org/project/ft-readiness/), [Threadcheck](https://pypi.org/project/threadcheck/)
12. [Stack Overflow Developer Survey 2025 — AI](https://survey.stackoverflow.co/2025/ai)
13. [Sigstore Python](https://github.com/sigstore/sigstore-python)
