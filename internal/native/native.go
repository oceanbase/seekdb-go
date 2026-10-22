// Package native wraps the libseekdb lifecycle API without exposing C types.
package native

/*
#cgo linux LDFLAGS: -ldl
#include <stdlib.h>
#include "native_loader.h"
*/
import "C"

import (
	"fmt"
	"sync"
	"unsafe"

	"github.com/oceanbase/seekdb-go/internal/bundle"
)

// Handle is an opaque native lifecycle handle. Its zero value is closed.
// Callers must serialize operations on each handle.
type Handle struct {
	value C.SeekdbHandle
}

// IsZero reports whether the handle is closed or uninitialized.
func (h Handle) IsZero() bool { return h.value == nil }

// ConnectionOptions copies endpoint fields borrowed from a native handle.
type ConnectionOptions struct {
	Transport  string
	User       string
	Host       string
	Port       uint
	UnixSocket string
	NamedPipe  string
}

// Error preserves a native return code and its diagnostic.
type Error struct {
	ReturnCode int
	Message    string
}

func (e *Error) Error() string { return e.Message }

var nativeMu sync.Mutex
var nativeReady bool

// Prepare loads the bundled library and configures its server executable.
// A failed attempt may be retried after the underlying problem is corrected.
func Prepare() error {
	nativeMu.Lock()
	defer nativeMu.Unlock()
	if nativeReady {
		return nil
	}

	paths, err := bundle.Prepare()
	if err != nil {
		return err
	}
	library := C.CString(paths.Library)
	defer C.free(unsafe.Pointer(library))
	var message [4096]C.char
	if rc := C.sdb_load(library, &message[0], C.size_t(len(message))); rc != C.SEEKDB_SUCCESS {
		return fmt.Errorf("load libseekdb: %s", C.GoString(&message[0]))
	}
	binary := C.CString(paths.Executable)
	defer C.free(unsafe.Pointer(binary))
	if rc := C.sdb_set_binary_path(binary); rc != C.SEEKDB_SUCCESS {
		return fmt.Errorf("set seekdb executable path: code %d", int(rc))
	}

	nativeReady = true
	return nil
}

// Open calls the prepared library with validated, alternating key/value strings.
func Open(dbDir string, pairs []string) (Handle, error) {
	cPairs := make([]*C.char, 0, len(pairs)+1)
	for _, value := range pairs {
		cPairs = append(cPairs, C.CString(value))
	}
	cPairs = append(cPairs, nil)
	defer func() {
		for _, value := range cPairs {
			C.free(unsafe.Pointer(value))
		}
	}()
	cDir := C.CString(dbDir)
	defer C.free(unsafe.Pointer(cDir))
	var handle C.SeekdbHandle
	var message [4096]C.char
	rc := C.sdb_open(cDir, (**C.char)(unsafe.Pointer(&cPairs[0])), &handle,
		&message[0], C.size_t(len(message)))
	if rc != C.SEEKDB_SUCCESS {
		if handle != nil {
			C.sdb_close(handle)
		}
		text := C.GoString(&message[0])
		if text == "" {
			text = "seekdb_open failed"
		}
		return Handle{}, &Error{ReturnCode: int(rc), Message: text}
	}
	return Handle{value: handle}, nil
}

// Options copies the connection options before their native storage can change.
func Options(handle Handle) (ConnectionOptions, error) {
	var options C.SeekdbConnectionOptions
	if rc := C.sdb_connection_options(handle.value, &options); rc != C.SEEKDB_SUCCESS {
		return ConnectionOptions{}, &Error{ReturnCode: int(rc), Message: "seekdb_connection_options failed"}
	}
	return ConnectionOptions{
		Transport:  C.GoString(options.transport),
		User:       C.GoString(options.user),
		Host:       C.GoString(options.host),
		Port:       uint(options.port),
		UnixSocket: C.GoString(options.unix_socket),
		NamedPipe:  C.GoString(options.named_pipe),
	}, nil
}

// Close releases the native handle.
func Close(handle Handle) error {
	if rc := C.sdb_close(handle.value); rc != C.SEEKDB_SUCCESS {
		return &Error{ReturnCode: int(rc), Message: "seekdb_close failed"}
	}
	return nil
}
