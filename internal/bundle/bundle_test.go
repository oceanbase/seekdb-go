//go:build (darwin && arm64) || (linux && amd64) || (linux && arm64) || (windows && amd64)

package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"os"
	"path/filepath"
	"testing"
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
