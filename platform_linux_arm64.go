//go:build linux && arm64

package seekdb

import native "github.com/oceanbase/seekdb-go/native/linux-arm64"

func platformBundle() []byte       { return native.Archive }
func platformLibrary() string      { return "libseekdb.so" }
func platformExecutable() string   { return "seekdb" }
func platformServerBinary() string { return "seekdb.bin" }
