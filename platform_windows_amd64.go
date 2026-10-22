//go:build windows && amd64

package seekdb

import native "github.com/oceanbase/seekdb-go/native/windows-amd64"

func platformBundle() []byte       { return native.Archive }
func platformLibrary() string      { return "seekdb.dll" }
func platformExecutable() string   { return "seekdb.exe" }
func platformServerBinary() string { return "seekdb.exe" }
