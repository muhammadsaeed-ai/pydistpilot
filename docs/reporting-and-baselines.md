# SARIF and baseline comparison

## Commands

```bash
pydistpilot verify . --report report.json --sarif report.sarif
pydistpilot inspect dist/example-1.0.0-py3-none-any.whl --json inspect.json --sarif inspect.sarif
pydistpilot compare accepted.json candidate.json --json comparison.json --sarif regressions.sarif
```

`inspect` only parses a local artifact. `verify` executes the trusted project's build backend and installed-package smoke checks. `compare` accepts two PyDistPilot schema-version-1 JSON reports emitted by `verify` or `inspect`. It checks the report identity and shape, rejects comparison-result JSON as a baseline, refuses unknown schema versions, requires regular-file inputs, and caps each JSON input file at 16 MiB.

## Comparison identity

A finding identity is `(code, severity, message)` and occurrences are counted. Paths, temporary build locations, and evidence snippets are deliberately excluded because those values often change across otherwise-equivalent runs. A new error or warning fails the comparison; informational findings are reported but do not block it. A finding that was present in the baseline and remains in the candidate is treated as known debt, not a new regression. Use `--fail-on-current-failure` when the policy is simply “the candidate status must be passed.”

Baseline files are policy inputs. Review them before accepting updates; an overly permissive baseline can mask pre-existing problems. Do not auto-accept a new baseline simply because the candidate failed.

## SARIF fields and privacy

PyDistPilot emits SARIF version `2.1.0`, stable rule identifiers, severity levels, recommendations, and a message-based partial fingerprint. It does not add `file://` base URIs. Paths within the supplied project root are made relative. External or absolute paths are reduced to basenames to avoid exposing unrelated local directory structure or usernames. This is a defense-in-depth measure, not a guarantee that all finding messages/evidence are free of secrets; review reports before sharing them.

The SARIF output is standards-shaped and can be consumed by compatible tooling. The current workflow validates its version and basic structure locally; hosted GitHub code-scanning ingestion should be tested after the public repository and required permissions are configured.
