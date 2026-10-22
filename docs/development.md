# Development

Run these commands from the repository root. Go 1.22 or newer, cgo, and a C
compiler are required; see the [platform requirements](../README.md#install).

Copy the workspace template when testing changes to checked-out platform modules.
The generated `go.work` is ignored by Git:

```sh
cp go.work.dev go.work
go test ./...
```

Test the same pinned native modules that users download by bypassing the local
workspace (no native tags are required for the initial pseudo-versions):

```sh
GOWORK=off go test -mod=readonly -count=1 ./...
```

CI runs the checked-out module test on macOS arm64, Linux amd64/arm64, and
Windows amd64. The downloaded-module test is mandatory on every run. Release
script safety checks run with `python3 -m unittest discover -s scripts/tests -v`.

The public-install workflow runs on main and root version tags. It can also be
dispatched with a root version, commit SHA or `latest`. Reproduce it with Go,
a C compiler, Python 3.10+ and network access to the public Go proxy and sumdb:

```sh
python3 scripts/verify_install.py ROOT_VERSION_OR_COMMIT
```

The check creates a separate consumer module with fresh module/build caches,
disables local workspaces and private proxy bypasses, and verifies SQL data after
closing and reopening the database. It does not use a local `replace`. Failed
checks retain their working directory and diagnostics; CI uploads those logs.

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
