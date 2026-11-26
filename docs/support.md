# Support and known limitations

## Platforms

The native `v1.4.1` modules embed seekdb 1.4.1.0. Go 1.22+ and cgo are
required. The runtime defaults to `memory_budget=1G` and `log_disk_size=2G`
on first initialization; allow additional process memory and disk space.

| Platform | Binary requirement | Functional verification environment |
| --- | --- | --- |
| macOS arm64 | macOS 15.0+ | CI: macos-26 |
| Linux amd64 | glibc 2.28+ | CI: Ubuntu 24.04 |
| Linux arm64 | glibc 2.28+ | CI: Ubuntu 24.04 arm64 |
| Windows amd64 | x64 Windows 10 or later | CI: windows-2025 |

The binary requirements come from the published C SDK build manifests. The
runner versions in the table are the environments exercised by Go CI. The
available bundles cover macOS arm64, Linux glibc amd64/arm64 and Windows amd64.

A Linux application built with cgo also inherits requirements from its build
compiler and libc. Build against the oldest glibc you intend to support. For
example, the test executable linked on the glibc 2.32 host required GLIBC_2.32;
rebuilding it inside glibc 2.28 allowed the same integration suite to pass there.
The native bundle's baseline alone cannot lower an application's link target.

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

- The v1.4.0 Windows bundle could intermittently fail fresh-database bootstrap with native
  `OB_TIMEOUT (-4012)`, after which the server exits before becoming ready.
  It is tracked in [seekdb #1544](https://github.com/oceanbase/seekdb/issues/1544).
  A later successful run does not establish that this native issue is fixed.
- A v1.4.0 macOS first-execution failure was associated with interrupted system trust
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
