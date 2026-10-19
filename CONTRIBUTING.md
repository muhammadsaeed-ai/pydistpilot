# Contributing to PyDistPilot

Thank you for helping improve release verification for Python packages.

## Before opening an issue

Use an accurate Python version, operating system, PyDistPilot version, build backend, and the exact command. Include a small reproducible package where possible. Review JSON/terminal evidence and remove credentials or private paths before sharing it. For security-sensitive findings, follow [SECURITY.md](SECURITY.md) rather than filing a public issue.

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
- Do not weaken or skip a check solely to obtain a green result. If a check is incorrect, add a regression test and fix the underlying logic.
- Keep the static-only `inspect` path free of code execution and extraction.
- Treat `verify` as trusted-source code execution and preserve its timeout/network boundaries.
- Keep subprocesses shell-free, output bounded, and findings evidence-based.
- Use stable finding codes; don't reuse a released code for a different meaning.
- Do not include real secrets or proprietary package artifacts in fixtures.
- Update the README/spec/security documentation when CLI behavior, findings, or the report schema changes.
- Keep the runtime dependency footprint small; justify every new dependency in the pull request.
- Avoid introducing a remote service or telemetry without a separate privacy and security design review.

## Pull request checklist

- [ ] Problem and intended user benefit are clear.
- [ ] Automated tests cover the change.
- [ ] `pytest`, `ruff check src tests`, and `mypy src/pydistpilot` pass locally.
- [ ] Documentation, finding guidance, and report-schema implications are updated.
- [ ] Security implications and execution permissions are described.
- [ ] No secrets, generated build outputs, or unrelated formatting changes are included.

## Design discussion

Prefer a small explicit workflow over a framework. PyDistPilot should report what its checks actually observed; it should not claim to prove correctness or infer a root cause from insufficient evidence.
