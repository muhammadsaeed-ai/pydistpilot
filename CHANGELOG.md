# Changelog

All notable changes to PyDistPilot are documented here. The format is inspired by Keep a Changelog; versions follow Semantic Versioning after API stability is established.

## [0.2.0] - 2026-10-19

### Added

- SARIF 2.1.0 export for static artifact inspection, end-to-end verification, and newly introduced regression findings.
- `compare` command for comparing schema-v1 reports against an accepted baseline with stable finding identity, new/resolved issue summaries, and CI-friendly exit codes.
- Strict structure validation and a 16 MiB per-file cap for comparison inputs to reduce malformed-input and resource-exhaustion risk.
- PyPI Trusted Publishing workflow skeleton that separates distribution building from OIDC-authenticated publishing and runs only for version tags.
- Expanded CI coverage to parse and validate the emitted SARIF document.

### Security and compatibility

- SARIF locations avoid embedding local file URIs; paths are project-relative when safe and otherwise reduced to basenames.
- Verification output paths refuse to clobber existing project files, while valid previous PyDistPilot reports can be refreshed atomically.
- Report comparison matches finding code, severity, and message, intentionally ignoring transient paths and evidence.
- Baseline comparison can suppress existing failures by design; use `--fail-on-current-failure` for a strict green-only policy.
- Version 0.2.0 retains the schema-v1 JSON verification report for the original verification fields and adds a separate comparison-report shape.

## [0.1.0] - 2026-10-19

### Added

- `verify` flow to build a wheel and sdist, audit both, rebuild a wheel from the sdist, and smoke-test built wheels in fresh virtual environments.
- Static `inspect` command for existing wheels and supported source distributions.
- Wheel metadata/structure/RECORD validation and source archive path/metadata checks.
- Import-root smoke checks and console-script `--help` checks from an empty working directory.
- JSON report schema version 1, stable finding codes, terminal output, and CI-ready exit codes.
- Offline/no-dependency install defaults, explicit network-related flags, bounded subprocess output, timeouts, and security documentation.
- Unit and integration test suites, GitHub Actions CI, contributing/security policy, and release checklist.

### Limitations

- Alpha release; needs validation against a larger set of real packages and platforms.
- Static inspections do not prove provenance or detect malicious logic.
- Smoke tests cover only selected import roots and console-script help behavior.

### Documentation follow-up — 19 October 2026

- Added a custom local SVG project banner and diagrams for architecture, end-to-end workflow, component hierarchy, and security boundaries.
- Added editable Mermaid diagram sources, a JSON diagram catalog, repository SEO/topic metadata, a public-launch checklist, and GitHub publishing instructions.
- Kept publishing and hosted CI states explicit: no remote repository creation or push is claimed by this source bundle.
