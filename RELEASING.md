# Releasing

This document describes how versions are determined, how to cut a release, and the planned path to fully automated PyPI publishing.

> **TL;DR** — Versions come from git tags. To release, tag the commit (`vX.Y.Z`) and push the tag. Once trusted publishing is wired up (see below), PyPI publish is automatic.

---

## Versioning model

This project uses [**setuptools-scm**](https://setuptools-scm.readthedocs.io/) as the single source of truth for the package version. There is **no version literal in `pyproject.toml` or in `__init__.py`**.

How it works:

- At **build time**, setuptools-scm runs `git describe` and derives the version from the nearest reachable tag.
- At **runtime**, `python_sentry_logger_wrapper.__version__` reads from installed package metadata via `importlib.metadata.version("sentry-struct-logger")`.

This means version drift between `pyproject.toml` and `__init__.py` is no longer possible — both come from the same git tag.

### What setuptools-scm infers

| Git state | Derived version | PyPI-uploadable? |
|---|---|---|
| HEAD is exactly on tag `v1.2.3` | `1.2.3` | yes |
| HEAD is 4 commits past tag `v1.2.3` | `1.2.4.dev4` | yes (dev release) |
| Dirty working tree | same as above | yes (we strip the `+dirty` local segment) |
| No git, no SCM metadata (sdist edge case) | `0.0.0+unknown` (fallback) | no — won't happen in practice |

We set `local_scheme = "no-local-version"` so dev builds get clean PEP 440 versions that PyPI accepts. We follow [SemVer](https://semver.org/) for tags.

---

## Cutting a release (manual, today)

Until trusted publishing is set up, the release is two commands locally plus an upload step.

```bash
# 1. Make sure main is clean and up to date
git checkout main
git pull --ff-only

# 2. Tag the release commit. Use an annotated tag.
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0

# 3. Build artifacts (uses setuptools-scm to stamp the version)
python -m build

# 4. Verify the wheel name matches the tag
ls dist/   # should show sentry_struct_logger-0.2.0-*.whl

# 5. Upload to PyPI
python -m twine upload dist/*
```

That's it. The git tag is the release.

### Choosing the next version (SemVer)

- **Patch** (`v0.1.0` → `v0.1.1`): bug fixes, no API changes.
- **Minor** (`v0.1.0` → `v0.2.0`): new features, backward-compatible.
- **Major** (`v0.1.0` → `v1.0.0`): breaking changes to the public API.

While on `0.x`, treat **minor** bumps as the breaking-change signal — consumers should pin `>=0.2,<0.3` accordingly.

### Don't

- **Don't move tags.** If a release goes wrong, bump the patch version and tag again. Yanked versions stay yanked on PyPI.
- **Don't hand-edit `__version__` or add `version =` back to `pyproject.toml`.** It will be ignored, then someone will hit a confusing inconsistency.
- **Don't tag from a feature branch** unless you are intentionally cutting a pre-release.

---

## Automating the release (recommended next step)

The manual flow above is fine, but a one-file GitHub Actions workflow can publish on tag push using **PyPI Trusted Publishing** (OIDC — no long-lived API tokens, nothing to rotate).

### One-time setup

1. Go to <https://pypi.org/manage/project/sentry-struct-logger/settings/publishing/> and add a **GitHub Actions** trusted publisher with:
   - **Owner**: `HEAL-Engineering`
   - **Repository**: `python-sentry-logger-wrapper`
   - **Workflow filename**: `release.yml`
   - **Environment** (recommended): `pypi`
2. In GitHub, create a [protected environment](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment) named `pypi` and require a manual approval reviewer.

### `.github/workflows/release.yml` (template for a follow-up PR)

```yaml
name: release

on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # setuptools-scm needs full history + tags
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install build
      - run: python -m build
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi              # gates on manual approval
    permissions:
      id-token: write              # required for trusted publishing
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

After this is in place, the entire release flow becomes:

```bash
git tag -a v0.2.1 -m "Release 0.2.1"
git push origin v0.2.1
# Approve the deployment in the GitHub Actions UI. Done.
```

### Going further (optional)

- **release-please** or **python-semantic-release** can read [Conventional Commits](https://www.conventionalcommits.org/) on `main` and open a "Release PR" that proposes the next tag + a CHANGELOG entry. Merging that PR creates the tag, which fires the workflow above. Fully push-button releases with no manual tag step.
- **CHANGELOG.md** — even without release-please, keep a hand-maintained changelog. Consumers read it before upgrading.

---

## For downstream consumers

This library is published on PyPI as **`sentry-struct-logger`** and imported as **`python_sentry_logger_wrapper`**.

While the project is pre-1.0, pin to a minor range:

```toml
# pyproject.toml of a consumer
dependencies = [
    "sentry-struct-logger>=0.2,<0.3",
]
```

After 1.0, a caret-style range (`>=1.0,<2`) is appropriate.

To check the installed version at runtime:

```python
import python_sentry_logger_wrapper
print(python_sentry_logger_wrapper.__version__)
```

---

## Troubleshooting

**`__version__` reports `0.0.0+unknown`.**
The package metadata wasn't found at import time. This happens if you're running directly from a source tree without `pip install -e .` first. Install the package (editable is fine) and re-run.

**Build reports a version like `0.0.0+unknown` or `0.1.1.dev0+d20251231`.**
setuptools-scm couldn't read git history. Causes:
- A shallow clone (CI default). Set `fetch-depth: 0` on `actions/checkout`.
- Building from an extracted sdist that was generated incorrectly. Always build from a git checkout.

**The version on PyPI is `X.Y.Z.devN` instead of `X.Y.Z`.**
You tagged the commit *before* it landed, or HEAD wasn't on the tagged commit when you ran `python -m build`. Make sure `git describe --tags --exact-match HEAD` prints the tag you want.

**I need to release a hotfix from an older minor line.**
Branch from the older tag (`git checkout -b 0.1.x v0.1.0`), commit the fix, tag `v0.1.1`, and push. setuptools-scm will derive `0.1.1` correctly because that branch's nearest tag is `v0.1.0`.
