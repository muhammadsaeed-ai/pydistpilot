# Publish PyDistPilot to GitHub

The source tree is prepared for a public repository named `pydistpilot`. The suggested owner from the previous project context is `muhammadsaeed-ai`; confirm the correct account before pushing. This environment can prepare and validate the source tree, but the available GitHub connection currently does not provide repository creation and is authenticated as a different account (`ranagraphics1573-eng`). No remote repository or push is claimed by this document.

## 1. Create the public repository

Open [GitHub's new repository page](https://github.com/new). Select the correct owner, enter `pydistpilot`, select **Public**, and create the repository without pre-populating a README, license, or `.gitignore` (these files are already present in this source tree).

## 2. Initialize and push the source tree

Open a terminal in the extracted `pydistpilot/` project directory. Configure your real Git commit identity first if it is not configured globally. Then run:

```bash
git init -b main
git add .
git commit -m "feat: prepare PyDistPilot 0.2.0 with README diagrams"
git remote add origin https://github.com/YOUR-OWNER/pydistpilot.git
git push -u origin main
```

Replace `YOUR-OWNER` with the account that actually created the repository. Git will prompt for or use your configured GitHub credential manager; do not paste a personal access token into the source tree, shell history, or README.

If this directory already has a Git repository, do not run `git init` again. Inspect `git status` and `git remote -v` first, then set the correct remote and commit only after checking the staged diff.

## 3. Apply repository metadata

Set this description:

> Python package release verification CLI: build and inspect wheels and sdists, rebuild from source distributions, and smoke-test installed artifacts locally and in CI.

Add the 20 relevant topics listed in [`repository-metadata.json`](repository-metadata.json). GitHub documents a maximum of 20 topics per repository; the topics are designed for relevance and classification, not to promise traffic. Confirm the README's local SVG diagrams display correctly after the initial push.

## 4. Verify hosted CI before a release

Open the **Actions** tab and inspect all jobs. The workflow configured in `.github/workflows/ci.yml` has not been run by GitHub-hosted runners in this preparation environment. Resolve any errors, and update [`verification-report.md`](verification-report.md) with the actual hosted results. Do not publish the package to PyPI or describe `v0.2.0` as release-certified until the missing lint, type, audit, and OS/Python matrix checks have evidence.
