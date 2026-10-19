# Security model and audit notes

## Intended threat boundary

PyDistPilot has two intentionally different modes:

- `inspect` parses existing wheel/sdist archives and metadata. It does not extract an archive, install it, import it, or invoke a build backend.
- `verify` executes a project's build backend, invokes pip against locally built wheel files, imports requested/inferred Python modules, and invokes each declared console script with `--help`. It is intended for **your own source tree or source you explicitly trust**, not unknown packages downloaded from the internet.

This distinction matters. Building a project and importing its code is code execution, even when initiated by a packaging tool. PyDistPilot cannot sandbox an arbitrary Python build backend into a secure boundary merely by creating a venv.

## Controls implemented

### Command execution

- Commands are passed as argument arrays with `shell=False`; no user string is evaluated by a command shell.
- Standard input is disconnected.
- Each build/install/import/CLI step has a timeout. On POSIX, a timed-out process group is killed; on Windows the tool attempts to terminate the process tree with `taskkill` and falls back to killing the direct child if that is unavailable.
- Child output is drained in a reader thread and stored in memory only up to 64 KiB; output excerpts are truncated.
- Common secret forms in output snippets are redacted on a best-effort basis.
- Network-enabled dependency installation and isolated build dependency installation require explicit flags.

### Temporary environments and files

- Wheel imports run with `python -I` from a new empty working directory to reduce source checkout and user-site influence.
- Fresh `venv` directories are used for built-wheel probes.
- Built archives go to a fresh temporary directory by default; temporary virtual environments and work areas are removed after the run.
- `--keep-artifacts` requires an empty target directory outside the project tree; pre-existing files are not overwritten.
- JSON reports are written atomically via a temporary sibling file.

### Archive inspection

- The static inspector does not extract archive members.
- It rejects absolute paths, parent traversal, backslashes in archive paths, duplicate ZIP member names, and wheel symlinks.
- It enforces limits of 100,000 members, 256 MiB per member, and 512 MiB total declared uncompressed size.
- ZIP CRCs and wheel RECORD hashes/sizes are verified.
- Core metadata is size-limited and validated for Name/Version.

### Dependencies and secrets

- Runtime behavior is standard-library only on Python 3.11+; Python 3.10 uses the `tomli` backport. The verifier uses PyPA `build` if installed, or an existing `uv` executable as a fallback; it does not install its own tooling.
- The selected build frontend is needed to run `verify`, but is optional to the base install; static `inspect` does not need it. Dependency versions are ranged rather than locked for library consumers; CI resolves the supported ranges, and Dependabot monitors Python and GitHub Actions dependencies.
- PyDistPilot makes no telemetry requests and does not upload artifacts.
- Reports include project/artifact paths and limited error evidence. Treat reports as internal diagnostic artifacts before sharing them publicly.

## Initial controls implemented in 0.1.0

- No shell-based subprocess invocation.
- Timeout applied to child processes.
- Bounded stored output and output redaction before it reaches findings.
- Path traversal checks and no direct archive extraction in static inspection.
- Duplicate-member/CRC/size guards and RECORD payload integrity checks.
- Dependency installation excluded from default smoke runs.
- Isolated interpreter and empty working directory for import origin checks.
- Refusal to overwrite a non-empty retained-artifact directory.

## Residual risks and known gaps

1. **`verify` executes arbitrary project build hooks and package code.** This is the largest risk. It must not be used as a malware sandbox for unknown projects.
2. **Redaction is heuristic.** It covers several common token and assignment patterns, but it cannot guarantee that a secret never appears in a custom traceback, environment dump, or unusual log format. Reports also include the absolute project path and can contain local artifact paths. Review reports before sharing or attaching them to public issues.
3. **A subprocess can still access files and network as the invoking user.** A timeout is not a sandbox. On Windows, tree termination is best-effort and the direct-child fallback cannot guarantee every descendant is stopped. For untrusted source, use a disposable VM/container with reduced privileges and inspect artifacts statically first.
4. **`--install-deps` can resolve from configured package indexes and executes installation/build hooks.** Dependency pinning, trusted indexes, hash checking, vulnerability scanning, and provenance verification remain the user's responsibility.
5. **`--build-isolation` may download build tools.** Default no-isolation mode uses the build environment already configured by the user.
6. **Archive parsers themselves may have vulnerabilities.** Size and path checks reduce some risks but cannot guarantee safety against all malformed inputs or dependency/runtime bugs.
7. **Static checks do not detect malicious logic or establish publisher identity.** Use Sigstore/PyPI attestations or other provenance policy when required.
8. **The report can be incomplete.** A smoke check covers only configured/inferred import roots and `--help`, not the entire API or business behavior.
9. **Cross-platform CI and vulnerability scans are only evidence for the specific builds that ran.** They are not a universal guarantee.

## Security policy

Please report vulnerabilities privately using the process described in [SECURITY.md](../SECURITY.md). Do not disclose a secret-bearing verification report in an issue without reviewing it first.


## Additional controls in 0.2.0

- Baseline comparison rejects unsupported JSON schema versions, non-PyDistPilot inputs, prior comparison results, and malformed list/object shapes instead of guessing how to interpret them.
- Each baseline/candidate input is capped at 16 MiB before JSON parsing, with an additional capped read to guard against file-size changes between the metadata check and read.
- SARIF paths are repository-relative when the path is under the supplied project root; external absolute paths are reduced to basenames. No local `file://` base URI is emitted.
- SARIF and JSON output paths are rejected when they resolve to the same location. JSON output writes remain atomic and refuse a symlink target.

These controls do not make diagnostic reports safe to publish automatically. Finding text can originate from build tools or project content; review outputs for sensitive messages and source-derived data before sharing. Baselines are also policy inputs: a reviewed baseline can deliberately allow known findings, so protect review changes to it.
