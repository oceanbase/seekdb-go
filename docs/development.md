# Development

Run these commands from the repository root. Go 1.22 or newer, cgo, and a C
compiler are required; see the [platform requirements](../README.md#install).

Copy the workspace template when testing changes to checked-out platform modules.
The generated `go.work` is ignored by Git:

```sh
cp go.work.dev go.work
go test ./...
```

After native module tags are published and `go.sum` is committed, test the same
tagged modules that users download by bypassing the local workspace:

```sh
GOWORK=off go test -count=1 ./...
```

CI runs the checked-out module test on macOS arm64, Linux amd64/arm64, and
Windows amd64. It runs the published module test when `go.sum` is present.

## Repository layout

- The root `seekdb` package owns the public API, argument validation and DB
  lifecycle synchronization. It exposes Go types and translates native errors
  into `*seekdb.Error`.
- `internal/native` wraps the C lifecycle API, loads the prepared library and
  copies native connection options into Go values. C types, allocations and the
  loader's C source and headers stay in this package.
- `internal/bundle` selects the platform module, validates or repairs the cached
  runtime and returns its library and executable paths. Platform file locks and
  archive-cache tests live alongside that implementation.
- `native/<platform>` contains the independently versioned resource modules.
  Their module paths, tag prefixes and embedded archive layout are part of the
  distribution contract.
- `scripts/` prepares, packages, verifies and releases the native bundles.
- `examples/lifecycle` demonstrates the public lifecycle API without requiring a
  SQL-driver dependency.

The dependency direction is `seekdb` -> `internal/native` -> `internal/bundle`
-> the selected `native/<platform>` module. Internal packages do not import the
public package.

## Tests and example

`go test ./...` runs the public API tests and internal cache tests, and compiles
the lifecycle example. API tests use `package seekdb_test` so they exercise the
same interface as a consuming application. Cache tests remain beside the code
whose extraction, integrity checking and repair behavior they verify.

Run the example with a writable database directory:

```sh
go run ./examples/lifecycle -db /path/to/database
```

It opens or reopens the database, prints the endpoint transport and closes its
handle. Choose a MySQL-protocol client to execute SQL, and close its connections
before closing the lifecycle handle.

For native bundle preparation and tagging, see [Releasing](releasing.md).
