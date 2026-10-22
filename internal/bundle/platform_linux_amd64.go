//go:build linux && amd64

package bundle

import native "github.com/oceanbase/seekdb-go/native/linux-amd64"

func platformBundle() []byte       { return native.Archive }
func platformLibrary() string      { return "libseekdb.so" }
func platformExecutable() string   { return "seekdb" }
func platformServerBinary() string { return "seekdb.bin" }
