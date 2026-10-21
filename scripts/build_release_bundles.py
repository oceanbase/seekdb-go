#!/usr/bin/env python3
"""Build native Go bundles from locally supplied platform runtime files."""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

from package_native import PLATFORMS

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    "darwin-arm64": "macOS arm64",
    "linux-amd64": "Linux amd64",
    "linux-arm64": "Linux arm64",
    "windows-amd64": "Windows amd64",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_readme(checksums: dict[str, str]) -> None:
    path = ROOT / "README.md"
    readme = path.read_text()
    for platform, checksum in checksums.items():
        label = LABELS[platform]
        pattern = rf"(^\| {re.escape(label)} bundle \| `)[0-9a-f]{{64}}(` \|$)"
        readme, count = re.subn(
            pattern, lambda match: match.group(1) + checksum + match.group(2),
            readme, flags=re.M,
        )
        if count != 1:
            raise ValueError(f"expected one README checksum row for {platform}")
    path.write_text(readme)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path, help="local directory containing one runtime directory per platform")
    parser.add_argument("platforms", nargs="*", choices=sorted(PLATFORMS),
                        help="platforms to build; default: all four")
    parser.add_argument("--output-root", type=Path,
                        help="bundle output directory; default: native/ and update README checksums")
    args = parser.parse_args()

    input_root = args.input_root.resolve(strict=True)
    output_root = args.output_root.resolve() if args.output_root else ROOT / "native"
    checksums = {}
    for platform in args.platforms or PLATFORMS:
        native_dir = input_root / platform
        if not native_dir.is_dir():
            parser.error(f"missing platform input directory: {native_dir}")
        output = output_root / platform / "bundle.tar.gz"
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/package_native.py"),
             platform, str(native_dir), str(output)],
            check=True,
        )
        checksums[platform] = sha256(output)
        print(f"{platform}: SHA-256 {checksums[platform]}")
    if args.output_root is None:
        update_readme(checksums)


if __name__ == "__main__":
    main()
