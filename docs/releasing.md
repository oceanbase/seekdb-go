# Releasing

Run the commands below from the repository root. For the local Go workspace and
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

After CI passes on `main`, run
`scripts/release.sh ROOT_VERSION NATIVE_VERSION /path/to/release-inputs [REMOTE]`.
The script compares every bundled native file with the supplied local inputs,
publishes immutable platform tags, updates the root `go.mod` and `go.sum`, and
tests the tagged dependencies. If those dependency files change, commit them
through a PR and rerun the script after merging; it then publishes the root
tag. Repeating the command does not move existing tags.
