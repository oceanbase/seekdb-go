# seekdb Go bindings

This package manages an embedded seekdb server through the `libseekdb` C API.
It provides `Open`, `ConnectionOptions`, and `Close`. Use a MySQL protocol
driver of your choice for SQL queries.

## Install

```sh
go get github.com/oceanbase/seekdb-go@latest
```

To pin a version of the root module:

```sh
go get github.com/oceanbase/seekdb-go@v1.4.0
```

The root SDK pins all four native modules, with checksums in `go.sum`. Root SDK
and native versions are independent, so a Go-only release can reuse existing native versions.
See the [changelog](CHANGELOG.md) for the release contents and known issues.

Building requires Go 1.22 or newer, `CGO_ENABLED=1`, and a C compiler targeting
the same OS and architecture as Go:

| Target | Build compiler | Native runtime requirements |
| --- | --- | --- |
| macOS arm64 | Apple clang / Xcode Command Line Tools | macOS 15.0+ |
| Linux amd64/arm64 | GCC or clang for the target architecture | glibc 2.28+; musl/Alpine is unsupported |
| Windows amd64 | MinGW-w64 GCC targeting x86_64 | x64 Windows 10+, with Visual C++ runtime DLLs included in the bundle |

On Windows, put MinGW-w64 GCC on `PATH` and set `CC=gcc` and `CGO_ENABLED=1`
in the build environment.
See [support and known limitations](docs/support.md) for tested environments
and the distinction between binary requirements and runtime verification.
For Linux deployment to glibc 2.28, compile the cgo application against that
baseline too; a newer build host can introduce newer libc requirements.

```go
package main

import (
    "log"

    seekdb "github.com/oceanbase/seekdb-go"
)

func main() {
    db, err := seekdb.Open("./data")
    if err != nil {
        log.Fatal(err)
    }
    defer db.Close()

    endpoint, err := db.ConnectionOptions()
    if err != nil {
        log.Fatal(err)
    }
    log.Printf("seekdb transport: %s", endpoint.Transport)
    // Connect to endpoint with a MySQL protocol client.
}
```

`Open` creates the database directory when needed and reopens existing data.
Close SQL client connections before calling `Close`.

## SQL example

The [complete SQL example](examples/sql) uses `go-sql-driver/mysql` and connects
using the fields returned by `ConnectionOptions`. The current POSIX bundles
return a Unix socket. The current Windows bundle defaults to TCP on
`127.0.0.1` with a dynamically selected port. Do not hard-code a named pipe or
port number.

From a checkout, run:

```sh
cd examples/sql
go run -mod=readonly . -db ../../sql-example-data
```

It creates a table, inserts parameterized Unicode text, closes the SQL client
and database, reopens the database, and checks the persisted value. Its separate
Go module keeps SQL-driver dependencies out of the core SDK. See the
[example instructions](examples/sql/README.md) for use in your own application.

## Native modules

The repository contains four separately versioned native Go modules:

| Target | Module | Bundle |
| --- | --- | ---: |
| macOS arm64 | `github.com/oceanbase/seekdb-go/native/darwin-arm64` | 48.6 MB |
| Linux amd64 | `github.com/oceanbase/seekdb-go/native/linux-amd64` | 53.9 MB |
| Linux arm64 | `github.com/oceanbase/seekdb-go/native/linux-arm64` | 49.1 MB |
| Windows amd64 | `github.com/oceanbase/seekdb-go/native/windows-amd64` | 48.5 MB |

Each module carries a `bundle.tar.gz` with a prebuilt seekdb executable,
`libseekdb` shared library, and required runtime libraries. The `.so`/`.dylib`/`.dll`
is needed by the Go binding and is small compared with the seekdb executable.
The Go build selects the matching module using build constraints and embeds its
bundle in the resulting program. At the first `Open`, the program extracts the
files under the user cache directory (`seekdb-go/<bundle SHA-256>/`) and loads
`libseekdb`. The cache is validated on first use in each process and rebuilt
if files are missing or damaged. `Open` does not download files.

Go downloads native modules from its normal module proxy or this GitHub
repository. A fresh `go get` can download all four platform bundles because the
root module declares all four dependencies; the build embeds only the selected
platform. A new native release uses a new module tag;
existing `go.mod` and `go.sum` files keep applications on their selected
version until they upgrade it.

The bundles in this checkout are the four `libseekdb` archives from
[seekdb-bindings v1.4.1](https://github.com/oceanbase/seekdb-bindings/releases/tag/v1.4.1).
They contain seekdb 1.4.1.0, its runtime resources and licenses, and the build
provenance in `BUILD-INFO.json`.
CI runs `Open`, `ConnectionOptions`, `Close`, and reopen tests on all four target
platforms using checked-out bundles. CI also always tests downloaded native
modules with the workspace disabled. A separate public-install workflow uses
fresh module and build caches to download the root module. Both paths run real
SQL integration checks for prepared statements, Unicode, CRUD, transaction
commit/rollback, vector queries, shared handles and persisted data after
reopening. The checks use the transport returned by `ConnectionOptions`.
The sample includes a Windows named-pipe adapter for endpoints that request it;
the shipped Windows bundle and current integration coverage use TCP.

| Bundle | SHA-256 |
| --- | --- |
| macOS arm64 bundle | `c56a78f9b8deb391d9ec6b50033378a671f5cb1f46c6ce14b191859ed0718eda` |
| Linux amd64 bundle | `55fbd0f5e70f570f29483cadb36306f4462893bf1abc8db2dddb70a163ad3450` |
| Linux arm64 bundle | `5e564f7103f44e176db8759d3f22a0555c9d31bbc4bb81b891211b555aac79ae` |
| Windows amd64 bundle | `f135d04bf52f98e06eca07cb469a7fd56fd6c842328756dc8b0cdcb297ab7728` |

## Cache cleanup

The extracted runtime lives under `seekdb-go/<bundle SHA-256>/` in Go's user
cache directory:

| Platform | Cache directory |
| --- | --- |
| macOS | `$HOME/Library/Caches/seekdb-go` |
| Linux | `$XDG_CACHE_HOME/seekdb-go`, or `$HOME/.cache/seekdb-go` when unset |
| Windows | `%LocalAppData%\seekdb-go` |

Old bundle directories are not removed automatically. After all programs using
seekdb have exited, delete obsolete SHA-256-named subdirectories to reclaim
space. Keep the directory for the bundle currently in use; its hash appears in
the table above. Deleting a cache directory never deletes the database passed
to `Open`. If the current cache is removed after the program exits, the next
`Open` extracts it again. Leave the `.lock` file in place.

## Development

See [Development](docs/development.md) for the repository layout, local workspace,
tests and [lifecycle example](examples/lifecycle/main.go). See
[Releasing](docs/releasing.md) for preparing native bundles and publishing tags.

The checksum table above stays in this README because the packaging and
verification scripts update and read it.
