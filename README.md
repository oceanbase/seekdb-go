# seekdb Go bindings

This package manages an embedded seekdb server through the `libseekdb` C API.
It provides `Open`, `ConnectionOptions`, and `Close`. Use a MySQL protocol
driver of your choice for SQL queries.

## Install

After the native modules and root module have been tagged in this repository:

```sh
go get github.com/oceanbase/seekdb-go@latest
```

Building requires Go 1.22 or newer, `CGO_ENABLED=1`, and a C compiler. Native
bundles are available for macOS arm64, Linux amd64/arm64, and Windows amd64.
The current macOS arm64 bundle requires macOS 15.6.1 or newer.
The Linux bundles require glibc 2.28 or newer and do not support musl/Alpine.
The Windows bundle requires the Microsoft Visual C++ runtime.

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

## Native modules

The repository contains four separately versioned native Go modules:

| Target | Module | Bundle |
| --- | --- | ---: |
| macOS arm64 | `github.com/oceanbase/seekdb-go/native/darwin-arm64` | 52.0 MB |
| Linux amd64 | `github.com/oceanbase/seekdb-go/native/linux-amd64` | 53.6 MB |
| Linux arm64 | `github.com/oceanbase/seekdb-go/native/linux-arm64` | 49.2 MB |
| Windows amd64 | `github.com/oceanbase/seekdb-go/native/windows-amd64` | 64.9 MB |

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

The current bundles use seekdb 1.4.0.0-r1 runtime files. The Linux bundles
include OpenSSL 1.1, libaio, and zlib.
CI runs `Open`, `ConnectionOptions`, `Close`, and reopen tests on all four target
platforms using checked-out bundles. Once the official native module tags and
`go.sum` are present, CI also tests published native modules. The Windows test
checks that the named pipe endpoint is present; it does not yet connect a MySQL
protocol client through that pipe.

| Bundle | SHA-256 |
| --- | --- |
| macOS arm64 bundle | `8267306ccd5e38076df790b025f01b0f403f9524bc98529573eac0e305e8c583` |
| Linux amd64 bundle | `73bae794192b643a4b836cedb1b7f6dd5b7fa5210654d57b804bdc74fe2d1cc7` |
| Linux arm64 bundle | `91b28ab4e0c4c15bab1c7972aec212c9aaee19bc0ce57e25fbff62d2763ca647` |
| Windows amd64 bundle | `3a50225198ac67f26f1777dd02cd6a5357ceb0a7ed33fa78db05a2e7a33af295` |

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

## Develop and release

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

Builds take local runtime files. Arrange them by target platform, with the
seekdb executable, the matching `libseekdb` shared library, and all required
runtime libraries in each directory:

```text
release-inputs/
  darwin-arm64/    seekdb  libseekdb.dylib  other *.dylib
  linux-amd64/    seekdb  libseekdb.so     other *.so.*
  linux-arm64/    seekdb  libseekdb.so     other *.so.*
  windows-amd64/  seekdb.exe  seekdb.dll   other *.dll
```

On macOS or Linux, `prepare_native_bundle.py` can stage a supplied executable
and library on the target machine, collecting their local dependencies. It uses
`otool` and `install_name_tool` on macOS, or `ldd`, `patchelf`, and `objdump`
on Linux. Use `--library-dir` for dependencies outside the support directory:

```sh
python3 scripts/prepare_native_bundle.py linux-amd64 /path/to/support \
  /path/to/release-inputs/linux-amd64 --seekdb-bin /path/to/seekdb \
  --library-dir /path/to/openssl/lib
```

Windows inputs must already contain the executable, shared library, and their
runtime DLLs. Building all four bundles on one host requires macOS with
`otool` and `lipo`, plus `patchelf` for the Linux binaries. Build the checked-in
bundles from these local directories:

```sh
python3 scripts/build_release_bundles.py /path/to/release-inputs
python3 scripts/verify_bundles.py --input-root /path/to/release-inputs
```

The build updates the bundle checksums in this README. It checks binary
architectures, macOS library install names, and Linux `$ORIGIN` dependencies.
Update the platform license and notice files when runtime dependencies change.
Each platform module has its own `go.mod` and is published by a tag prefixed
with its directory, for example
`native/linux-amd64/v1.4.0`. The root module uses a root tag such as `v1.4.0`.
Publish changed native bundles under new, immutable versions.

After CI passes on `main`, run
`scripts/release.sh ROOT_VERSION NATIVE_VERSION /path/to/release-inputs [REMOTE]`.
The script compares every bundled native file with the supplied local inputs,
publishes immutable platform tags, updates the root `go.mod` and `go.sum`, and
tests the tagged dependencies. If those dependency files change, commit them
through a PR and rerun the script after merging; it then publishes the root
tag. Repeating the command does not move existing tags.
