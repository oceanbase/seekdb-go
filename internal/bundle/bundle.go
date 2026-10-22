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
	"os"
	"path/filepath"
	"runtime"
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
	if bundleReady(target, bundleHash) {
		return target, nil
	}
	unlock, err := lockNativeCache(root)
	if err != nil {
		return "", fmt.Errorf("lock native cache: %w", err)
	}
	defer unlock()
	if bundleReady(target, bundleHash) {
		return target, nil
	}
	temp, err := os.MkdirTemp(root, ".extract-")
	if err != nil {
		return "", fmt.Errorf("create extraction directory: %w", err)
	}
	defer os.RemoveAll(temp)
	if err := extractArchive(temp, archive, bundleHash); err != nil {
		return "", err
	}
	if !bundleReady(temp, bundleHash) {
		return "", errors.New("native bundle extraction failed validation")
	}
	if err := os.RemoveAll(target); err != nil {
		return "", fmt.Errorf("replace incomplete native cache: %w", err)
	}
	if err := os.Rename(temp, target); err != nil {
		return "", fmt.Errorf("install native bundle: %w", err)
	}
	return target, nil
}

func validBundleName(name string) bool {
	return name != "" && name != "." && name != ".." && name != manifestName &&
		!strings.ContainsAny(name, `/\\`)
}

func bundleReady(dir, bundleHash string) bool {
	data, err := os.ReadFile(filepath.Join(dir, manifestName))
	if err != nil {
		return false
	}
	var manifest bundleManifest
	if err := json.Unmarshal(data, &manifest); err != nil || manifest.BundleSHA256 != bundleHash {
		return false
	}
	for _, name := range []string{platformLibrary(), platformExecutable(), platformServerBinary()} {
		if name == "" {
			return false
		}
		if _, ok := manifest.Files[name]; !ok {
			return false
		}
	}
	for name, expected := range manifest.Files {
		if !validBundleName(name) || expected.Size < 0 {
			return false
		}
		path := filepath.Join(dir, name)
		info, err := os.Lstat(path)
		if err != nil || !info.Mode().IsRegular() || info.Size() != expected.Size {
			return false
		}
		if runtime.GOOS != "windows" &&
			(name == platformLibrary() || name == platformExecutable() || name == platformServerBinary()) &&
			info.Mode().Perm()&0111 == 0 {
			return false
		}
		file, err := os.Open(path)
		if err != nil {
			return false
		}
		hash := sha256.New()
		_, copyErr := io.Copy(hash, file)
		closeErr := file.Close()
		if copyErr != nil || closeErr != nil || hex.EncodeToString(hash.Sum(nil)) != expected.SHA256 {
			return false
		}
	}
	return true
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
		if !validBundleName(name) || header.Typeflag != tar.TypeReg {
			return fmt.Errorf("invalid native bundle entry %q", name)
		}
		mode := os.FileMode(header.Mode) & 0777
		file, err := os.OpenFile(filepath.Join(dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL, mode)
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
