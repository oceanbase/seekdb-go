//go:build !darwin && !linux && !windows

package bundle

func lockNativeCache(string) (func(), error) {
	return func() {}, nil
}
