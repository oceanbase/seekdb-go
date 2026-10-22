//go:build (darwin && arm64) || (linux && amd64) || (linux && arm64) || (windows && amd64)

package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

func testBundle(t *testing.T) []byte {
	t.Helper()
	var compressed bytes.Buffer
	gz := gzip.NewWriter(&compressed)
	tw := tar.NewWriter(gz)
	for name, contents := range map[string]string{
		platformLibrary():    "library",
		platformExecutable(): "#!/bin/sh\n",
		"seekdb.bin":         "binary",
		"libruntime.so":      "runtime",
	} {
		header := &tar.Header{Name: name, Mode: 0755, Size: int64(len(contents)), Typeflag: tar.TypeReg}
		if err := tw.WriteHeader(header); err != nil {
			t.Fatal(err)
		}
		if _, err := tw.Write([]byte(contents)); err != nil {
			t.Fatal(err)
		}
	}
	if err := tw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := gz.Close(); err != nil {
		t.Fatal(err)
	}
	return compressed.Bytes()
}

func TestInstallBundleRepairsIncompleteCache(t *testing.T) {
	archive := testBundle(t)
	root := t.TempDir()
	target, err := installBundle(root, archive)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(target, "libruntime.so")); err != nil {
		t.Fatal(err)
	}
	if _, err := installBundle(root, archive); err != nil {
		t.Fatalf("repair missing runtime library: %v", err)
	}
	contents, err := os.ReadFile(filepath.Join(target, "libruntime.so"))
	if err != nil || string(contents) != "runtime" {
		t.Fatalf("restored runtime library = %q, %v", contents, err)
	}
	if err := os.WriteFile(filepath.Join(target, "libruntime.so"), []byte("broken!"), 0755); err != nil {
		t.Fatal(err)
	}
	if _, err := installBundle(root, archive); err != nil {
		t.Fatalf("repair corrupted runtime library: %v", err)
	}
	contents, err = os.ReadFile(filepath.Join(target, "libruntime.so"))
	if err != nil || string(contents) != "runtime" {
		t.Fatalf("restored runtime library = %q, %v", contents, err)
	}
}

func TestInstallBundleRetriesAfterCacheError(t *testing.T) {
	archive := testBundle(t)
	root := filepath.Join(t.TempDir(), "cache")
	if err := os.WriteFile(root, []byte("occupied"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := installBundle(root, archive); err == nil {
		t.Fatal("installBundle succeeded with a file at the cache path")
	}
	if err := os.Remove(root); err != nil {
		t.Fatal(err)
	}
	if _, err := installBundle(root, archive); err != nil {
		t.Fatalf("retry after fixing cache path: %v", err)
	}
}

func TestInstallBundleUsesReadOnlyCompleteCache(t *testing.T) {
	archive := testBundle(t)
	root := t.TempDir()
	if _, err := installBundle(root, archive); err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(filepath.Join(root, ".lock")); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(root, 0500); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { os.Chmod(root, 0700) })
	if _, err := installBundle(root, archive); err != nil {
		t.Fatalf("use complete cache without write permission: %v", err)
	}
}

func TestInstallBundleConcurrentProcesses(t *testing.T) {
	if root := os.Getenv("SEEKDB_CACHE_TEST_ROOT"); root != "" {
		archive, err := os.ReadFile(os.Getenv("SEEKDB_CACHE_TEST_ARCHIVE"))
		if err != nil {
			t.Fatal(err)
		}
		target, err := installBundle(root, archive)
		if err != nil {
			t.Fatal(err)
		}
		contents, err := os.ReadFile(filepath.Join(target, "libruntime.so"))
		if err != nil || string(contents) != "runtime" {
			t.Fatalf("installed runtime = %q, %v", contents, err)
		}
		return
	}
	root := t.TempDir()
	archivePath := filepath.Join(root, "bundle.tar.gz")
	if err := os.WriteFile(archivePath, testBundle(t), 0600); err != nil {
		t.Fatal(err)
	}
	executable, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	start := make(chan struct{})
	results := make(chan error, 4)
	for i := 0; i < 4; i++ {
		go func() {
			<-start
			command := exec.CommandContext(ctx, executable, "-test.run=^TestInstallBundleConcurrentProcesses$")
			command.Env = append(os.Environ(), "SEEKDB_CACHE_TEST_ROOT="+filepath.Join(root, "cache"), "SEEKDB_CACHE_TEST_ARCHIVE="+archivePath)
			output, err := command.CombinedOutput()
			if err != nil {
				err = fmt.Errorf("cache installer: %w\n%s", err, output)
			}
			results <- err
		}()
	}
	close(start)
	for i := 0; i < 4; i++ {
		if err := <-results; err != nil {
			t.Error(err)
		}
	}
	entries, err := os.ReadDir(filepath.Join(root, "cache"))
	if err != nil {
		t.Fatal(err)
	}
	// Exactly one complete hash directory and the persistent lock should remain.
	if len(entries) != 2 {
		t.Fatalf("concurrent extraction left %d cache entries, want 2", len(entries))
	}
}
