// Package bundle prepares the platform's bundled runtime in the user cache.
package bundle

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"strings"
)

const manifestName = ".seekdb-bundle.json"

type bundleFile struct {
	Size   int64  `json:"size"`
	SHA256 string `json:"sha256"`
}

type bundleManifest struct {
	BundleSHA256 string                `json:"bundle_sha256"`
	Files        map[string]bundleFile `json:"files"`
}

// Paths identifies the extracted native library and server executable.
type Paths struct {
	Library    string
	Executable string
}

// Prepare validates or repairs the cached runtime and returns its file paths.
func Prepare() (Paths, error) {
	archive := platformBundle()
	if len(archive) == 0 {
		return Paths{}, fmt.Errorf("seekdb has no native bundle for this platform")
	}
	cacheRoot, err := os.UserCacheDir()
	if err != nil {
		return Paths{}, fmt.Errorf("find cache directory: %w", err)
	}
	dir, err := installBundle(filepath.Join(cacheRoot, "seekdb-go"), archive)
	if err != nil {
		return Paths{}, err
	}
	return Paths{
		Library:    filepath.Join(dir, platformLibrary()),
		Executable: filepath.Join(dir, platformExecutable()),
	}, nil
}

func installBundle(root string, archive []byte) (string, error) {
	checksum := sha256.Sum256(archive)
	bundleHash := hex.EncodeToString(checksum[:])
	if err := os.MkdirAll(root, 0700); err != nil {
		return "", fmt.Errorf("create native cache: %w", err)
	}
	target := filepath.Join(root, bundleHash)
	if runtimeDir := cachedRuntimeDir(target, bundleHash); runtimeDir != "" {
		return filepath.Join(target, runtimeDir), nil
	}
	unlock, err := lockNativeCache(root)
	if err != nil {
		return "", fmt.Errorf("lock native cache: %w", err)
	}
	defer unlock()
	if runtimeDir := cachedRuntimeDir(target, bundleHash); runtimeDir != "" {
		return filepath.Join(target, runtimeDir), nil
	}
	temp, err := os.MkdirTemp(root, ".extract-")
	if err != nil {
		return "", fmt.Errorf("create extraction directory: %w", err)
	}
	defer os.RemoveAll(temp)
	if err := extractArchive(temp, archive, bundleHash); err != nil {
		return "", err
	}
	runtimeDir := cachedRuntimeDir(temp, bundleHash)
	if runtimeDir == "" {
		return "", errors.New("native bundle extraction failed validation")
	}
	if err := os.RemoveAll(target); err != nil {
		return "", fmt.Errorf("replace incomplete native cache: %w", err)
	}
	if err := os.Rename(temp, target); err != nil {
		return "", fmt.Errorf("install native bundle: %w", err)
	}
	return filepath.Join(target, runtimeDir), nil
}

func validBundleName(name string) bool {
	return name != "." && name != manifestName && fs.ValidPath(name) &&
		!strings.ContainsAny(name, `\:`) && filepath.IsLocal(filepath.FromSlash(name))
}

func cachedRuntimeDir(dir, bundleHash string) string {
	if info, err := os.Lstat(dir); err != nil || !info.IsDir() {
		return ""
	}
	data, err := os.ReadFile(filepath.Join(dir, manifestName))
	if err != nil {
		return ""
	}
	var manifest bundleManifest
	if err := json.Unmarshal(data, &manifest); err != nil || manifest.BundleSHA256 != bundleHash {
		return ""
	}
	runtimeDir := "."
	required := []string{platformLibrary(), platformExecutable(), platformServerBinary()}
	if _, ok := manifest.Files["lib/"+platformLibrary()]; ok {
		runtimeDir = "lib"
		required = []string{"lib/" + platformLibrary(), "lib/" + platformExecutable()}
	}
	for _, name := range required {
		if _, ok := manifest.Files[name]; !ok || name == "" {
			return ""
		}
	}
	for name, expected := range manifest.Files {
		if !validBundleName(name) || expected.Size < 0 {
			return ""
		}
		path := filepath.Join(dir, filepath.FromSlash(name))
		for parent := filepath.Dir(path); parent != dir; parent = filepath.Dir(parent) {
			if info, err := os.Lstat(parent); err != nil || !info.IsDir() {
				return ""
			}
		}
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Size() != expected.Size {
			return ""
		}
		if runtime.GOOS != "windows" && slices.Contains(required, name) && info.Mode().Perm()&0111 == 0 {
			return ""
		}
		file, err := os.Open(path)
		if err != nil {
			return ""
		}
		hash := sha256.New()
		_, copyErr := io.Copy(hash, file)
		closeErr := file.Close()
		if copyErr != nil || closeErr != nil || hex.EncodeToString(hash.Sum(nil)) != expected.SHA256 {
			return ""
		}
	}
	return runtimeDir
}

func extractArchive(dir string, archive []byte, bundleHash string) error {
	gz, err := gzip.NewReader(bytes.NewReader(archive))
	if err != nil {
		return fmt.Errorf("read native bundle: %w", err)
	}
	defer gz.Close()
	tr := tar.NewReader(gz)
	manifest := bundleManifest{BundleSHA256: bundleHash, Files: make(map[string]bundleFile)}
	for {
		header, err := tr.Next()
		if errors.Is(err, io.EOF) {
			data, err := json.Marshal(manifest)
			if err != nil {
				return fmt.Errorf("encode native bundle manifest: %w", err)
			}
			if err := os.WriteFile(filepath.Join(dir, manifestName), data, 0600); err != nil {
				return fmt.Errorf("write native bundle manifest: %w", err)
			}
			return nil
		}
		if err != nil {
			return fmt.Errorf("read native bundle entry: %w", err)
		}
		name := header.Name
		if header.Typeflag == tar.TypeDir && validBundleName(strings.TrimSuffix(name, "/")) {
			continue
		}
		if !validBundleName(name) || header.Typeflag != tar.TypeReg {
			return fmt.Errorf("invalid native bundle entry %q", name)
		}
		path := filepath.Join(dir, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
			return fmt.Errorf("create directory for native file %q: %w", name, err)
		}
		mode := os.FileMode(header.Mode) & 0777
		file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
		if err != nil {
			return fmt.Errorf("create native file %q: %w", name, err)
		}
		hash := sha256.New()
		size, copyErr := io.Copy(file, io.TeeReader(tr, hash))
		closeErr := file.Close()
		if copyErr != nil {
			return fmt.Errorf("extract native file %q: %w", name, copyErr)
		}
		if closeErr != nil {
			return fmt.Errorf("close native file %q: %w", name, closeErr)
		}
		if size != header.Size {
			return fmt.Errorf("native file %q has unexpected size", name)
		}
		manifest.Files[name] = bundleFile{Size: size, SHA256: hex.EncodeToString(hash.Sum(nil))}
	}
}
