# Contributing to PyDistPilot

Thank you for helping improve release verification for Python packages.

## Before opening an issue

Use an accurate Python version, operating system, PyDistPilot version, build backend, and exact command. Include a small reproducible package where possible. Review JSON/terminal evidence and remove credentials or private paths before sharing it. For security-sensitive findings, follow [SECURITY.md](SECURITY.md) rather than filing a public issue.

## Development setup

Python 3.10–3.14 is intended for CI support.

```bash
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
ruff check src tests
mypy src/pydistpilot
```

## Contribution rules

- Add tests for behavior changes, boundary cases, and error paths.
- Do not weaken a check solely to obtain a green result. Add a regression test and fix incorrect behavior.
- Keep the static-only `inspect` path free of code execution and extraction.
- Treat `verify` as trusted-source execution and preserve timeout/network boundaries.
- Keep subprocesses shell-free, output bounded, and findings evidence-based.
- Use stable finding codes; do not reuse a released code for a different meaning.
- Do not include real secrets or proprietary package artifacts in fixtures.
- Update documentation when CLI behavior, findings, or report schemas change.
- Justify new dependencies and avoid telemetry or remote services without a separate privacy/security design.

## Pull request checklist

- [ ] Problem and user benefit are clear.
- [ ] Automated tests cover the change.
- [ ] Tests, Ruff, and mypy pass locally.
- [ ] Documentation and report-schema implications are updated.
- [ ] Security implications and execution permissions are described.
- [ ] No secrets, generated build outputs, or unrelated formatting changes are included.

Prefer a small explicit workflow over a framework. PyDistPilot should report what it observed; it should not claim to prove correctness or infer a root cause from insufficient evidence.
