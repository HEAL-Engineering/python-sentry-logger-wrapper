# Releasing

This document describes how versions are determined and how to cut a release.

> **TL;DR** — Versions come from git tags. To release: `git tag -a vX.Y.Z -m "Release X.Y.Z" && git push origin vX.Y.Z`, then approve the deployment in the GitHub Actions UI. PyPI publish is automatic via trusted publishing.

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

## Cutting a release

Releases are automated via [`.github/workflows/publish.yml`](.github/workflows/publish.yml). Pushing a `v*` tag builds the wheel and uploads it to PyPI through [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no API tokens to manage).

```bash
# 1. Make sure main is clean and up to date
git checkout main
git pull --ff-only

# 2. Tag the release commit. Use an annotated tag.
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0

# 3. Approve the run in GitHub Actions
#    (the `pypi` environment gates publish on a required reviewer).
```

That's it. The git tag is the release.

### If a publish run fails

Prefer **re-running the original tag-triggered workflow run** from the Actions UI — it's already tied to the right tag ref, so the rebuild will produce the same version.

`workflow_dispatch` is available as a backup, but the job is hard-gated to only run when the ref is `refs/tags/v*`. That means dispatching the workflow with `main` (the default in the UI) will exit immediately. To dispatch manually, pick the **`vX.Y.Z` tag** from the "Use workflow from" dropdown — never a branch.

### Already configured (FYI, not setup steps)

These are configured once per project and shouldn't need to change:

- **PyPI trusted publisher** is registered against this repo + `publish.yml` + the `pypi` environment.
- **GitHub `pypi` environment** has required reviewers configured — that's the manual approval gate.

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

## Going further (optional)

- **release-please** or **python-semantic-release** can read [Conventional Commits](https://www.conventionalcommits.org/) on `main` and open a "Release PR" that proposes the next tag + a CHANGELOG entry. Merging that PR creates the tag, which fires `publish.yml`. Fully push-button releases with no manual tag step.
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
