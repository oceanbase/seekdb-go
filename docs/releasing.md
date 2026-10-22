# Releasing

Run the commands below from the repository root with Python 3.10+ and Go 1.22+.
For the local Go workspace and
checks to run before releasing, see [Development](development.md).

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

The build updates the bundle checksums in the [root README](../README.md).
It checks binary architectures, macOS library install names, and Linux `$ORIGIN`
dependencies.
Update the platform license and notice files when runtime dependencies change.
Each platform module has its own `go.mod` and is published by a tag prefixed
with its directory, for example
`native/linux-amd64/v1.4.0`. The root module uses a root tag such as `v1.4.0`.
Publish changed native bundles under new, immutable versions.

The initial native dependencies use Go pseudo-versions for an existing commit,
so `go get ...@latest` works before any release tags exist. Keep these immutable
pins and `go.sum` committed until a native tagged release is prepared.

Publishing has two stages:

1. Start from a clean checkout of the current remote `main`, after the Test CI
   passes. Run
   `scripts/release.sh ROOT_VERSION NATIVE_VERSION /path/to/release-inputs [REMOTE]`.
   It verifies the inputs, publishes the four immutable native tags, and updates
   `go.mod`/`go.sum` using direct fetching. If dependencies change, it stops
   **before publishing the root tag**. Commit the dependency files through a PR.
2. After merging that PR, wait for both Test and **Public install validation**
   on the exact main commit. The latter downloads the root commit through
   `proxy.golang.org` with `sum.golang.org`, using a separate consumer and fresh
   caches, and checks SQL persistence on all four platforms. Rerun the release
   command from that commit. It refuses root publication unless the latest main
   push runs of both workflows succeeded, and checks that remote main still matches.

The workflow gate reads the GitHub Actions API. For API rate limits, or a private
repository, set `GITHUB_TOKEN` or `GH_TOKEN` with Actions read permission. The
token is never passed as a command-line argument. A manual workflow run for some
other revision cannot satisfy the exact-main-commit release gate.

The public Go proxy may take time to observe newly published native tags. Wait
for successful public validation instead of bypassing it with `GOPRIVATE` or
reusing the release machine's module cache. Repeating the release command does
not move existing tags. Root `v*` tags trigger the same public-install validation
using the exact tag; before announcing a release, also dispatch it with `latest`
to verify the default user-facing selector.
