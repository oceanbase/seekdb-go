#!/usr/bin/env python3
"""Stage a seekdb executable, libseekdb, and local runtime dependencies."""

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from native_deps import collect_linux, collect_mac


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("darwin-arm64", "linux-amd64", "linux-arm64"))
    parser.add_argument("support_dir", type=Path, help="directory containing libseekdb")
    parser.add_argument("output_dir", type=Path, help="new platform runtime directory")
    parser.add_argument("--seekdb-bin", type=Path, required=True, help="locally supplied seekdb executable")
    parser.add_argument("--library-dir", type=Path, action="append", default=[],
                        help="additional directory to search for runtime libraries (repeatable)")
    args = parser.parse_args()

    library_name = "libseekdb.dylib" if args.platform == "darwin-arm64" else "libseekdb.so"
    support = args.support_dir.resolve(strict=True)
    executable = args.seekdb_bin.resolve(strict=True)
    search = [directory.resolve(strict=True) for directory in args.library_dir]
    if not (support / library_name).is_file():
        parser.error(f"missing {library_name} in {support}")
    output = args.output_dir.resolve()
    if output.exists():
        parser.error(f"output directory already exists: {output}")

    with tempfile.TemporaryDirectory(prefix="seekdb-release-") as temp_name:
        stage = Path(temp_name) / "stage"
        stage.mkdir()
        shutil.copy2(support / library_name, stage / library_name)
        binary = stage / "seekdb"
        shutil.copy2(executable, binary)
        binary.chmod(0o755)
        try:
            if args.platform.startswith("linux-"):
                collect_linux(stage, [support, *search])
            else:
                collect_mac(stage, support, executable, search)
        except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as error:
            parser.error(str(error))
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, output)
    print(f"staged {args.platform} runtime in {output}")


if __name__ == "__main__":
    main()
