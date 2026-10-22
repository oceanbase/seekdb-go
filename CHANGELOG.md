# Changelog

## v1.4.0

Initial Go SDK release for seekdb 1.4.0.0-r1.

- Embedded database lifecycle APIs: `Open`, `ConnectionOptions`, and `Close`.
- Native runtimes for macOS arm64, Linux amd64/arm64, and Windows amd64.
- A runnable SQL example with close/reopen persistence.

Requires Go 1.22+ and cgo.

### Known issues

- Windows fresh-database initialization can intermittently fail with native
  `OB_TIMEOUT`, tracked in
  [seekdb #1544](https://github.com/oceanbase/seekdb/issues/1544).

See [support](docs/support.md) for platform requirements, verified environments,
and other runtime limitations.
