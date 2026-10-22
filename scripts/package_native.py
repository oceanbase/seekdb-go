#!/usr/bin/env python3
"""Create a reproducible seekdb bundle for a native Go module."""

import argparse
import gzip
import io
import struct
import subprocess
import tarfile
from pathlib import Path

from native_deps import verify_linux_static, verify_mac

PLATFORMS = {
    "darwin-arm64": ("libseekdb.dylib", "seekdb"),
    "linux-amd64": ("libseekdb.so", "seekdb"),
    "linux-arm64": ("libseekdb.so", "seekdb"),
    "windows-amd64": ("seekdb.dll", "seekdb.exe"),
}


def bundle_files(platform: str, native_dir: Path) -> list[Path]:
    library, executable = PLATFORMS[platform]
    required = {library, executable}
    files = sorted(
        path for path in native_dir.iterdir()
        if path.is_file() and (
            path.name in required
            or path.name.endswith((".dylib", ".so"))
            or ".so." in path.name
            or (platform == "windows-amd64" and path.name.endswith(".dll"))
        )
    )
    missing = required - {path.name for path in files}
    if missing:
        raise ValueError(f"missing native files in {native_dir}: {', '.join(sorted(missing))}")
    return files


def verify_macho_arm64(path: Path) -> None:
    """Check thin/universal Mach-O headers without invoking macOS tools.

    Layouts are mach_header_64, fat_arch and fat_arch_64 from Apple's
    mach-o/loader.h and mach-o/fat.h. This is an architecture check; packaging
    separately validates load commands and dependencies with lipo/otool.
    """
    thin_formats = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">"}
    fat_formats = {
        b"\xca\xfe\xba\xbe": (">", "IIIII"),
        b"\xbe\xba\xfe\xca": ("<", "IIIII"),
        b"\xca\xfe\xba\xbf": (">", "IIQQII"),
        b"\xbf\xba\xfe\xca": ("<", "IIQQII"),
    }

    def arm64_header(header: bytes) -> bool:
        endian = thin_formats.get(header[:4])
        if endian is None or len(header) < 32:
            return False
        cpu, subtype = struct.unpack_from(endian + "II", header, 4)
        # CPU_TYPE_ARM64 / CPU_SUBTYPE_ARM64_ALL. arm64e and arm64_32 are
        # distinct targets, not the generic arm64 slice required by this bundle.
        return cpu == 0x0100000C and subtype & 0x00FFFFFF == 0

    with path.open("rb") as binary:
        file_size = binary.seek(0, 2)
        binary.seek(0)
        header = binary.read(32)
        if header[:4] in thin_formats:
            if arm64_header(header):
                return
        elif header[:4] in fat_formats and len(header) >= 8:
            endian, layout = fat_formats[header[:4]]
            entry_size = struct.calcsize(endian + layout)
            count = struct.unpack_from(endian + "I", header, 4)[0]
            table_end = 8 + count * entry_size
            if count == 0 or table_end > file_size:
                raise ValueError(f"invalid Mach-O architecture table: {path}")
            found = False
            for index in range(count):
                binary.seek(8 + index * entry_size)
                cpu, subtype, offset, size, *_ = struct.unpack(
                    endian + layout, binary.read(entry_size))
                if offset < table_end or size == 0 or offset + size > file_size:
                    raise ValueError(f"invalid Mach-O slice bounds: {path}")
                if cpu == 0x0100000C and subtype & 0x00FFFFFF == 0:
                    binary.seek(offset)
                    if size < 32 or not arm64_header(binary.read(32)):
                        raise ValueError(f"invalid arm64 Mach-O slice: {path}")
                    found = True
            if found:
                return
    raise ValueError(f"{path} does not contain arm64")


def verify_machine(platform: str, path: Path) -> None:
    if platform == "darwin-arm64":
        verify_macho_arm64(path)
        return
    with path.open("rb") as binary:
        header = binary.read(64)
        if platform.startswith("linux-"):
            expected = 62 if platform == "linux-amd64" else 183
            if header[:4] != b"\x7fELF" or struct.unpack_from("<H", header, 18)[0] != expected:
                raise ValueError(f"wrong ELF architecture: {path}")
        else:
            if header[:2] != b"MZ":
                raise ValueError(f"not a Windows PE file: {path}")
            binary.seek(struct.unpack_from("<I", header, 0x3C)[0])
            if binary.read(4) != b"PE\0\0" or struct.unpack("<H", binary.read(2))[0] != 0x8664:
                raise ValueError(f"wrong PE architecture: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=PLATFORMS)
    parser.add_argument("native_dir", type=Path)
    parser.add_argument("output", type=Path, help="output bundle.tar.gz path")
    args = parser.parse_args()

    native_dir = args.native_dir.resolve(strict=True)
    try:
        files = bundle_files(args.platform, native_dir)
        for path in files:
            verify_machine(args.platform, path)
        if args.platform == "darwin-arm64":
            verify_mac(native_dir)
        elif args.platform.startswith("linux-"):
            verify_linux_static(native_dir)
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    library, executable = PLATFORMS[args.platform]
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    launcher = b'#!/bin/sh\n"${0%/*}/seekdb.bin" "$@"\n'
    with destination.open("wb") as output, gzip.GzipFile(
        fileobj=output, mode="wb", filename="", mtime=0
    ) as compressed, tarfile.open(fileobj=compressed, mode="w") as archive:
        for path in files:
            name = "seekdb.bin" if path.name == executable and args.platform != "windows-amd64" else path.name
            info = tarfile.TarInfo(name)
            info.size = path.stat().st_size
            info.mode = 0o755 if path.name == executable or path.name == library else 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as source:
                archive.addfile(info, source)
            print(f"included {name} ({info.size} bytes)")
        if args.platform != "windows-amd64":
            info = tarfile.TarInfo(executable)
            info.size = len(launcher)
            info.mode = 0o755
            info.mtime = 0
            archive.addfile(info, io.BytesIO(launcher))
            print(f"included {executable} launcher ({len(launcher)} bytes)")
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
