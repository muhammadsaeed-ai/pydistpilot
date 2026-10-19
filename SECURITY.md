# Security policy

## Supported versions

Security fixes currently target the latest published release candidate line, 0.2.x. The project is alpha, so stable backport commitments will be defined after a 1.0 release.

## Reporting a vulnerability

Please do not post exploit details, private logs, or credential-bearing reports in a public issue. Use GitHub's private vulnerability reporting / security advisory feature on this repository when enabled. Include the affected version, platform, a minimal safe reproducer, impact, and mitigations. Remove secrets and private package data before sharing.

## Important usage guidance

- `pydistpilot inspect` is static inspection and should be preferred for artifacts from unknown sources.
- `pydistpilot verify` runs build backends and package imports/entry points. Do not use it as a sandbox for untrusted source.
- Use a disposable, low-privilege environment/container for suspicious source or packages.
- Reports may contain paths and sanitized output excerpts; review them before sharing.
- The project does not claim malware detection, full secret detection, or package provenance verification.
