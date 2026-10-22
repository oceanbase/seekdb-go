package seekdb

import (
	"errors"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/oceanbase/seekdb-go/internal/native"
)

// OpenOptions supplies seekdb server parameters. Ordinary values apply on first initialization.
type OpenOptions struct {
	Parameters map[string]string
}

// ConnectionOptions describes the local endpoint while a DB handle is open.
type ConnectionOptions struct {
	Transport  string
	User       string
	Host       string
	Port       uint
	UnixSocket string
	NamedPipe  string
}

// Error reports a failure from libseekdb.
type Error struct {
	ReturnCode int
	Message    string
}

func (e *Error) Error() string { return e.Message }

// DB owns a local seekdb lifecycle handle. Close client connections before Close.
type DB struct {
	mu     sync.Mutex
	handle native.Handle
	DBDir  string
}

// Open starts or reuses a local seekdb instance rooted at dbDir.
func Open(dbDir string, options ...OpenOptions) (*DB, error) {
	if dbDir == "" {
		return nil, errors.New("dbDir must not be empty")
	}
	if strings.ContainsRune(dbDir, 0) {
		return nil, errors.New("dbDir must not contain NUL")
	}
	if len(options) > 1 {
		return nil, errors.New("pass at most one OpenOptions value")
	}
	absolute, err := filepath.Abs(dbDir)
	if err != nil {
		return nil, fmt.Errorf("resolve dbDir: %w", err)
	}
	if err := native.Prepare(); err != nil {
		return nil, err
	}
	var parameters map[string]string
	if len(options) == 1 {
		parameters = options[0].Parameters
	}
	keys := make([]string, 0, len(parameters))
	for key := range parameters {
		if key == "" {
			return nil, errors.New("parameter keys must not be empty")
		}
		if strings.ContainsRune(key, 0) || strings.ContainsRune(parameters[key], 0) {
			return nil, errors.New("parameter keys and values must not contain NUL")
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)
	pairs := make([]string, 0, 2*len(keys))
	for _, key := range keys {
		pairs = append(pairs, key, parameters[key])
	}
	handle, err := native.Open(absolute, pairs)
	if err != nil {
		return nil, publicError(err)
	}
	return &DB{handle: handle, DBDir: absolute}, nil
}

// ConnectionOptions returns fields for a caller-owned MySQL-protocol client.
func (db *DB) ConnectionOptions() (ConnectionOptions, error) {
	db.mu.Lock()
	defer db.mu.Unlock()
	if db.handle.IsZero() {
		return ConnectionOptions{}, errors.New("seekdb is closed")
	}
	options, err := native.Options(db.handle)
	if err != nil {
		return ConnectionOptions{}, publicError(err)
	}
	return ConnectionOptions(options), nil
}

// Close releases this handle; repeated calls are harmless. It does not delete data.
func (db *DB) Close() error {
	db.mu.Lock()
	defer db.mu.Unlock()
	if db.handle.IsZero() {
		return nil
	}
	err := native.Close(db.handle)
	db.handle = native.Handle{}
	return publicError(err)
}

func publicError(err error) error {
	if nativeErr, ok := err.(*native.Error); ok {
		return &Error{ReturnCode: nativeErr.ReturnCode, Message: nativeErr.Message}
	}
	return err
}
