# Support and known limitations

## Platforms

The native `v1.4.0` modules embed seekdb 1.4.0.0-r1. Go 1.22+ and cgo are
required. The runtime defaults to `memory_budget=1G` and `log_disk_size=2G`
on first initialization; allow additional process memory and disk space.

| Platform | Binary requirement | Functional verification environment |
| --- | --- | --- |
| macOS arm64 | macOS 15.6.1+ | CI: macos-26; manual: macOS 27.0.1, Apple clang 17 |
| Linux amd64 | glibc 2.28+ | CI: Ubuntu 24.04; manual: Alibaba Cloud Linux 3, glibc 2.32, GCC 9.4 |
| Linux arm64 | glibc 2.28+ | CI: Ubuntu 24.04 arm64 |
| Windows amd64 | x64 Windows with Microsoft Visual C++ v14 x64 runtime | CI: windows-2025; manual: Windows 11 26H2, MinGW GCC 16.2 |

The macOS and glibc floors describe native binary requirements. Newer CI
systems do not prove that every feature works on those minimum OS/library
versions. Minimum-version acceptance must be recorded separately when making
a release support claim. Windows versions older than the environments listed
above have not been qualified; this SDK does not claim support for every
Windows release. macOS amd64, Windows arm64 and musl/Alpine bundles are not
provided.

The normal endpoint is a Unix socket on POSIX and loopback TCP with a random
port on Windows. Consume `ConnectionOptions` instead of assuming that default.
The current bundle does not exercise the optional named-pipe client adapter.

## Lifecycle contract

- `Open` creates or reopens the given database directory. Ordinary server
  parameters apply on first initialization; persisted settings are used on
  reopen. `port` and `mysql_port_mode` are driver-reserved startup settings.
- Multiple handles in one process may refer to the same directory. Each handle
  must be closed. Close the SQL connections associated with a handle before
  closing that handle; another open handle remains usable.
- `Close` is idempotent. Concurrent `Close` and `ConnectionOptions` calls on the
  same handle are serialized. Once closed, `ConnectionOptions` returns an error.
  Do not copy a `DB` value or mutate its `DBDir` field to retarget it.
- Processes may share the native extraction cache; first extraction is locked
  across processes. This is not a promise of concurrent multi-process ownership
  of one database directory. Use separate database directories across processes.
- The SDK does not provide server health monitoring or automatic recovery after
  unexpected server termination. An endpoint describes connection information,
  not a health check. Check SQL errors and preserve the instance's `log/`
  directory when diagnosing failures.

## Known startup limitations

- Windows fresh-database bootstrap can intermittently fail with native
  `OB_TIMEOUT (-4012)`, after which the server exits before becoming ready.
  It is tracked in [seekdb #1544](https://github.com/oceanbase/seekdb/issues/1544).
  A later successful run does not establish that this native issue is fixed.
- A macOS first-execution failure was associated with interrupted system trust
  assessment. Later runs passed, but a clean-system first-execution validation
  is still outstanding. The current executable uses an ad-hoc signature;
  signature integrity is separate from distribution trust. No workaround that
  disables system security is part of this SDK's installation procedure.

These native/runtime limitations are tracked separately from Go package
installation and integration-test coverage.

## Versioning

The root Go module and the four platform modules have independent tags. A root
version pins exact native module versions and checksums. A Go-only change may
reuse the same native versions; changed archive bytes require a new immutable
native version. Never move an already published tag.

The public lifecycle API is the root `seekdb` package. Internal packages,
packaging scripts and archive layout are not application APIs. Major-version
changes to the Go API follow Go module versioning; this does not promise that a
new native engine can read every older data directory. Consult engine upgrade
guidance and back up data before changing native versions.
