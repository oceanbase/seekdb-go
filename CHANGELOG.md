# Changelog

## Unreleased

### Added

- Independently tagged native `v1.4.0` modules with committed dependency
  checksums and public Go proxy/sumdb installation validation.
- A complete SQL example in its own module, using returned connection options,
  parameterized Unicode data and close/reopen persistence.
- Four-platform SQL integration coverage for prepared statements, CRUD,
  transactions, vector distance, shared handles and persisted results.
- Concurrent lifecycle and cross-process native-cache extraction tests.
- Failed test instance retention and CI log artifacts.

### Fixed

- Downloaded-native-module tests can no longer silently skip missing checksums.
- Root release publication requires successful Test and Public install
  validation runs for the exact remote main commit.
- macOS packaging and supplied-release-input validation reject runtime files
  without an arm64 slice, including bundled dependencies.

### Documentation

- Clarified Windows loopback TCP defaults, MinGW-w64 cgo compilation and the
  separate Visual C++ runtime prerequisite.
- Documented platform verification scope, lifecycle boundaries, independent
  module versions and known native startup limitations in
  [support](docs/support.md).

### Known issues

- Intermittent Windows native bootstrap `OB_TIMEOUT`, tracked in
  [seekdb #1544](https://github.com/oceanbase/seekdb/issues/1544).
- Clean-system macOS first-execution trust validation remains outstanding.

No root-module release tag has been published as part of these changes. Native
archive bytes are unchanged.
