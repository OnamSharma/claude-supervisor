# Releasing

Releases are built and published to PyPI automatically when a `v*` tag is
pushed, via [`.github/workflows/release.yml`](../.github/workflows/release.yml).

## One-time setup

Configure **PyPI Trusted Publishing** so no API token is needed:

1. Create the project on [PyPI](https://pypi.org) (or reserve the name).
2. In the project's *Publishing* settings, add a **GitHub Actions** trusted
   publisher:
   - Owner: `OnamSharma`
   - Repository: `claude-supervisor`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In the GitHub repo, create an **environment** named `pypi`
   (Settings → Environments). Optionally add required reviewers.

(Alternatively, add a `PYPI_API_TOKEN` secret and switch the publish step to
token auth — but Trusted Publishing is preferred.)

## Cutting a release

1. Update the version in `pyproject.toml` **and**
   `src/claude_supervisor/__init__.py` (keep them in sync).
2. Move the `CHANGELOG.md` "Unreleased" items under the new version + date.
3. Commit: `git commit -am "release: vX.Y.Z"`.
4. Tag and push:
   ```bash
   git tag vX.Y.Z
   git push origin main --tags
   ```
5. The release workflow builds, `twine check`s, and publishes to PyPI.
6. Create a **GitHub Release** from the tag, pasting the changelog section.

## Versioning

Semantic Versioning. While pre-1.0 the API and detection defaults may change
between minor versions; breaking changes are called out in the changelog.
