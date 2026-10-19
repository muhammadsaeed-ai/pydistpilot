# Product specification

## Identity

- **Name:** PyDistPilot (working name; verify GitHub/PyPI ownership and trademark conflicts before public release).
- **Version:** 0.2.0 alpha.
- **Description:** A local Python CLI that builds, statically audits, and smoke-tests Python distribution artifacts in isolated environments.
- **Target users:** Python library maintainers, release engineers, and CI maintainers.
- **Primary value:** Detect obvious release-artifact failures before a wheel or sdist reaches users.

## User problem

A project's test suite can import files from the checkout, while the release wheel can omit modules, misconfigure console scripts, or carry inconsistent distribution metadata. A source archive can also be incomplete and fail to rebuild. Existing packaging and CI tools cover these parts, but a small library maintainer may need to compose several commands and author custom smoke commands. PyDistPilot provides focused automatic defaults while allowing precise import targets.

## Primary workflow

1. Install PyDistPilot's `build` extra in an isolated developer environment.
2. Run `pydistpilot verify .` before tagging a release.
3. PyDistPilot invokes the project's configured PEP 517 backend without shell expansion and with a per-step timeout.
4. It statically audits the resulting wheel and source archive without extracting them itself.
5. It rebuilds a wheel from the sdist to catch source archives that do not contain enough material to rebuild.
6. It creates fresh virtual environments, installs artifacts offline without resolving dependencies by default, and smoke-tests configured or inferred import roots.
7. It locates declared console scripts and runs each with `--help`.
8. It reports finding codes, evidence, recommended next steps, artifact hashes, elapsed time, and a machine-readable JSON schema.

## Functional requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
|---|---|---|
| F-01 | Build wheel and sdist | For a buildable fixture project, verification records at least one `.whl` and one supported sdist; command failures/timeouts produce a non-zero status and actionable finding. |
| F-02 | Static wheel audit | Valid fixture passes; invalid metadata, unsafe member paths, duplicate members, corrupted ZIP data, and `RECORD` hash/size inconsistencies produce error findings. |
| F-03 | Static sdist audit | Valid supported sdist passes; unsafe paths, special tar members, absent/duplicate `PKG-INFO`, excessive sizes/counts, and malformed archives are flagged. |
| F-04 | Wheel-from-sdist build | A valid sdist is independently used to build a wheel; build failure is a release-blocking error. |
| F-05 | Fresh-environment install | Each candidate wheel installs into a new temporary `venv`, using `--no-index --no-deps` by default. |
| F-06 | Import-origin smoke test | Configured/inferred imports are attempted with `python -I` from an empty directory and their resolved paths must be inside the temporary environment. |
| F-07 | Console-script smoke test | Declared entry points are found in the venv and `--help` exits successfully within the configured timeout. |
| F-08 | Report stability | JSON has `schema_version: 1`, artifact hashes, errors/warnings, smoke outcomes, durations, and stable finding codes. |
| F-09 | Offline-by-default | No network call is initiated by PyDistPilot itself; dependency resolution and build isolation are explicit flags. The chosen build backend may itself access resources only when configured by the user. |
| F-10 | Input/resource safety | Subprocesses use argument arrays and `shell=False`; each process has a timeout; captured output is bounded; archives have size/member limits and path checks. |
| F-11 | Static-only inspection | `inspect` never installs artifacts, calls a build backend, imports package code, or extracts archive contents. |
| F-12 | Predictable exit status | Successful run returns 0; verification or artifact errors return 1; CLI/report-write errors return 2. |
| F-13 | No silent overwrites | `--keep-artifacts` only accepts a new/empty directory outside the source project and refuses non-empty target directories. |
| F-14 | Documentation reproducibility | Clean virtual environment instructions, CLI quick start, config example, exit codes, safety boundary, and known limitations match the installed code. |
| F-15 | SARIF export | `inspect`, `verify`, and `compare` can emit SARIF 2.1.0 with stable rule IDs and privacy-conscious paths; generated JSON parses and output paths cannot collide. |
| F-16 | Regression comparison | `compare` validates schema-v1 input reports up to 16 MiB each, matches findings by stable identity, reports added/resolved counts, and returns nonzero for newly introduced warnings/errors. Strict mode also fails on any failed candidate report. |

## Nonfunctional requirements

- **Python:** 3.10–3.14 in CI; current interpreter is used to build/smoke by default.
- **Dependencies:** no required external runtime dependency on Python 3.11+; `tomli` backport only for Python 3.10; `build` is an optional development/verification dependency.
- **Network/privacy:** no telemetry or automatic uploads. `--install-deps` and `--build-isolation` clearly signal behaviors that can use network package indexes.
- **Reliability:** no shell execution, bounded output memory, per-command timeout, report schema version, deterministic findings, unit and integration tests.
- **Security:** static archive inspection before install, archive path/size limits, no direct extraction of untrusted archive content, minimal temporary environments, best-effort redaction of output excerpts.
- **Portability:** Windows, Linux, and macOS are CI targets. Process/path behavior is exercised in a matrix before release claims.
- **Usability:** one main verification command, one static-inspection command, exit codes suitable for CI, actionable remediation for each error.

## Configuration

```toml
[tool.pydistpilot]
imports = ["public_package", "public_package.api"]
```

`--import MODULE` is repeatable and overrides configured targets for that run. Import auto-discovery only includes visible regular packages/modules from a wheel; namespace package intentions and generated import roots should be configured explicitly.

## Deliberately out of scope for 0.2.0

- Automatically upload to PyPI or GitHub Releases.
- Sign distributions or verify Sigstore/PyPI attestations.
- Scan package dependencies for CVEs, licenses, malicious code, or package-name typosquatting.
- Claim reproducible builds or compare independent builder outputs byte-for-byte.
- Execute a test suite or arbitrary user-supplied command by default.
- Resolve dependencies from the internet unless `--install-deps` is passed.
- Perform a complete Python-version/OS architecture matrix.
- Prove end-to-end functional correctness or semantic compatibility.

## MVP and roadmap

### 0.2.0 alpha — current scope

- Build wheel + sdist; rebuild wheel from sdist.
- Static archive path, metadata, ZIP integrity, wheel RECORD verification.
- New virtual environment install with no index/no deps by default.
- Import and console-script help smoke checks.
- CLI and JSON report; GitHub Actions CI; security-focused documentation.

### 0.2.x — based on maintainer feedback

- Configurable console-script arguments and explicit allow/skip rules.
- Optional offline wheelhouse for dependency-complete smoke testing.
- GitHub Actions job-summary adapter built on existing report data.
- Better namespace-package and `py.typed`/package-data heuristics.

### 0.3.x

- Multi-interpreter matrix runner using explicitly selected interpreters.
- Optional wheel/sdist file manifest comparison with explained exclusions.
- Output schema migration guidance and richer artifact-level baseline policies.

### 1.0 gate

- Validate on a range of real maintained packages and extension-package workflows.
- Collect user feedback on false positives, timings, and setup friction.
- Complete platform matrix, audit false positive/negative behavior, document schema guarantees, and stabilize configuration.


## 0.2.0 release additions

- Emit SARIF 2.1.0 alongside existing JSON reports for `inspect`, `verify`, and `compare`.
- Compare accepted and candidate schema-v1 reports using stable issue keys and report new/resolved findings.
- Fail the default comparison gate for new errors and warnings; offer `--fail-on-current-failure` for strict candidate status enforcement.
- Reject malformed report structures and cap each comparison JSON input at 16 MiB.
- Keep local path handling privacy-conscious in SARIF by using safe relative paths or basenames rather than local file URIs.
