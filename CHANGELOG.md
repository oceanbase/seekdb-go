# Changelog

## Unreleased

## v1.4.0

### Versions

- First tagged release of the root Go SDK module,
  `github.com/oceanbase/seekdb-go v1.4.0`; requires Go 1.22+ and cgo.
- Pins all four platform modules at `v1.4.0`, embedding seekdb 1.4.0.0-r1.
  The existing native archives are reused without changes.
- Root SDK and native-module versions are independent. A Go-only release can
  reuse an existing native version.

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
- Supplied-release-input validation reads thin and universal Mach-O headers in
  Python, allowing prebuilt bundles to be published without macOS tools.

### Documentation

- Clarified Windows loopback TCP defaults, MinGW-w64 cgo compilation and the
  separate Visual C++ runtime prerequisite.
- Documented platform verification scope, lifecycle boundaries, independent
  module versions and known native startup limitations in
  [support](docs/support.md).

### Known issues

- Complete source/build provenance for the bundled native inputs remains
  outstanding, tracked in [seekdb-go #3](https://github.com/oceanbase/seekdb-go/issues/3).
- Intermittent Windows native bootstrap `OB_TIMEOUT`, tracked in
  [seekdb #1544](https://github.com/oceanbase/seekdb/issues/1544).
- Clean-system macOS first-execution trust validation remains outstanding.
- The macOS 15.6.1 runtime floor and Linux arm64 glibc 2.28 userland have not
  been exercised directly. See [support](docs/support.md) for verified
  environments and native/runtime requirements.
