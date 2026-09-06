# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **distribution** is `typedout-py`; the **import** is `typedout`. See the
README for why they differ.

## [0.1.1] — 2026-09-06

The first tag that rebuilds what is published. `v0.1.0` did not: it predates
the commit that set the distribution name, so the tag and `typedout-py 0.1.0`
on PyPI are different trees. Nothing in the code was wrong — it was a
provenance defect — but a tag you cannot rebuild from is not much of a tag.

### Changed

- The distribution is published as **`typedout-py`**. PyPI refuses the bare
  name `typedout`: it normalises away `-`, `_` and `.` before comparing, so it
  collides with an unrelated project called `typed-out`. The import name is
  unchanged, and no code has to change.
- `README` install instructions and the Python floor, which claimed 3.9 while
  `requires-python` and the classifiers said 3.10.

### Added

- CI on every push and pull request: the full suite across Python 3.10–3.13,
  plus a job that installs and imports the optional Anthropic and OpenAI
  extras.
- `SECURITY.md`, including a private reporting channel and the two limits worth
  stating plainly — validation guarantees the *shape* of a result and not its
  truth, and `ValidationFailure.last_raw` carries the raw model output into
  logs.
- This changelog.

### Fixed

- `test_version_matches_installed_metadata` asked `importlib.metadata` for the
  import name rather than the distribution name, so it broke on the rename.

## [0.1.0] — 2026-09-05

First tagged release, shipping the state of `main` after the verified audit of
2026-09-04.

**Do not build from this tag expecting the published package.** See the
correction on its release page.

[0.1.1]: https://github.com/ferinazumaDEV/typedout/releases/tag/v0.1.1
[0.1.0]: https://github.com/ferinazumaDEV/typedout/releases/tag/v0.1.0
