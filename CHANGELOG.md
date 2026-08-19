# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [2.1.0] - 2026-08-19

### Fixed

- **Compression sampling produced no result on non-amd64 builds — including
  every Apple Silicon Mac.** `compressSample` called `minlz.TryEncode` with
  `LevelSuperFast`. That level's pure-Go fallback path — used on arm64 and on
  any `amd64` build compiled with `-tags=noasm`/`purego` — returns "not
  compressible" for every input regardless of content, so every sample was
  discarded and the tool always reported
  `Error: No data was compressed successfully`. This affected the CLI binary
  and the packaged Electron app identically. Fixed by switching to
  `minlz.LevelBalanced`, which uses a working encoder on every architecture.
  Not an arm64-specific defect in this codebase: it reproduces on amd64 too
  once the assembly path is disabled, and traces to the underlying
  `minlz` library, not to anything IBM's upstream `ess_comprestimator` does
  (upstream already used `LevelBalanced`).
- **Reported sizes were truncated, not rounded.** `prettyBytes` divided
  integers before converting to `float64`, so e.g. 1.9 GB displayed (and was
  parsed downstream by the web backend) as `1.00 GB`. Every size shown by the
  CLI and the web UI was affected. Fixed with float-accurate division.
- A handful of other silent failures were converted to explicit errors —
  see the [v2.1.0 pull request](https://github.com/cdmaestas/ess_comprestimator/pull/1)
  for the full list.

### Changed

- CI now runs the Go test suite on `macos-latest` (arm64) in addition to
  `ubuntu-latest` (amd64), and the packaging job no longer runs unless both
  platforms' checks pass. This is the check that would have caught the
  compression defect above before it shipped.
- RPM signing in the release workflow now degrades to an unsigned release
  (with a build warning) when `GPG_PRIVATE_KEY` isn't configured, instead of
  failing the release outright.

### Known issue carried into this release

- The estimated compression ratio still excludes incompressible sample bytes
  from both sides of the ratio, which can overstate the achievable ratio by
  a large factor on data that mixes compressible and incompressible content.
  A corrected dual-ratio (compressible-only vs. whole-sample "effective"
  ratio) is planned for the next release.

## [2.0.1.1] - 2026-06-22

> **⚠️ Broken on Apple Silicon (and any non-amd64 build).** Every job fails
> with `Error: No data was compressed successfully`. Fixed in 2.1.0 — do not
> use this release. Marked pre-release on GitHub.

Packaging fix only (author metadata for Linux `.deb`/`.rpm`). Carries the
same compression defect as 2.0.1.

## [2.0.1] - 2026-06-19

> **⚠️ Broken on Apple Silicon (and any non-amd64 build).** Every job fails
> with `Error: No data was compressed successfully`. Fixed in 2.1.0 — do not
> use this release. Marked pre-release on GitHub.

Introduced the `minlz.TryEncode` + `LevelSuperFast` combination responsible
for the defect above, as part of adding incompressible-byte tracking to the
Go binary's output.

[Unreleased]: https://github.com/cdmaestas/ess_comprestimator/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/cdmaestas/ess_comprestimator/compare/v2.0.1.1...v2.1.0
[2.0.1.1]: https://github.com/cdmaestas/ess_comprestimator/compare/v2.0.1...v2.0.1.1
[2.0.1]: https://github.com/cdmaestas/ess_comprestimator/releases/tag/v2.0.1
