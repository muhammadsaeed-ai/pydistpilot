# PyPI Trusted Publishing

The repository includes `.github/workflows/publish.yml`. It only publishes when a `v*` tag is pushed; `workflow_dispatch` can run the build job but intentionally does not publish. The distribution build job has read-only contents permission and no OIDC publishing permission. A separate `publish` job downloads the exact built artifacts and receives `id-token: write`.

Before a tag can publish, the maintainer must:

1. Create the intended public GitHub repository and push the source.
2. Confirm `pyproject.toml` repository URLs name the real owner and repository.
3. Create or reserve the `pydistpilot` project on PyPI with a Trusted Publisher configured for the exact GitHub owner, repository, workflow filename `.github/workflows/publish.yml`, and GitHub environment `pypi`. For a first PyPI release, configure the publisher during the PyPI project's initial setup per PyPI documentation.
4. Ensure the required environment exists and review its protection/rules.
5. Wait for all CI gates to pass on the exact commit to be released.
6. Confirm the version in `pyproject.toml`, package source, README, changelog, and tag agree.
7. Create and push the version tag, e.g. `v0.2.0`, only after explicit release approval.
8. Verify the build and publish jobs succeed and inspect the resulting project page and uploaded artifact hashes.

The workflow checks that a pushed release tag exactly matches the version in `pyproject.toml`; a tag/version mismatch fails the build before publishing. `workflow_dispatch` runs the build only. The workflow does not use a PyPI API token. PyPI Trusted Publishing requires the job's `id-token: write` permission and a matching publisher configured on PyPI. The publish action should remain separate from the build job so untrusted build-time code cannot inherit OIDC publishing authority. Read the [PyPA Trusted Publishing guide](https://docs.pypi.org/trusted-publishers/using-a-publisher/) and [Python Packaging User Guide's publishing workflow](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) before first release.

This workflow is configuration, not evidence that package registration or publication has happened. No release should be tagged until remote CI passes and the package name/project ownership have been confirmed.
