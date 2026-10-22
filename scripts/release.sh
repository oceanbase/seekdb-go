#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ] ||
   [[ ! "$1" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
   [[ ! "$2" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "usage: scripts/release.sh ROOT_VERSION NATIVE_VERSION INPUT_ROOT [REMOTE]" >&2
    exit 2
fi

root_version="$1"
native_version="$2"
if [ ! -d "$3" ]; then
    echo "missing input directory: $3" >&2
    exit 1
fi
input_root="$(cd "$3" && pwd)"
remote="${4:-origin}"
root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [ "$(git branch --show-current)" != "main" ]; then
    echo "release must run from main" >&2
    exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
    echo "release requires a clean worktree" >&2
    exit 1
fi

python3 scripts/verify_bundles.py --input-root "$input_root"
git fetch --quiet --tags "$remote"

platforms=(darwin-arm64 linux-amd64 linux-arm64 windows-amd64)
if git rev-parse -q --verify "refs/tags/${root_version}" >/dev/null &&
   [ "$(git rev-parse "refs/tags/${root_version}^{commit}")" != "$(git rev-parse HEAD)" ]; then
    echo "${root_version} already points to a different commit" >&2
    exit 1
fi

for platform in "${platforms[@]}"; do
    tag="native/${platform}/${native_version}"
    directory="native/${platform}"
    if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null &&
       ! git diff --quiet "refs/tags/${tag}" HEAD -- "$directory"; then
        echo "${tag} already exists with different ${directory} contents" >&2
        exit 1
    fi
done

tag_refs=()
for platform in "${platforms[@]}"; do
    tag="native/${platform}/${native_version}"
    if ! git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
        git tag "$tag"
    fi
    tag_refs+=("refs/tags/${tag}")
done
git push "$remote" "${tag_refs[@]}"

# Direct fetch avoids waiting for a newly pushed platform tag to reach a module proxy.
export GOWORK=off
module_path="$(go list -m)"
export GOPRIVATE="${GOPRIVATE:+${GOPRIVATE},}${module_path}"
for platform in "${platforms[@]}"; do
    go mod edit -require="${module_path}/native/${platform}@${native_version}"
done
go mod tidy
if [ -n "$(git status --porcelain -- go.mod go.sum)" ]; then
    echo "Root dependencies changed. Commit go.mod and go.sum through a PR, then rerun this script." >&2
    exit 1
fi

go test -count=1 ./...
if ! git rev-parse -q --verify "refs/tags/${root_version}" >/dev/null; then
    git tag "$root_version"
fi
git push "$remote" "refs/tags/${root_version}"
echo "Published ${root_version} with native modules ${native_version}"
