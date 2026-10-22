//go:build !darwin && !linux && !windows

package seekdb

func lockNativeCache(string) (func(), error) {
	return func() {}, nil
}
