package native

import _ "embed"

// Archive contains seekdb.exe, seekdb.dll, and their runtime DLLs.
//
//go:embed bundle.tar.gz
var Archive []byte
