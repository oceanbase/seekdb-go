# Changelog

## v1.4.1

- Embed SeekDB 1.4.1.0 from `ab58f3d233bc` and libseekdb from `0d1cd473db05`.
- Pin all four platform modules at `v1.4.1`. Each bundle preserves the official
  C SDK layout, runtime resources and license notices.

SeekDB 1.4.1 changes the local storage format. Export schema and data from the
earlier engine, then import them into a new 1.4.1 database. See the
[SeekDB upgrade notes](https://github.com/oceanbase/seekdb/releases/tag/v1.4.1#upgrade-notes).

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
