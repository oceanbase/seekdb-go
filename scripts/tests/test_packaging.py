import hashlib
import io
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import native_deps
import package_native
import verify_bundles


def macho_header(cpu=0x0100000C, subtype=0, endian="<"):
    """Minimal synthetic mach_header_64 for portable header-check tests."""
    return struct.pack(endian + "8I", 0xFEEDFACF, cpu, subtype, 2, 0, 0, 0, 0)


def universal_macho(endian=">", fat64=False, arm_payload=None):
    layout = "IIQQII" if fat64 else "IIIII"
    entry_size = struct.calcsize(endian + layout)
    table_end = 8 + 2 * entry_size
    x86 = macho_header(cpu=0x01000007)
    arm = arm_payload if arm_payload is not None else macho_header()
    entries = [(0x01000007, 0, table_end, len(x86), 0),
               (0x0100000C, 0, table_end + len(x86), len(arm), 0)]
    table = b"".join(struct.pack(endian + layout, *(entry + ((0,) if fat64 else ())))
                     for entry in entries)
    return struct.pack(endian + "II", 0xCAFEBABF if fat64 else 0xCAFEBABE, 2) + table + x86 + arm


class PortableMacArchitectureTests(unittest.TestCase):
    def check(self, contents):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime"
            path.write_bytes(contents)
            with patch.object(subprocess, "run", side_effect=AssertionError("must not invoke a native tool")):
                package_native.verify_machine("darwin-arm64", path)

    def test_thin_and_universal_arm64_without_mac_tools(self):
        fixtures = [macho_header(endian=endian) for endian in ["<", ">"]]
        fixtures += [universal_macho(endian, fat64) for endian in ["<", ">"] for fat64 in [False, True]]
        for fixture in fixtures:
            with self.subTest(magic=fixture[:4]):
                self.check(fixture)

    def test_rejects_other_targets_and_truncated_headers(self):
        fixtures = [b"", b"\x7fELF" + bytes(60), macho_header(cpu=0x01000007),
                    macho_header(subtype=2), macho_header(cpu=0x0200000C),
                    macho_header()[:16]]
        for fixture in fixtures:
            with self.subTest(header=fixture[:12]), self.assertRaises(ValueError):
                self.check(fixture)

    def test_rejects_malformed_universal_files(self):
        for endian in ["<", ">"]:
            for fat64 in [False, True]:
                layout = "IIQQII" if fat64 else "IIIII"
                magic = 0xCAFEBABF if fat64 else 0xCAFEBABE
                extra = (0,) if fat64 else ()
                fixtures = [
                    struct.pack(endian + "II", magic, 0),
                    struct.pack(endian + "II", magic, 100),
                    universal_macho(endian, fat64, arm_payload=macho_header(cpu=0x01000007)),
                    universal_macho(endian, fat64, arm_payload=macho_header()[:16]),
                ]
                for offset, size in [(0, 32), (4096, 32), (8 + struct.calcsize(endian + layout), 4096)]:
                    fixtures.append(struct.pack(endian + "II", magic, 1)
                                    + struct.pack(endian + layout, 0x0100000C, 0, offset, size, 0, *extra)
                                    + macho_header())
                for fixture in fixtures:
                    with self.subTest(endian=endian, fat64=fat64, fixture=fixture[:24]), self.assertRaises(ValueError):
                        self.check(fixture)

    def release_fixture(self, root, runtime, wrong=None):
        """Build matching synthetic inputs/archives for the release verifier."""
        readme = []
        elf = bytearray(64)
        elf[:4] = b"\x7fELF"
        pe = bytearray(88)
        pe[:2] = b"MZ"
        struct.pack_into("<I", pe, 0x3C, 64)
        pe[64:68] = b"PE\0\0"
        struct.pack_into("<H", pe, 68, 0x8664)
        for platform, (library, executable) in package_native.PLATFORMS.items():
            if platform.startswith("linux"):
                struct.pack_into("<H", elf, 18, 62 if platform == "linux-amd64" else 183)
                contents = bytes(elf)
            else:
                contents = bytes(pe) if platform == "windows-amd64" else runtime
            stage = root / "inputs" / platform
            stage.mkdir(parents=True)
            files = {library: contents, executable: contents}
            if platform == "darwin-arm64":
                files["libdependency.dylib"] = runtime
                if wrong is not None:
                    files[wrong] = macho_header(cpu=0x01000007)
            archive_path = root / "native" / platform / "bundle.tar.gz"
            archive_path.parent.mkdir(parents=True)
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, value in files.items():
                    (stage / name).write_bytes(value)
                    archive_name = "seekdb.bin" if name == executable and platform != "windows-amd64" else name
                    entry = tarfile.TarInfo(archive_name)
                    entry.size = len(value)
                    archive.addfile(entry, io.BytesIO(value))
                if platform != "windows-amd64":
                    entry = tarfile.TarInfo("seekdb")
                    entry.size = 10
                    archive.addfile(entry, io.BytesIO(b"#!/bin/sh\n"))
            checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            readme.append(f"| {verify_bundles.LABELS[platform]} bundle | `{checksum}` |")
        (root / "README.md").write_text("\n".join(readme))

    def test_all_platform_release_inputs_work_without_native_tools(self):
        for runtime in [macho_header(), universal_macho(), universal_macho(fat64=True)]:
            with self.subTest(magic=runtime[:4]), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.release_fixture(root, runtime)
                empty_path = root / "empty-path"
                empty_path.mkdir()
                with patch.object(verify_bundles, "ROOT", root), patch.dict(os.environ, {"PATH": str(empty_path)}), \
                        patch.object(sys, "argv", ["verify_bundles.py", "--input-root", str(root / "inputs")]), \
                        patch.object(subprocess, "run", side_effect=AssertionError("must not invoke a native tool")):
                    verify_bundles.main()

    def test_matching_archive_cannot_hide_wrong_architecture(self):
        for wrong in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.release_fixture(root, macho_header(), wrong=wrong)
                with patch.object(verify_bundles, "ROOT", root), self.assertRaisesRegex(ValueError, "does not contain arm64"):
                    verify_bundles.verify("darwin-arm64", (root / "README.md").read_text(), root / "inputs")


class MacArchitectureTests(unittest.TestCase):
    def test_every_runtime_file_requires_arm64(self):
        for wrong in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as directory:
                stage = Path(directory)
                for name in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
                    (stage / name).touch()

                def inspect(*args):
                    if args[0] == "lipo":
                        return "x86_64" if Path(args[-1]).name == wrong else "arm64"
                    return f"{args[-1]}:\n"

                with patch.object(native_deps, "run", side_effect=inspect):
                    with self.assertRaisesRegex(ValueError, f"{wrong} does not contain arm64"):
                        native_deps.verify_mac(stage)


@unittest.skipUnless(sys.platform == "darwin", "requires macOS clang, lipo and otool")
class MacPackagingCommandsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.stage = self.root / "inputs" / "darwin-arm64"
        self.stage.mkdir(parents=True)
        self.source = self.root / "fixture.c"
        self.source.write_text("int main(void) { return 0; }\n")

    def compile(self, name, arch):
        command = ["clang", "-arch", arch, str(self.source), "-o", str(self.stage / name)]
        if name.endswith(".dylib"):
            command.append("-dynamiclib")
        subprocess.run(command, check=True, capture_output=True)

    def package(self):
        return subprocess.run([sys.executable, str(SCRIPTS / "package_native.py"),
                               "darwin-arm64", str(self.stage), str(self.root / "bundle.tar.gz")],
                              text=True, capture_output=True)

    def test_direct_packager_rejects_real_x86_64_files(self):
        for wrong in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
            with self.subTest(wrong=wrong):
                for name in ["seekdb", "libseekdb.dylib", "libdependency.dylib"]:
                    self.compile(name, "x86_64" if name == wrong else "arm64")
                result = self.package()
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(f"{wrong} does not contain arm64", result.stderr)
                self.assertFalse((self.root / "bundle.tar.gz").exists())

    def test_arm64_and_universal_inputs_are_accepted(self):
        self.compile("seekdb", "arm64")
        self.compile("libseekdb.dylib", "arm64")
        self.compile("libdependency.dylib", "x86_64")
        x86 = self.root / "x86.dylib"
        (self.stage / "libdependency.dylib").rename(x86)
        self.compile("libdependency.dylib", "arm64")
        subprocess.run(["lipo", "-create", str(x86), str(self.stage / "libdependency.dylib"),
                        "-output", str(self.stage / "libdependency.dylib")], check=True, capture_output=True)
        result = self.package()
        self.assertEqual(result.returncode, 0, result.stderr)
        with tarfile.open(self.root / "bundle.tar.gz") as archive:
            self.assertEqual(set(archive.getnames()),
                             {"seekdb", "seekdb.bin", "libseekdb.dylib", "libdependency.dylib"})
        # Publishing this real universal bundle must also work without lipo or
        # otool, even though those tools were used to build it above.
        destination = self.root / "native" / "darwin-arm64" / "bundle.tar.gz"
        destination.parent.mkdir(parents=True)
        contents = (self.root / "bundle.tar.gz").read_bytes()
        destination.write_bytes(contents)
        readme = f"| macOS arm64 bundle | `{hashlib.sha256(contents).hexdigest()}` |\n"
        with patch.object(verify_bundles, "ROOT", self.root), patch.dict(os.environ, {"PATH": ""}), \
                patch.object(subprocess, "run", side_effect=AssertionError("must not invoke a native tool")):
            verify_bundles.verify("darwin-arm64", readme, self.root / "inputs")

    def test_release_input_check_rejects_matching_wrong_architecture(self):
        self.compile("seekdb", "x86_64")
        self.compile("libseekdb.dylib", "arm64")
        # A matching checksum and matching archive bytes must not bypass the
        # architecture check on the supplied release inputs.
        destination = self.root / "native" / "darwin-arm64" / "bundle.tar.gz"
        destination.parent.mkdir(parents=True)
        with tarfile.open(destination, "w:gz") as archive:
            for name, contents in {
                "seekdb": b"#!/bin/sh\n",
                "seekdb.bin": (self.stage / "seekdb").read_bytes(),
                "libseekdb.dylib": (self.stage / "libseekdb.dylib").read_bytes(),
            }.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(contents)
                archive.addfile(entry, io.BytesIO(contents))
        checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
        readme = f"| macOS arm64 bundle | `{checksum}` |\n"
        with patch.object(verify_bundles, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "seekdb does not contain arm64"):
                verify_bundles.verify("darwin-arm64", readme, self.root / "inputs")


if __name__ == "__main__":
    unittest.main()
