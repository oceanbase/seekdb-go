#!/usr/bin/env python3
"""Verify committed bundles, optionally against locally supplied runtime files."""

import argparse
import hashlib
import re
import tarfile
from pathlib import Path

from build_release_bundles import LABELS
from package_native import PLATFORMS, bundle_files

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(platform: str, readme: str, input_root: Path | None) -> None:
    archive_path = ROOT / "native" / platform / "bundle.tar.gz"
    label = LABELS[platform]
    match = re.search(rf"^\| {re.escape(label)} bundle \| `([0-9a-f]{{64}})` \|$", readme, re.M)
    if match is None:
        raise ValueError(f"missing README checksum for {platform}")
    actual = sha256_file(archive_path)
    if actual != match.group(1):
        raise ValueError(f"{platform}: bundle SHA-256 {actual} differs from README")

    library, executable = PLATFORMS[platform]
    required = {library, "seekdb.exe"} if platform == "windows-amd64" else {
        library, "seekdb", "seekdb.bin"
    }
    with tarfile.open(archive_path, "r:gz") as archive:
        entries = {}
        for entry in archive:
            if (not entry.isfile() or not entry.name or
                    entry.name in (".", "..") or "/" in entry.name or "\\" in entry.name or
                    entry.name in entries or entry.size == 0):
                raise ValueError(f"{platform}: invalid bundle entry {entry.name!r}")
            entries[entry.name] = entry
        if not required <= entries.keys():
            raise ValueError(f"{platform}: missing bundle entries {sorted(required - entries.keys())}")

        if input_root is not None:
            input_dir = input_root / platform
            files = bundle_files(platform, input_dir)
            expected = {
                ("seekdb.bin" if path.name == executable and platform != "windows-amd64" else path.name): path
                for path in files
            }
            expected_names = set(expected)
            if platform != "windows-amd64":
                expected_names.add("seekdb")  # Generated launcher.
            if entries.keys() != expected_names:
                raise ValueError(f"{platform}: bundle files differ from supplied runtime files")
            for name, path in expected.items():
                source = archive.extractfile(entries[name])
                if source is None:
                    raise ValueError(f"{platform}: cannot read {name} from bundle")
                digest = hashlib.sha256()
                with source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != sha256_file(path):
                    raise ValueError(f"{platform}: {name} differs from supplied runtime file")
    print(f"{platform}: verified {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path,
                        help="compare bundle contents with local platform runtime directories")
    args = parser.parse_args()
    input_root = args.input_root.resolve(strict=True) if args.input_root else None
    readme = (ROOT / "README.md").read_text()
    for platform in PLATFORMS:
        verify(platform, readme, input_root)


if __name__ == "__main__":
    main()
