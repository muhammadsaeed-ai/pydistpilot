# Security policy

## Supported versions

Security fixes are currently targeted at the latest 0.1.x release. The project is an alpha, and a formal backport policy will be established after a stable 1.0 release.

## Reporting a vulnerability

Please do not post exploit details, private logs, or credential-bearing reports in a public issue. Use GitHub's **Report a vulnerability** / private security-advisory workflow on the repository once the remote repository has been created. Include the affected version, platform, the smallest safe reproducer, impact, and any mitigations. Remove secrets and private user/package data before sharing.

If private reporting is not enabled yet, contact the repository maintainer through the private contact channel published on the actual repository profile. Do not invent or assume an email address.

## Important usage guidance

- `pydistpilot inspect` is static inspection and should be preferred for artifacts from unknown sources.
- `pydistpilot verify` runs build backends and package imports/entry points. Do not use it as a sandbox for untrusted source.
- Use a disposable, low-privilege environment/container for suspicious source or packages.
- Reports may include paths and sanitized output excerpts; review before sharing.
- The project does not claim malware detection, full secret detection, or package provenance verification.
