//go:build !(darwin && arm64) && !(linux && amd64) && !(linux && arm64) && !(windows && amd64)

package bundle

func platformBundle() []byte       { return nil }
func platformLibrary() string      { return "" }
func platformExecutable() string   { return "" }
func platformServerBinary() string { return "" }
